from django.urls import path
from . import views

app_name = 'services'

urlpatterns = [
    path('', views.services, name='services'),
    path('temp/', views.services_temp, name='services_temp'),
    path('checkout/status/<slug:txn_ref>/', views.service_checkout_status, name='service_checkout_status'),
    # Service category landing pages (slugged)
    path('category/<slug:slug>/', views.category_detail, name='category_detail'),
    path('<slug:slug>/checkout/', views.service_checkout, name='service_checkout'),
    # Individual service detail fallback
    path('<slug:slug>/', views.service_detail, name='service_detail'),
]
