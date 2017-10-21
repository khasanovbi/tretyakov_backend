from django.db import models


class Author(models.Model):
    first_name = models.CharField(max_length=50, null=True)
    middle_name = models.CharField(max_length=50, null=True)
    last_name = models.CharField(max_length=50)


class Painting(models.Model):
    author = models.ForeignKey(Author, related_name='paintings')
    title = models.CharField(max_length=256)
    image = models.ImageField(upload_to='paintings')
    site_url = models.CharField(max_length=256, unique=True)
    years = models.CharField(max_length=256)
    description = models.TextField()
