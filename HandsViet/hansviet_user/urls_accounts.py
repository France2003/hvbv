from django.urls import path
from django.contrib.auth import views as auth_views
from . import views

app_name = 'auth'

urlpatterns = [
    path('login/', views.login_view, name='login'),
    path('register/', views.register_view, name='register'),
    path('profile/', views.profile_view, name='profile'),
    path('care-management/', views.care_management_view, name='care_management'),
    # Logout allows GET to prevent 405 in static menus
    path('logout/', views.logout_view, name='logout'),
]
