from django.urls import path

from . import views

urlpatterns = [
    path("setup-webhook/", views.webhook, name="setup_webhook"),
    path("webhook/", views.webhook_receiver_view, name="webhook_receiver"),
]
