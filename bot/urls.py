"""
URL configuration for the ``bot`` app.
"""

from django.urls import path
from . import views

urlpatterns = [
    path("", views.webhook, name="max_webhook"),  # POST /bot/ receives webhook
]
