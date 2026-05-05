"""
Business logic for the MAX messenger bot.

All functions are async and can be called from the webhook view.
The module uses the maxapi ``Bot`` and ``Dispatcher`` utilities.
"""

import asyncio
import logging
import re
from typing import Any, Dict, List, Tuple

from maxapi import Bot, Dispatcher, types
# from maxapi.types import InlineKeyboardButton, InlineKeyboardMarkup

from django.conf import settings
from django.utils import timezone

from .models import BotConfig, BotSession, Application

logger = logging.getLogger("bot")

# ---------------------------------------------------------------------------
# Helper utilities
# ---------------------------------------------------------------------------

PHONE_REGEX = re.compile(r"^\+7\d{10}$")


def get_keyboard(edit_phone: bool = False, edit_name: bool = False):
    """Build the confirmation inline keyboard.

    Parameters
    ----------
    edit_phone, edit_name:
        Flags that indicate whether the corresponding edit button should be
        be displayed. In the normal flow both are shown, but after a single
        edit we hide the button that has just been edited so the user can
        continue without redundant options.
    """
    buttons = []
    row = []
    
    if edit_phone:
        row.append({
            "text": "✏️ Редактировать телефон",
            "callback_data": "edit_phone",
        })
    if edit_name:
        row.append({
            "text": "✏️ Редактировать ФИО",
            "callback_data": "edit_name",
        })
    
    if row:
        buttons.append(row)

    # Кнопка подтверждения
    buttons.append([
        {
            "text": "✅ Подтвердить и отправить",
            "callback_data": "confirm",
        }
    ])
    
    return {"inline_keyboard": buttons}


async def send_message(bot: Bot, chat_id: int, text: str, *, reply_markup = None) -> None:
    """Thin wrapper that logs and executes ``Bot.send_message`` asynchronously."""
    logger.debug("Sending message to %s: %s", chat_id, text)
    await bot.send_message(chat_id=chat_id, text=text, reply_markup=reply_markup)


# ---------------------------------------------------------------------------
# Core conversation handlers – pure async functions, no Django request needed
# ---------------------------------------------------------------------------

async def start_handler(bot: Bot, chat_id: int, user_id: int) -> None:
    """Entry point – called when a new chat starts or /start is received.

    It creates (or resets) a BotSession for the user and sends the greeting
    defined in ``BotConfig``.
    """
    config = BotConfig.get_config()
    # Upsert BotSession – ensure a fresh state for each start
    session, _ = BotSession.objects.update_or_create(
        user_id=user_id,
        defaults={"current_step": BotSession.STEP_WAITING_PHONE, "phone": "", "child_name": ""},
    )
    await send_message(bot, chat_id, config.greeting_text)
    await send_message(bot, chat_id, config.phone_prompt)


async def phone_handler(bot: Bot, chat_id: int, user_id: int, message_text: str) -> None:
    """Validate phone number, store it, and ask for child's name."""
    config = BotConfig.get_config()
    if not PHONE_REGEX.match(message_text.strip()):
        await send_message(bot, chat_id, config.phone_error)
        return
    BotSession.objects.filter(user_id=user_id).update(
        phone=message_text.strip(), current_step=BotSession.STEP_WAITING_NAME
    )
    await send_message(bot, chat_id, config.name_prompt)


async def name_handler(bot: Bot, chat_id: int, user_id: int, message_text: str) -> None:
    """Store child's full name and present the confirmation screen."""
    config = BotConfig.get_config()
    BotSession.objects.filter(user_id=user_id).update(
        child_name=message_text.strip(), current_step=BotSession.STEP_CONFIRMING
    )
    session = BotSession.objects.get(user_id=user_id)
    summary = config.confirmation_template.format(phone=session.phone, name=session.child_name)
    keyboard = get_keyboard(edit_phone=True, edit_name=True)
    await send_message(bot, chat_id, summary, reply_markup=keyboard)


async def edit_phone_handler(bot: Bot, chat_id: int, user_id: int) -> None:
    """Prompt user to re‑enter phone number (editing flow)."""
    config = BotConfig.get_config()
    BotSession.objects.filter(user_id=user_id).update(current_step=BotSession.STEP_EDITING_PHONE)
    await send_message(bot, chat_id, config.edit_phone_prompt)


async def edit_name_handler(bot: Bot, chat_id: int, user_id: int) -> None:
    """Prompt user to re‑enter child's full name (editing flow)."""
    config = BotConfig.get_config()
    BotSession.objects.filter(user_id=user_id).update(current_step=BotSession.STEP_EDITING_NAME)
    await send_message(bot, chat_id, config.edit_name_prompt)


