"""URL configuration: REST API under /api/, and the React SPA for everything else."""
from django.urls import include, path, re_path

from api.views import (
    ManifestView,
    PrivacyView,
    RobotsView,
    ServiceWorkerView,
    SpaView,
)

urlpatterns = [
    path('api/', include('api.urls')),
    # PWA / store assets served from the origin root.
    path('manifest.webmanifest', ManifestView.as_view(), name='manifest'),
    path('manifest.json', ManifestView.as_view()),
    path('sw.js', ServiceWorkerView.as_view(), name='service-worker'),
    path('robots.txt', RobotsView.as_view(), name='robots'),
    path('privacy', PrivacyView.as_view(), name='privacy'),
    path('privacy/', PrivacyView.as_view()),
    # SPA fallback (chat, review, keyboard, … all handled client-side).
    re_path(r'^(?!api/|static/|admin/).*$', SpaView.as_view(), name='spa'),
]
