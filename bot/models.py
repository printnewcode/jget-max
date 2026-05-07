from django.db import models
from django.core.exceptions import ValidationError


class BotConfig(models.Model):
    greeting_text = models.TextField(
        verbose_name="Приветственное сообщение",
        default=(
            "👋 Добро пожаловать!\n\n"
            "Я помогу вам оставить заявку. Давайте начнём.\n\n"
            "📞 Пожалуйста, введите ваш номер телефона в формате +7XXXXXXXXXX:"
        ),
    )
    phone_prompt = models.TextField(
        verbose_name="Запрос номера телефона",
        default="📞 Введите номер телефона в формате +7XXXXXXXXXX:",
    )
    phone_error = models.TextField(
        verbose_name="Ошибка валидации телефона",
        default=(
            "❌ Неверный формат номера телефона.\n\n"
            "Введите номер в формате +7XXXXXXXXXX (знак + и 11 цифр):"
        ),
    )
    name_prompt = models.TextField(
        verbose_name="Запрос ФИО ребёнка",
        default="👤 Введите ФИО ребёнка полностью (Фамилия Имя Отчество):",
    )
    confirmation_template = models.TextField(
        verbose_name="Шаблон подтверждения (используйте {phone} и {name})",
        default=(
            "📋 Проверьте введённые данные:\n\n"
            "📞 Телефон: {phone}\n"
            "👤 ФИО ребёнка: {name}\n\n"
            "Всё верно?"
        ),
    )
    completion_text = models.TextField(
        verbose_name="Сообщение после отправки заявки",
        default=(
            "✅ Ваша заявка успешно отправлена!\n\n"
            "Мы свяжемся с вами в ближайшее время. Спасибо!"
        ),
    )
    edit_phone_prompt = models.TextField(
        verbose_name="Запрос нового номера телефона (редактирование)",
        default="✏️ Введите новый номер телефона в формате +7XXXXXXXXXX:",
    )
    edit_name_prompt = models.TextField(
        verbose_name="Запрос нового ФИО (редактирование)",
        default="✏️ Введите новое ФИО ребёнка:",
    )

    class Meta:
        verbose_name = "Настройки бота"
        verbose_name_plural = "Настройки бота"

    def __str__(self) -> str:
        return "Настройки бота"

    def clean(self) -> None:
        if not self.pk and BotConfig.objects.exists():
            raise ValidationError(
                "Может существовать только одна запись настроек бота."
            )

    def save(self, *args, **kwargs) -> None:
        self.full_clean()
        super().save(*args, **kwargs)

    @classmethod
    def get_config(cls) -> "BotConfig":
        obj, _ = cls.objects.get_or_create(pk=1)
        return obj


class BotSession(models.Model):
    STEP_WAITING_PHONE = "waiting_phone"
    STEP_WAITING_NAME = "waiting_name"
    STEP_CONFIRMING = "confirming"
    STEP_EDITING_PHONE = "editing_phone"
    STEP_EDITING_NAME = "editing_name"
    STEP_DONE = "done"

    STEP_CHOICES = [
        (STEP_WAITING_PHONE, "Ожидание телефона"),
        (STEP_WAITING_NAME, "Ожидание имени"),
        (STEP_CONFIRMING, "Подтверждение"),
        (STEP_EDITING_PHONE, "Редактирование телефона"),
        (STEP_EDITING_NAME, "Редактирование имени"),
        (STEP_DONE, "Завершено"),
    ]

    user_id = models.BigIntegerField(
        unique=True,
        verbose_name="ID пользователя MAX",
        db_index=True,
    )
    current_step = models.CharField(
        max_length=32,
        choices=STEP_CHOICES,
        default=STEP_WAITING_PHONE,
        verbose_name="Текущий шаг",
    )
    phone = models.CharField(
        max_length=16,
        blank=True,
        default="",
        verbose_name="Телефон",
    )
    child_name = models.CharField(
        max_length=255,
        blank=True,
        default="",
        verbose_name="ФИО ребёнка",
    )
    updated_at = models.DateTimeField(auto_now=True, verbose_name="Обновлено")

    class Meta:
        verbose_name = "Сессия бота"
        verbose_name_plural = "Сессии бота"

    def __str__(self) -> str:
        return f"Сессия пользователя {self.user_id} [{self.current_step}]"


class Application(models.Model):
    STATUS_SUBMITTED = "submitted"
    STATUS_CHOICES = [
        (STATUS_SUBMITTED, "Отправлена"),
    ]

    user_id = models.BigIntegerField(
        verbose_name="ID пользователя MAX",
        db_index=True,
    )
    phone = models.CharField(max_length=16, verbose_name="Телефон")
    child_full_name = models.CharField(max_length=255, verbose_name="ФИО ребёнка")
    created_at = models.DateTimeField(auto_now_add=True, verbose_name="Дата подачи")
    status = models.CharField(
        max_length=16,
        choices=STATUS_CHOICES,
        default=STATUS_SUBMITTED,
        verbose_name="Статус",
    )

    class Meta:
        verbose_name = "Заявка"
        verbose_name_plural = "Заявки"
        ordering = ["-created_at"]

    def __str__(self) -> str:
        return f"Заявка #{self.pk} | {self.phone} | {self.child_full_name}"
