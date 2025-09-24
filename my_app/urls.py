from django.contrib import admin
from django.urls import path
from my_app import views

urlpatterns = [
    # Landing page
    path('', views.index, name='home'),

    # PDF operations
    path('rotate/', views.rotate, name='rotate'),
    path('protect/', views.protect_pdf, name='protect_pdf'),
    path('split/', views.split_pdf, name='split_pdf'),
    path('merge/', views.merge_pdf, name='merge_pdf'),
    path('delete/', views.delete_pages, name='delete_pages'),
    path('copy/', views.copy_pages, name='copy_pages'),
    path('extract_images/', views.extract_images, name='extract_images'),
    path('add_watermark/', views.add_text_watermark, name='add_watermark'),

    # PDF ↔ Word conversions
    path('pdf_to_word/', views.pdf_to_word, name='pdf_to_word'),
    path('word_to_pdf/', views.word_to_pdf, name='word_to_pdf'),

    # Django admin (optional)
    path('admin/', admin.site.urls),
]
