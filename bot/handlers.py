import logging
import re
from pathlib import Path

from asgiref.sync import sync_to_async
from django.conf import settings
from django.utils import timezone
from maxapi import Bot, Dispatcher, types
from maxapi.types.attachments.buttons import CallbackButton
from maxapi.types.input_media import InputMedia
from maxapi.utils.inline_keyboard import InlineKeyboardBuilder

from bot import dp
from .models import Application, BotConfig, BotSession

logger = logging.getLogger("bot")

PHONE_REGEX = re.compile(r"^\+7\d{10}$")
_handlers_registered = False
DUPLICATE_ADD_CHILD_PAYLOAD = "duplicate_add_child"
DUPLICATE_EXIT_PAYLOAD = "duplicate_exit"


def get_keyboard(edit_phone: bool = False, edit_name: bool = False):
    builder = InlineKeyboardBuilder()
    edit_buttons = []

    if edit_phone:
        edit_buttons.append(
            CallbackButton(text="Изменить телефон", payload="edit_phone")
        )
    if edit_name:
        edit_buttons.append(CallbackButton(text="Изменить ФИО", payload="edit_name"))

    if edit_buttons:
        builder.row(*edit_buttons)

    builder.row(CallbackButton(text="Подтвердить и отправить", payload="confirm"))
    return builder.as_markup()


def get_duplicate_phone_keyboard():
    builder = InlineKeyboardBuilder()
    builder.row(
        CallbackButton(
            text="Да, добавить ребенка",
            payload=DUPLICATE_ADD_CHILD_PAYLOAD,
        )
    )
    builder.row(
        CallbackButton(
            text="Нет, выйти",
            payload=DUPLICATE_EXIT_PAYLOAD,
        )
    )
    return builder.as_markup()


async def send_message(
    bot: Bot,
    chat_id: int,
    text: str,
    *,
    attachments=None,
) -> None:
    logger.debug("Sending message to %s: %s", chat_id, text)
    await bot.send_message(chat_id=chat_id, text=text, attachments=attachments)


async def get_config() -> BotConfig:
    return await sync_to_async(BotConfig.get_config)()


async def get_session(user_id: int) -> BotSession | None:
    return await sync_to_async(
        lambda: BotSession.objects.filter(user_id=user_id).first()
    )()


async def phone_exists(phone: str) -> bool:
    return await sync_to_async(lambda: Application.objects.filter(phone=phone).exists())()


async def start_handler(bot: Bot, chat_id: int, user_id: int) -> None:
    config = await get_config()
    await sync_to_async(BotSession.objects.update_or_create)(
        user_id=user_id,
        defaults={
            "current_step": BotSession.STEP_WAITING_PHONE,
            "phone": "",
            "child_name": "",
        },
    )
    await send_message(bot, chat_id, config.greeting_text)


async def phone_handler(
    bot: Bot, chat_id: int, user_id: int, message_text: str
) -> None:
    config = await get_config()
    phone = message_text.strip()
    if not PHONE_REGEX.match(phone):
        await send_message(bot, chat_id, config.phone_error)
        return

    if await phone_exists(phone):
        await sync_to_async(
            lambda: BotSession.objects.filter(user_id=user_id).update(phone=phone)
        )()
        await send_message(
            bot,
            chat_id,
            (
                "Этот номер телефона уже есть в базе.\n\n"
                "Хотите добавить еще одного ребенка на этот же номер?"
            ),
            attachments=[get_duplicate_phone_keyboard()],
        )
        return

    await sync_to_async(
        lambda: BotSession.objects.filter(user_id=user_id).update(
            phone=phone,
            current_step=BotSession.STEP_WAITING_NAME,
        )
    )()
    await send_message(bot, chat_id, config.name_prompt)


async def name_handler(
    bot: Bot, chat_id: int, user_id: int, message_text: str
) -> None:
    config = await get_config()
    await sync_to_async(
        lambda: BotSession.objects.filter(user_id=user_id).update(
            child_name=message_text.strip(),
            current_step=BotSession.STEP_CONFIRMING,
        )
    )()
    session = await sync_to_async(BotSession.objects.get)(user_id=user_id)
    summary = config.confirmation_template.format(
        phone=session.phone,
        name=session.child_name,
    )
    await send_message(
        bot,
        chat_id,
        summary,
        attachments=[get_keyboard(edit_phone=True, edit_name=True)],
    )


async def edit_phone_handler(bot: Bot, chat_id: int, user_id: int) -> None:
    config = await get_config()
    await sync_to_async(
        lambda: BotSession.objects.filter(user_id=user_id).update(
            current_step=BotSession.STEP_EDITING_PHONE
        )
    )()
    await send_message(bot, chat_id, config.edit_phone_prompt)


async def edit_name_handler(bot: Bot, chat_id: int, user_id: int) -> None:
    config = await get_config()
    await sync_to_async(
        lambda: BotSession.objects.filter(user_id=user_id).update(
            current_step=BotSession.STEP_EDITING_NAME
        )
    )()
    await send_message(bot, chat_id, config.edit_name_prompt)


async def confirm_handler(bot: Bot, chat_id: int, user_id: int) -> None:
    config = await get_config()
    session = await sync_to_async(BotSession.objects.get)(user_id=user_id)
    await sync_to_async(Application.objects.create)(
        user_id=user_id,
        phone=session.phone,
        child_full_name=session.child_name,
        status=Application.STATUS_SUBMITTED,
        created_at=timezone.now(),
    )
    await sync_to_async(lambda: BotSession.objects.filter(user_id=user_id).delete())()
    await send_message(bot, chat_id, config.completion_text)


