"""
authentication/decorators.py
Remplace les décorateurs Flask : login_required, admin_required
"""

from django.http import JsonResponse
from functools import wraps


def login_required(f):
    """
    Remplace : @login_required de Flask
    Vérifie que user_id est bien dans la session Django.
    """
    @wraps(f)
    def wrapper(request, *args, **kwargs):
        if not request.session.get("user_id"):
            return JsonResponse(
                {"success": False, "error": "Non authentifié"},
                status=401
            )
        return f(request, *args, **kwargs)
    return wrapper


def admin_required(f):
    """
    Vérifie que l'utilisateur connecté a le rôle 'admin'.
    À utiliser après @login_required.
    """
    @wraps(f)
    def wrapper(request, *args, **kwargs):
        if request.session.get("role") != "admin":
            return JsonResponse(
                {"success": False, "error": "Droits insuffisants"},
                status=403
            )
        return f(request, *args, **kwargs)
    return wrapper
