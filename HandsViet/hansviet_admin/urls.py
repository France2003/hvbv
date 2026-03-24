from django.urls import path
from . import views

app_name = "dashboard"

urlpatterns = [
    path("login/", views.admin_login_view, name="login"),
    path("", views.dashboard_home, name="home"),
    path("logout/", views.dashboard_logout, name="logout"),

    # Users
    path("users/", views.user_list, name="user_list"),
    path("users/create/", views.user_create, name="user_create"),
    path("users/<int:pk>/edit/", views.user_edit, name="user_edit"),
    path("users/<int:pk>/delete/", views.user_delete, name="user_delete"),

    # Services & Categories
    path("services/", views.service_list, name="service_list"),
    path("services/create/", views.service_create, name="service_create"),
    path("services/<int:pk>/edit/", views.service_edit, name="service_edit"),
    path("services/<int:pk>/delete/", views.service_delete, name="service_delete"),
    path("videos/", views.video_list, name="video_list"),
    path("videos/create/", views.video_create, name="video_create"),
    path("videos/<int:pk>/edit/", views.video_edit, name="video_edit"),
    path("videos/<int:pk>/delete/", views.video_delete, name="video_delete"),
    path("therapies/", views.therapy_list, name="therapy_list"),
    path("therapies/create/", views.therapy_create, name="therapy_create"),
    path("therapies/<int:pk>/edit/", views.therapy_edit, name="therapy_edit"),
    path("therapies/<int:pk>/delete/", views.therapy_delete, name="therapy_delete"),
    path("bookings/", views.booking_list, name="booking_list"),
    path("bookings/feed/", views.booking_feed, name="booking_feed"),
    path("bookings/<int:pk>/send-confirmation/", views.booking_send_confirmation_email, name="booking_send_confirmation_email"),

    path("categories/", views.category_list, name="category_list"),
    path("categories/create/", views.category_create, name="category_create"),
    path("categories/<int:pk>/edit/", views.category_edit, name="category_edit"),
    path("categories/<int:pk>/delete/", views.category_delete, name="category_delete"),

    # News & news categories
    path("news/", views.news_list, name="news_list"),
    path("news/create/", views.news_create, name="news_create"),
    path("news/<int:pk>/edit/", views.news_edit, name="news_edit"),
    path("news/<int:pk>/delete/", views.news_delete, name="news_delete"),

    path("news/categories/", views.news_category_list, name="news_category_list"),
    path("news/categories/create/", views.news_category_create, name="news_category_create"),
    path("news/categories/<int:pk>/edit/", views.news_category_edit, name="news_category_edit"),
    path("news/categories/<int:pk>/delete/", views.news_category_delete, name="news_category_delete"),
]