async def duplicate_add_child_handler(bot: Bot, chat_id: int, user_id: int) -> None:
    config = await get_config()
    await sync_to_async(
        lambda: BotSession.objects.filter(user_id=user_id).update(
            current_step=BotSession.STEP_WAITING_NAME,
            child_name="",
        )
    )()
    await send_message(bot, chat_id, config.name_prompt)


async def duplicate_exit_handler(bot: Bot, chat_id: int, user_id: int) -> None:
    await sync_to_async(lambda: BotSession.objects.filter(user_id=user_id).delete())()
    await send_message(
        bot,
        chat_id,
        "Хорошо, заявку не добавляю. Чтобы начать заново, отправьте /start.",
    )


async def callback_query_handler(
    bot: Bot, chat_id: int, user_id: int, payload: str | None
) -> None:
    if payload == "edit_phone":
        await edit_phone_handler(bot, chat_id, user_id)
    elif payload == "edit_name":
        await edit_name_handler(bot, chat_id, user_id)
    elif payload == "confirm":
        await confirm_handler(bot, chat_id, user_id)
    elif payload == DUPLICATE_ADD_CHILD_PAYLOAD:
        await duplicate_add_child_handler(bot, chat_id, user_id)
    elif payload == DUPLICATE_EXIT_PAYLOAD:
        await duplicate_exit_handler(bot, chat_id, user_id)
    else:
        logger.warning("Unknown callback payload received: %s", payload)


async def export_handler(bot: Bot, chat_id: int, user_id: int) -> None:
    if user_id != settings.MAX_ADMIN_ID:
        logger.warning("Unauthorized export attempt by %s", user_id)
        return

    await send_message(bot, chat_id, "Формирую файл с заявками...")

    import pandas as pd

    rows = await sync_to_async(
        lambda: list(
            Application.objects.all().values(
                "phone",
                "child_full_name",
            )
        )
    )()
    df = pd.DataFrame.from_records(rows)
    if df.empty:
        await send_message(bot, chat_id, "Нет заявок для экспорта.")
        return

    df = df.rename(
        columns={
            "child_full_name": "ФИО ребенка",
            "phone": "Телефон",
        }
    )[["ФИО ребенка", "Телефон"]]
    file_path: Path = (
        settings.BASE_DIR
        / f"applications_{timezone.now().strftime('%Y%m%d_%H%M%S')}.xlsx"
    )
    await sync_to_async(df.to_excel)(file_path, index=False, engine="openpyxl")
    try:
        await bot.send_message(
            chat_id=chat_id,
            text="Экспорт заявок",
            attachments=[InputMedia(str(file_path))],
        )
    finally:
        file_path.unlink(missing_ok=True)

    logger.info("Exported %d applications for admin %s", df.shape[0], user_id)


def _message_text(event: types.MessageCreated) -> str:
    body = event.message.body
    return body.text if body and body.text else ""


def _message_chat_id(event: types.MessageCreated) -> int | None:
    return event.message.recipient.chat_id


def _message_user_id(event: types.MessageCreated) -> int | None:
    return event.message.sender.user_id if event.message.sender else None


def get_dispatcher() -> Dispatcher:
    global _handlers_registered

    if _handlers_registered:
        return dp

    @dp.bot_started()
    async def _(event: types.BotStarted):
        await start_handler(dp.bot, event.chat_id, event.user.user_id)

    @dp.message_created(types.Command("start"))
    async def _(event: types.MessageCreated):
        chat_id = _message_chat_id(event)
        user_id = _message_user_id(event)
        if chat_id is None or user_id is None:
            logger.warning("Cannot handle /start without chat_id or user_id")
            return
        await start_handler(dp.bot, chat_id, user_id)

    @dp.message_created(types.Command("export"))
    async def _(event: types.MessageCreated):
        chat_id = _message_chat_id(event)
        user_id = _message_user_id(event)
        if chat_id is None or user_id is None:
            logger.warning("Cannot handle /export without chat_id or user_id")
            return
        await export_handler(dp.bot, chat_id, user_id)

    @dp.message_created()
    async def _(event: types.MessageCreated):
        text = _message_text(event)
        if text.startswith("/"):
            return

        chat_id = _message_chat_id(event)
        user_id = _message_user_id(event)
        if chat_id is None or user_id is None:
            logger.warning("Cannot handle message without chat_id or user_id")
            return

        session = await get_session(user_id)
        if not session:
            return

        if session.current_step == BotSession.STEP_WAITING_PHONE:
            await phone_handler(dp.bot, chat_id, user_id, text)
        elif session.current_step == BotSession.STEP_WAITING_NAME:
            await name_handler(dp.bot, chat_id, user_id, text)
        elif session.current_step == BotSession.STEP_EDITING_PHONE:
            await phone_handler(dp.bot, chat_id, user_id, text)
        elif session.current_step == BotSession.STEP_EDITING_NAME:
            await name_handler(dp.bot, chat_id, user_id, text)

    @dp.message_callback()
    async def _(event: types.MessageCallback):
        if event.message is None:
            logger.warning("Cannot handle callback without source message")
            return

        chat_id = event.message.recipient.chat_id
        if chat_id is None:
            logger.warning("Cannot handle callback without chat_id")
            return

        await callback_query_handler(
            dp.bot,
            chat_id,
            event.callback.user.user_id,
            event.callback.payload,
        )

    _handlers_registered = True
    return dp
