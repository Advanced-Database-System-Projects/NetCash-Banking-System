"""
URL configuration for Bank_System project.

The `urlpatterns` list routes URLs to views. For more information please see:
    https://docs.djangoproject.com/en/6.1/topics/http/urls/
Examples:
Function views
    1. Add an import:  from my_app import views
    2. Add a URL to urlpatterns:  path('', views.home, name='home')
Class-based views
    1. Add an import:  from other_app.views import Home
    2. Add a URL to urlpatterns:  path('', Home.as_view(), name='home')
Including another URLconf
    1. Import the include() function: from django.urls import include, path
    2. Add a URL to urlpatterns:  path('blog/', include('blog.urls'))
"""
from django.contrib import admin

admin.site.site_header = "NetCash Administration"
admin.site.site_title = "NetCash Admin"
admin.site.index_title = "NetCash Management"
from django.urls import path, include
from SysDataBase import views
from django.contrib.auth import views as auth_views
from django.views.generic import TemplateView
from rest_framework_simplejwt.views import ( TokenObtainPairView, TokenRefreshView, )

urlpatterns = [
    path('admin/', admin.site.urls),
    path('', include('SysDataBase.urls')),
    path("login/", views.user_login, name="user_login"),
    path('logout/', auth_views.LogoutView.as_view(), name='logout'),
    path("offline/",
    TemplateView.as_view(template_name="offline.html"),
    name="offline"),
    path("service-worker.js",
    TemplateView.as_view(template_name="service-worker.js",content_type="application/javascript"),
    name="service_worker"), path('api/token/', TokenObtainPairView.as_view(), name='api_token_obtain_pair'),
    path('api/token/refresh/', TokenRefreshView.as_view(), name='api_token_refresh'),
    path('api-auth/', include('rest_framework.urls')),
    path('api/', include('SysDataBase.api_urls')),
]
