"""URL configuration: REST API under /api/, and the React SPA for everything else."""
from django.urls import include, path, re_path

from api.views import SpaView

urlpatterns = [
    path('api/', include('api.urls')),
    # SPA fallback (chat, review, keyboard, … all handled client-side).
    re_path(r'^(?!api/|static/|admin/).*$', SpaView.as_view(), name='spa'),
]
