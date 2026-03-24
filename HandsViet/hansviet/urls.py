from django.contrib import admin
from django.urls import path, include
from django.conf import settings
from django.conf.urls.static import static

urlpatterns = [
    path('admin/', admin.site.urls),
    path('i18n/', include('django.conf.urls.i18n')),

    path('', include('hansviet_user.urls_pages')),
    path('news/', include('hansviet_user.urls_news')),
    path('services/', include('hansviet_user.urls_services')),
    path('therapies/', include('hansviet_user.urls_therapies')),
    path('rehab/', include('hansviet_user.urls_rehab')),
    # Auth routes are namespaced to avoid clashes
    path('auth/', include(('hansviet_user.urls_accounts', 'auth'), namespace='auth')),
    # Custom admin dashboard
    path('handsviet_admin/', include(('hansviet_admin.urls', 'dashboard'), namespace='dashboard')),
] + static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)
