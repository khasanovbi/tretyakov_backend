from django.core.management.base import BaseCommand
import os
from shutil import copyfile

from recognition.models import Author, Painting

class Command(BaseCommand):
    help = 'Closes the specified poll for voting'

    def add_arguments(self, parser):
        parser.add_argument('pages', nargs='?', type=int)

    def handle(self, *args, **options):
        for author in Author.objects.all():
            for painting in Painting.objects.filter(author=author).all():
                os.makedirs('tf_files/photos', exist_ok=True)
                os.makedirs(f'tf_files/photos/{author.id}/', exist_ok=True)
                copyfile(
                    painting.image.path,
                    f'tf_files/photos/{author.id}/{painting.id}'
                    f'{os.path.splitext(painting.image.path)[1]}'
                )

