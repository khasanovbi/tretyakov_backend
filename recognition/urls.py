from django.conf.urls import include, url
from rest_framework import routers

from recognition.views import PaintingViewSet, RecognizeAPIView

router = routers.SimpleRouter()
router.register(r'painting', PaintingViewSet)

urlpatterns = [
    url(r'', include(router.urls)),
    url(r'^recognize$', RecognizeAPIView.as_view())
]
