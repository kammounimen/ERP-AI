"""
authentication/urls.py — Toutes les routes de l'application
Remplace les @app.route(...) de Flask
"""

from django.urls import path
from . import views

urlpatterns = [
    # ── Pages HTML statiques ──────────────────────────────────────────────────
    path("",                                views.index,           name="index"),
    path("licences",                        views.licences_page,   name="licences-page"),
    path("users",                           views.users_page,      name="users-page"),

    # ── Auth ──────────────────────────────────────────────────────────────────
    path("api/auth/login",                  views.login,           name="login"),
    path("api/auth/logout",                 views.logout,          name="logout"),
    path("api/auth/me",                     views.me,              name="me"),
    path("api/auth/erp-token", views.erp_token, name="erp-token"),

    # ── System ────────────────────────────────────────────────────────────────
    path("api/system/status",               views.system_status,   name="system-status"),
    path("api/system/control",              views.system_control,  name="system-control"),
    path("api/system/logs",                 views.get_logs,        name="system-logs"),

    # ── Stats ─────────────────────────────────────────────────────────────────
    path("api/stats",                       views.stats,           name="stats"),

    # ── Licences ──────────────────────────────────────────────────────────────
    path("api/licences",                    views.licences,           name="licences"),
    path("api/licences/<int:id>",           views.licence_detail,     name="licence-detail"),
    path("api/licences/<int:id>/renew",     views.renew_licence,      name="licence-renew"),
    path("api/licences/<int:id>/renewals",  views.get_renewals,       name="licence-renewals"),

    # ── Users ─────────────────────────────────────────────────────────────────
    path("api/users",                       views.users,           name="users"),
    path("api/users/<int:user_id>",         views.user_detail,     name="user-detail"),

    # ── Utilitaires ───────────────────────────────────────────────────────────
    path("api/verify-token",                views.verify_token,    name="verify-token"),
    path("api/debug/company-check",         views.company_check,   name="company-check"),
    path("ping",                            views.ping,            name="ping"),
]
