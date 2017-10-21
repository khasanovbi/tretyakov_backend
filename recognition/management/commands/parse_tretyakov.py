import asyncio
import copy
import logging
import os
from itertools import chain

import aiofiles
import aiohttp
from bs4 import BeautifulSoup
from django.conf import settings
from django.core.management.base import BaseCommand

BASE_URL = 'https://www.tretyakovgallery.ru'

PAINTING_LIST_URL_TEMPLATE = BASE_URL + '/collection/?category=all&period=all&page={page}&place=all'
PAINTINGS_DIR = os.path.join(settings.STATIC_ROOT, 'paintings')

logger = logging.getLogger('tretyakov.parser')


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
    return [painting['href'] for painting in paintings]


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
        year = None
    else:
        title = split_result[0].strip()
        year = split_result[1].strip()

    soup.find('div', {'class': 'exhibit-some__title'})

    related_image_link_tags = soup.find_all('a', {'class': 'collections-item'})

    related_image_urls = []
    for related_image_link_tag in related_image_link_tags:
        related_image_urls.append(get_absolute_url(related_image_link_tag['href']))

    description = soup.find(attrs={'class': 'exhibit__info'}).p.get_text().strip()

    author = soup.find(attrs={'class': 'exhibit-info__author'}).a.string

    return {
        'site_url': url,
        'title': title,
        'image_url': image_url,
        'years': year,
        'description': description,
        'author': author,
        'related_image_urls': related_image_urls,
    }


async def fetch_image(metainfo, semaphore):
    image_url = metainfo['image_url']
    filepath = metainfo['filepath']
    async with aiohttp.ClientSession() as session:
        async with semaphore:
            async with session.get(image_url) as resp:
                binary_image = await resp.read()

    async with aiofiles.open(filepath, mode='wb') as f:
        await f.write(binary_image)
    logger.info('Save file %s', filepath)


def normalize_metainfo_list(raw_metainfo_list):
    metainfo_list = []
    for item_raw_metainfo in raw_metainfo_list:
        item_metainfo = copy.copy(item_raw_metainfo)
        image_url = item_raw_metainfo['image_url']
        _, ext = os.path.splitext(image_url)
        filepath = os.path.join(PAINTINGS_DIR, f'{item_raw_metainfo["title"]}{ext}')
        item_metainfo['filepath'] = filepath
        metainfo_list.append(item_metainfo)

    return metainfo_list


async def run_parser(pages_count=None):
    if not pages_count:
        pages_count = await get_pages_count()

    logger.info('Parse list items links')
    links_semaphore = asyncio.Semaphore(50)
    tasks = []
    for page in range(1, pages_count + 1):
        tasks.append(parse_paintings_list(page, links_semaphore))
    urls = list(chain.from_iterable(await asyncio.gather(*tasks)))

    logger.info('Fetch meta info')
    meta_semaphore = asyncio.Semaphore(20)
    tasks = []
    for url in urls:
        tasks.append(get_painting_metainfo(get_absolute_url(url), meta_semaphore))
    raw_metainfo_list = [item_metainfo
                         for item_metainfo in await asyncio.gather(*tasks)
                         if item_metainfo]

    metainfo_list = normalize_metainfo_list(raw_metainfo_list)

    logger.info('Fetch images')
    os.makedirs(PAINTINGS_DIR, exist_ok=True)
    tasks = []
    images_semaphore = asyncio.Semaphore(20)
    for item_metainfo in metainfo_list:
        tasks.append(fetch_image(item_metainfo, images_semaphore))
    await asyncio.wait(tasks)


class Command(BaseCommand):
    help = 'Closes the specified poll for voting'

    def add_arguments(self, parser):
        parser.add_argument('pages', nargs='?', type=int)

    def handle(self, *args, **options):
        pages = options["pages"]
        loop = asyncio.get_event_loop()
        loop.run_until_complete(run_parser(pages))
        loop.close()

        self.stdout.write(self.style.SUCCESS(f'Successfully parse {pages} page(s)'))
