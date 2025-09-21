from django.contrib import admin
from django.urls import path
from my_app import views

urlpatterns = [
    path('', views.index, name='home'),
    path('rotate/', views.rotate, name='rotate'),
    path("protect/", views.protect_pdf, name="protect_pdf"),
    path("split/", views.split_pdf, name="split_pdf"),
    path('merge/', views.merge_pdf, name='merge_pdf'),
    path('delete/', views.delete_pages, name='delete_pages'),
]