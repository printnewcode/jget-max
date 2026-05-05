"""
ASGI config for MAX project.

Exposes the ASGI callable as ``application``.
Run with:
    uvicorn MAX.asgi:application --host 0.0.0.0 --port 8000
"""

import os

from django.core.asgi import get_asgi_application

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "MAX.settings")

application = get_asgi_application()
