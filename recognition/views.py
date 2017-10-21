from rest_framework import mixins, viewsets

from recognition.models import Painting
from recognition.serializers import PaintingSerializer


class PaintingViewSet(mixins.RetrieveModelMixin,
                      mixins.ListModelMixin,
                      viewsets.GenericViewSet):
    queryset = Painting.objects.select_related('author')
    serializer_class = PaintingSerializer
