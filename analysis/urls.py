from django.urls import path

from .views import analysis_detail_view, analysis_submit_view

urlpatterns = [
    path("analyses/", analysis_submit_view, name="analysis-submit"),
    path("analyses/<uuid:analysis_id>/", analysis_detail_view, name="analysis-detail"),
]
