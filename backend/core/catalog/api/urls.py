from rest_framework.routers import DefaultRouter

from .views import CounterViewSet, ItemViewSet

app_name = "catalog"

router = DefaultRouter()
router.register("catalogue/items", ItemViewSet, basename="catalogue-item")
router.register("catalogue/counter", CounterViewSet, basename="catalogue-counter")

urlpatterns = router.urls
