from django.urls import path
from . import views

app_name = 'pages'

urlpatterns = [
    path('', views.home, name='home'),
    path('about/', views.about, name='about'),
    path('booking/', views.booking, name='booking'),
    path('services/', views.services, name='services'),
    path('packages/<slug:slug>/buy/', views.buy_package, name='package_buy'),
    path('experts/', views.experts, name='experts'),
    path('facilities/', views.facilities, name='facilities'),
    path('exercise-library/', views.exercise_library, name='exercise_library'),
    path('payment/vnpay/<slug:slug>/', views.vnpay_start, name='vnpay_start'),
    path('payment/vnpay/return/', views.vnpay_return, name='vnpay_return'),
    path('payment/qr/webhook/', views.qr_payment_webhook, name='qr_payment_webhook'),
    path('physical-therapy/', views.physical_therapy, name='physical_therapy'),
    path('occupational-therapy/', views.occupational_therapy, name='occupational_therapy'),
    path('speech-therapy/', views.speech_therapy, name='speech_therapy'),
    path('rehab/', views.rehab_fields, name='rehab_fields'),
    path('contact/', views.contact, name='contact'),
    path('contact/click-track/', views.contact_click_track, name='contact_click_track'),
    path('faq/', views.faq, name='faq'),
    path('partners/', views.partners, name='partners'),
    path('visit-guide/', views.visit_guide, name='visit_guide'),
]
