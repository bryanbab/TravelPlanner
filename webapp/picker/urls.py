from django.urls import path

from . import views

urlpatterns = [
    path("", views.home, name="home"),
    path("save_location", views.save_location, name="save_location"),
]