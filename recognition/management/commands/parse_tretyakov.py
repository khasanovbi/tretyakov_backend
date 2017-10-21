import asyncio
import copy
import logging
import os
from concurrent.futures import ThreadPoolExecutor
from itertools import chain

import aiohttp
import re
from bs4 import BeautifulSoup
from django.conf import settings
from django.core.files.base import ContentFile
from django.core.management.base import BaseCommand
from django.db.transaction import atomic

from recognition.models import Author, Painting

BASE_URL = 'https://www.tretyakovgallery.ru'

PAINTING_LIST_URL_TEMPLATE = BASE_URL + '/collection/?category=all&period=all&page={page}&place=all'
PAINTINGS_DIR = os.path.join(settings.STATIC_ROOT, 'paintings')

logger = logging.getLogger('tretyakov.parser')

# To don't lock sqlite 1 worker used
thread_pool_executor = ThreadPoolExecutor(max_workers=1)


alias_re = re.compile(r'\(.*\)$')


def get_absolute_url(relative_url):
    return f'{BASE_URL}{relative_url}'


async def parse_paintings_list(page, semaphore):
    async with semaphore:
        async with aiohttp.ClientSession() as session:
            async with session.get(PAINTING_LIST_URL_TEMPLATE.format(page=page)) as resp:
                text = await resp.text()
    soup = BeautifulSoup(text, 'html.parser')
    paintings = (soup
                 .find('div', {'class': 'collections__list'})
                 .find_all('a', {'class': 'collections-item'}))
    logger.debug('Images list item links from page %s finished', page)
    return [get_absolute_url(painting['href']) for painting in paintings]


async def get_pages_count():
    async with aiohttp.ClientSession() as session:
        async with session.get(PAINTING_LIST_URL_TEMPLATE.format(page=1)) as resp:
            text = await resp.text()
    soup = BeautifulSoup(text, 'html.parser')
    last_pagination_item = (soup
                            .find('ul', attrs={'class': 'collections-nav__list pagination'})
                            # TODO
                            .find_all('li', attrs={'class': 'pagination__item'})[-2])
    return int(last_pagination_item.span.string)


async def get_painting_metainfo(url, semaphore):
    async with aiohttp.ClientSession() as session:
        async with semaphore:
            logger.info('Getting metainfo from %s', url)
            async with session.get(url) as resp:
                text = await resp.text()
    soup = BeautifulSoup(text, 'html.parser')
    title_with_year = soup.find('div', {'class': 'exhibit-info__title'}).string
    image_tag = soup.find('div', {'class': 'exhibit-slide'}).find('img')
    if not image_tag:
        logger.error('Image not found at %s', url)
        return None

    image_url = get_absolute_url(image_tag['src'])

    split_result = title_with_year.rsplit('.', 1)
    if len(split_result) == 1:
        title = title_with_year.strip()
        years = None
    else:
        title = split_result[0].strip()
        years = split_result[1].strip()

    soup.find('div', {'class': 'exhibit-some__title'})

    description = soup.find(attrs={'class': 'exhibit__info'}).p.get_text().strip()

    author = soup.find(attrs={'class': 'exhibit-info__author'}).a.string
    author = alias_re.sub('', author).strip()
    first_name = middle_name = None
    if 'Неизвестный художник' in author:
        last_name = author
    else:
        split_name = author.rsplit(' ', 2)
        split_name_len = len(split_name)
        if split_name_len == 1:
            last_name = split_name[0]
        elif split_name_len == 2:
            last_name, first_name = split_name
        else:
            last_name, first_name, middle_name = split_name

    return {
        'site_url': url,
        'title': title,
        'image_url': image_url,
        'years': years,
        'description': description,
        'author': {
            'first_name': first_name,
            'last_name': last_name,
            'middle_name': middle_name,
        },
    }


@atomic
def save_painting(metainfo, binary_image):
    author, _ = Author.objects.get_or_create(**metainfo['author'])
    site_url = metainfo['site_url']
    old_painting = Painting.objects.filter(site_url=site_url).first()
    if old_painting:
        logger.debug('Skip painting saving %s', site_url)
        return

    painting = Painting(
        author=author,
        site_url=metainfo['site_url'],
        title=metainfo['title'],
        years=metainfo['years'],
        description=metainfo['description'],
    )
    painting.image.save(metainfo['filename'], ContentFile(binary_image))


async def fetch_image(metainfo, semaphore):
    image_url = metainfo['image_url']
    async with aiohttp.ClientSession() as session:
        async with semaphore:
            async with session.get(image_url) as resp:
                binary_image = await resp.read()
    await asyncio.get_event_loop().run_in_executor(
        thread_pool_executor,
        save_painting,
        metainfo,
        binary_image
    )
    logger.info('Save %s', metainfo['title'])


def normalize_metainfo_list(raw_metainfo_list):
    metainfo_list = []
    for item_raw_metainfo in raw_metainfo_list:
        item_metainfo = copy.copy(item_raw_metainfo)
        image_url = item_raw_metainfo['image_url']
        _, ext = os.path.splitext(image_url)
        filename = f'{item_raw_metainfo["title"]}{ext}'
        item_metainfo['filename'] = filename
        metainfo_list.append(item_metainfo)

    return metainfo_list


async def run_parser(pages_count=None):
    max_pages_count = await get_pages_count()
    pages_count = min(pages_count, max_pages_count) if pages_count else max_pages_count

    logger.info('Parse list items links')
    links_semaphore = asyncio.Semaphore(50)
    tasks = []
    for page in range(1, pages_count + 1):
        tasks.append(parse_paintings_list(page, links_semaphore))
    site_urls = list(chain.from_iterable(await asyncio.gather(*tasks)))

    site_urls = set(site_urls)
    site_urls = site_urls.difference(Painting.objects.values_list('site_url', flat=True))
    if not site_urls:
        return pages_count

    logger.info('Fetch meta info')
    meta_semaphore = asyncio.Semaphore(20)
    tasks = []
    for url in site_urls:
        tasks.append(get_painting_metainfo(url, meta_semaphore))
    raw_metainfo_list = [item_metainfo
                         for item_metainfo in await asyncio.gather(*tasks)
                         if item_metainfo]
    if not raw_metainfo_list:
        return pages_count

    metainfo_list = normalize_metainfo_list(raw_metainfo_list)

    logger.info('Fetch images')
    os.makedirs(PAINTINGS_DIR, exist_ok=True)
    tasks = []
    images_semaphore = asyncio.Semaphore(20)
    for item_metainfo in metainfo_list:
        tasks.append(fetch_image(item_metainfo, images_semaphore))
    await asyncio.wait(tasks)
    return pages_count


class Command(BaseCommand):
    help = 'Closes the specified poll for voting'

    def add_arguments(self, parser):
        parser.add_argument('pages', nargs='?', type=int)

    def handle(self, *args, **options):
        pages = options["pages"]
        loop = asyncio.get_event_loop()
        pages = loop.run_until_complete(run_parser(pages))
        loop.close()

        self.stdout.write(self.style.SUCCESS(f'Successfully parse {pages} page(s)'))
