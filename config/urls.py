from django.contrib import admin
from django.urls import include, path, re_path
from django.views.static import serve
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent

from analysis.views import home_view

urlpatterns = [
    path("", home_view, name="home"),
    path("admin/", admin.site.urls),
    path("api/", include("analysis.urls")),
    re_path(r'^static/(?P<path>.*)$', serve, {'document_root': BASE_DIR / 'analysis' / 'static'}),
]
