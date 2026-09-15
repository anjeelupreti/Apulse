from django.urls import path

from .views import MeView

app_name = "identity"

urlpatterns = [
    path("me/", MeView.as_view(), name="me"),
]
