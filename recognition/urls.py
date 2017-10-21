from rest_framework import routers

from recognition.views import PaintingViewSet

router = routers.SimpleRouter()
router.register(r'painting', PaintingViewSet)

urlpatterns = router.urls
