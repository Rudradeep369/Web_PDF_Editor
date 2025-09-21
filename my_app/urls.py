from django.contrib import admin
from django.urls import path
from my_app import views

urlpatterns = [
    path('', views.index, name='home'),
    path('rotate/', views.rotate, name='rotate'),
    path("protect/", views.protect_pdf, name="protect_pdf"),
]