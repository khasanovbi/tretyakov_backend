import os
from shutil import copyfile

from django.core.management.base import BaseCommand

from recognition.models import Author, Painting


class Command(BaseCommand):
    def add_arguments(self, parser):
        parser.add_argument('pages', nargs='?', type=int)

    def handle(self, *args, **options):
        os.makedirs('tf_files/photos', exist_ok=True)
        for author in Author.objects.all():
            for painting in Painting.objects.filter(author=author).all():
                os.makedirs(f'tf_files/photos/{author.id}/', exist_ok=True)
                copyfile(
                    painting.image.path,
                    f'tf_files/photos/{author.id}/{painting.id}'
                    f'{os.path.splitext(painting.image.path)[1]}'
                )
