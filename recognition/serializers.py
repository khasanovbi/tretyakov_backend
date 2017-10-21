from rest_framework import serializers

from recognition.models import Painting


class PaintingSerializer(serializers.ModelSerializer):
    author = serializers.SerializerMethodField()

    class Meta:
        model = Painting
        fields = ('id', 'author', 'title', 'image', 'years', 'description')

    def get_author(self, obj):
        author = obj.author
        return f'{author.last_name} {author.first_name} {author.middle_name}'
