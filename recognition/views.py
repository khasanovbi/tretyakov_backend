import tempfile

from rest_framework import generics, mixins, viewsets
from rest_framework.response import Response

from recognition.models import Painting
from recognition.serializers import PaintingSerializer, RecognizeSerializer
from scripts.label_image import main


class PaintingViewSet(mixins.RetrieveModelMixin,
                      mixins.ListModelMixin,
                      viewsets.GenericViewSet):
    queryset = Painting.objects.select_related('author').order_by('id')
    serializer_class = PaintingSerializer


class ProgramAPIView(generics.GenericAPIView):
    def get(self, request, format=None):
        return Response(data={
            "data": [
                {
                    "title": "Город и люди. Москва в графике ХХ века",
                    "dates": "11 октября 2017 - 28 января 2018",
                    "picture": "https://www.tretyakovgallery.ru/upload/iblock/951/95170e80eebc1f942139bf69536af350.jpg",
                    "location": "Новая Третьяковка",
                    "description": "А.А. Дейнека. Площадь Свердлова. 1941–1946. Серия «Москва военная». Бумага, гуашь, темпера, уголь. 67 х 81,7. Третьяковская галерея"
                }
            ]
        })


class RecognizeAPIView(generics.GenericAPIView):
    serializer_class = RecognizeSerializer

    def post(self, request, format=None):
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        tempfile_ = tempfile.NamedTemporaryFile()
        with serializer.validated_data['file'] as f:
            tempfile_.write(f.read())
        painting_id = main(tempfile_.name)

        painting = Painting.objects.get(id=painting_id)
        return Response(PaintingSerializer(painting, context=self.get_serializer_context()).data)
