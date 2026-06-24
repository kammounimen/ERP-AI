"""
erp_auth/urls.py — Routeur principal Django
Délègue toutes les routes à l'app authentication
"""

from django.urls import path, include

urlpatterns = [
    path("", include("authentication.urls")),
]
