from rest_framework import serializers

from recognition.models import Author, Painting


class _PaintingSerializer(serializers.ModelSerializer):
    class Meta:
        model = Painting
        fields = ('id', 'title', 'image', 'years', 'description')


class AuthorSerializer(serializers.ModelSerializer):
    full_name = serializers.SerializerMethodField()
    paintings = serializers.SerializerMethodField()

    class Meta:
        model = Author
        fields = ('full_name', 'paintings')

    def get_full_name(self, author):
        return f'{author.last_name} {author.first_name} {author.middle_name}'

    def get_paintings(self, author):
        exclude_painting_id = self.context.get('exclude_painting_id')
        if exclude_painting_id:
            instance = author.paintings.exclude(id=exclude_painting_id)
        else:
            instance = author.paintings
        return _PaintingSerializer(instance=instance, many=True, read_only=True).data


class PaintingSerializer(serializers.ModelSerializer):
    author = serializers.SerializerMethodField()

    class Meta:
        model = Painting
        fields = ('id', 'author', 'title', 'image', 'years', 'description')

    def get_author(self, obj):
        serializer_context = {'exclude_painting_id': obj.id}
        return AuthorSerializer(obj.author, context=serializer_context).data
