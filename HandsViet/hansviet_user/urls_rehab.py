from django.urls import path
from . import views

app_name = 'rehab'

urlpatterns = [
    path('', views.rehab_fields, name='fields'),
    path('<slug:slug>/', views.rehab_field_detail, name='detail'),
]
