from django.contrib import admin
from django.http import HttpRequest

from .models import Application, BotConfig, BotSession


@admin.register(BotConfig)
class BotConfigAdmin(admin.ModelAdmin):
    fieldsets = (
        (
            "Стартовое приветствие",
            {"fields": ("greeting_text",)},
        ),
        (
            "Сбор телефона",
            {"fields": ("phone_prompt", "phone_error")},
        ),
        (
            "Сбор ФИО",
            {"fields": ("name_prompt",)},
        ),
        (
            "Подтверждение и редактирование",
            {"fields": ("confirmation_template", "edit_phone_prompt", "edit_name_prompt")},
        ),
        (
            "Завершение",
            {"fields": ("completion_text",)},
        ),
    )

    def has_add_permission(self, request: HttpRequest) -> bool:
        return not BotConfig.objects.exists()

    def has_delete_permission(self, request: HttpRequest, obj=None) -> bool:
        return False

    def has_change_permission(self, request: HttpRequest, obj=None) -> bool:
        return True


@admin.register(BotSession)
class BotSessionAdmin(admin.ModelAdmin):
    list_display = ("user_id", "current_step", "phone", "child_name", "updated_at")
    list_filter = ("current_step",)
    search_fields = ("user_id", "phone", "child_name")
    readonly_fields = ("user_id", "current_step", "phone", "child_name", "updated_at")
    ordering = ("-updated_at",)

    def has_add_permission(self, request: HttpRequest) -> bool:
        return False


@admin.register(Application)
class ApplicationAdmin(admin.ModelAdmin):
    list_display = ("pk", "user_id", "phone", "child_full_name", "status", "created_at")
    list_filter = ("status", "created_at")
    search_fields = ("user_id", "phone", "child_full_name")
    readonly_fields = ("user_id", "phone", "child_full_name", "status", "created_at")
    ordering = ("-created_at",)

    def has_add_permission(self, request: HttpRequest) -> bool:
        return False
