import tempfile

from rest_framework import mixins, views, viewsets
from rest_framework.response import Response

from recognition.models import Painting
from recognition.serializers import PaintingSerializer
from scripts.label_image import main


class PaintingViewSet(mixins.RetrieveModelMixin,
                      mixins.ListModelMixin,
                      viewsets.GenericViewSet):
    queryset = Painting.objects.select_related('author').order_by('id')
    serializer_class = PaintingSerializer


class RecognizeAPIView(views.APIView):
    def post(self, request, format=None):
        tempfile_ = tempfile.NamedTemporaryFile()
        tempfile_.write(request.data['file'].read())
        painting_id = main(tempfile_.name)
        painting = Painting.objects.get(id=painting_id)
        return Response(PaintingSerializer(painting).data)
