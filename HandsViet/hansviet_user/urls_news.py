from django.urls import path
from . import views

app_name = 'news'

urlpatterns = [
    # News listing homepage
    path('', views.news_list, name='news_list'),
    # News by category
    path('category/<slug:category_slug>/', views.news_category, name='news_category'),
    # Individual article detail
    path('<slug:slug>/', views.news_detail, name='news_detail'),
]