async def confirm_handler(bot: Bot, chat_id: int, user_id: int) -> None:
    """Finalize the submission, save to ``Application`` and clear the session."""
    config = BotConfig.get_config()
    session = BotSession.objects.get(user_id=user_id)
    # Persist final record
    Application.objects.create(
        user_id=user_id,
        phone=session.phone,
        child_full_name=session.child_name,
        status=Application.STATUS_SUBMITTED,
        created_at=timezone.now(),
    )
    # Clear the session (so a new start begins fresh)
    BotSession.objects.filter(user_id=user_id).delete()
    await send_message(bot, chat_id, config.completion_text)


# ---------------------------------------------------------------------------
# Inline button dispatcher – called from webhook when ``callback_query`` arrives
# ---------------------------------------------------------------------------

async def callback_query_handler(bot: Bot, chat_id: int, user_id: int, data: str) -> None:
    if data == "edit_phone":
        await edit_phone_handler(bot, chat_id, user_id)
    elif data == "edit_name":
        await edit_name_handler(bot, chat_id, user_id)
    elif data == "confirm":
        await confirm_handler(bot, chat_id, user_id)
    else:
        logger.warning("Unknown callback data received: %s", data)


# ---------------------------------------------------------------------------
# Export command – only admin can trigger via a private chat
# ---------------------------------------------------------------------------

async def export_handler(bot: Bot, chat_id: int, user_id: int) -> None:
    """Export all applications to an XLSX file and send it to the admin.

    Only the user whose ``user_id`` matches ``settings.MAX_ADMIN_ID`` may
    invoke this function.
    """
    if user_id != settings.MAX_ADMIN_ID:
        logger.warning("Unauthorized export attempt by %s", user_id)
        return
    import pandas as pd

    qs = Application.objects.all().values(
        "pk",
        "user_id",
        "phone",
        "child_full_name",
        "status",
        "created_at",
    )
    df = pd.DataFrame.from_records(qs)
    if df.empty:
        await send_message(bot, chat_id, "⚠ Нет заявок для экспорта.")
        return
    # Convert datetime to string for Excel friendliness
    df["created_at"] = df["created_at"].dt.strftime("%Y-%m-%d %H:%M:%S")
    file_path = settings.BASE_DIR / f"applications_{timezone.now().strftime('%Y%m%d_%H%M%S')}.xlsx"
    df.to_excel(file_path, index=False, engine="openpyxl")
    with open(file_path, "rb") as f:
        await bot.send_document(chat_id=chat_id, document=f, caption="📊 Экспорт заявок")
    # Clean up the temporary file
    file_path.unlink(missing_ok=True)
    logger.info("Exported %d applications for admin %s", df.shape[0], user_id)


# ---------------------------------------------------------------------------
# Dispatcher configuration – ties together the above handlers
# ---------------------------------------------------------------------------

def get_dispatcher() -> Dispatcher:
    bot = Bot(token=settings.MAX_BOT_TOKEN)
    dp = Dispatcher()
    dp.bot = bot # Привязываем бота к диспетчеру

    # Команда /start
    @dp.message_created(types.Command("start"))
    async def _(event: types.MessageCreated):
        await start_handler(dp.bot, event.message.chat_id, event.message.from_user.id)

    # Команда /export
    @dp.message_created(types.Command("export"))
    async def _(event: types.MessageCreated):
        await export_handler(dp.bot, event.message.chat_id, event.message.from_user.id)

    # Обычные сообщения (обработка шагов регистрации)
    @dp.message_created()
    async def _(event: types.MessageCreated):
        if event.message.text.startswith("/"):
            return

        user_id = event.message.from_user.id
        session = BotSession.objects.filter(user_id=user_id).first()
        if not session:
            return

        chat_id = event.message.chat_id
        text = event.message.text

        if session.current_step == BotSession.STEP_WAITING_PHONE:
            await phone_handler(dp.bot, chat_id, user_id, text)
        elif session.current_step == BotSession.STEP_WAITING_NAME:
            await name_handler(dp.bot, chat_id, user_id, text)
        elif session.current_step in (BotSession.STEP_EDITING_PHONE, BotSession.STEP_EDITING_NAME):
            if session.current_step == BotSession.STEP_EDITING_PHONE:
                await phone_handler(dp.bot, chat_id, user_id, text)
            else:
                await name_handler(dp.bot, chat_id, user_id, text)

    # ОБРАБОТКА КНОПОК (измените на message_callback)
    @dp.message_callback()
    async def _(event: types.MessageCallback):
        # В этой библиотеке данные кнопки обычно в event.callback_data или event.data
        await callback_query_handler(
            dp.bot, 
            event.message.chat_id, 
            event.from_user.id, 
            event.data # Проверьте это поле в дебаге, если не сработает
        )

    return dp
