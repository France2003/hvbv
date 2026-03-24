from django.urls import path
from . import views

app_name = 'therapies'

urlpatterns = [
    path('physical/', views.physical_therapy, name='physical'),
    path('speech/', views.speech_therapy, name='speech'),
    path('occupational/', views.occupational_therapy, name='occupational'),
]