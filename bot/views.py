import json
import logging
from http import HTTPStatus

from django.conf import settings
from django.http import HttpRequest, HttpResponse, JsonResponse
from django.views.decorators.csrf import csrf_exempt
from maxapi.enums.update import UpdateType
from maxapi.methods.types.getted_updates import process_update_webhook

from bot import create_bot
from .handlers import get_dispatcher

logger = logging.getLogger("bot")

dp = get_dispatcher()

WEBHOOK_UPDATE_TYPES = [
    UpdateType.MESSAGE_CREATED,
    UpdateType.MESSAGE_CALLBACK,
    UpdateType.BOT_STARTED,
]


async def prepare_dispatcher(request_bot) -> None:
    dp._ready = False
    await dp.startup(request_bot)


@csrf_exempt
async def webhook_receiver_view(request: HttpRequest):
    if request.method != "POST":
        logger.info("Webhook endpoint checked with %s", request.method)
        return JsonResponse(
            {
                "ok": True,
                "message": "Webhook endpoint is ready. MAX must send POST here.",
            }
        )

    try:
        raw_body = request.body.decode("utf-8")
        payload = json.loads(raw_body or "{}")
    except json.JSONDecodeError as exc:
        logger.warning("Invalid webhook JSON: %s", exc)
        return JsonResponse({"ok": False, "error": "invalid_json"}, status=400)

    logger.info("Incoming MAX webhook update_type=%s", payload.get("update_type"))

    try:
        request_bot = create_bot()
        try:
            await prepare_dispatcher(request_bot)
            event_object = await process_update_webhook(
                event_json=payload,
                bot=request_bot,
            )

            if event_object is None:
                logger.warning(
                    "Unsupported MAX webhook update_type=%s",
                    payload.get("update_type"),
                )
                return JsonResponse({"ok": True, "handled": False})

            await dp.handle(event_object)
            return JsonResponse({"ok": True})
        finally:
            await request_bot.close_session()
    except Exception as exc:
        logger.exception("Webhook processing failed")
        return JsonResponse({"ok": False, "error": str(exc)}, status=500)


@csrf_exempt
async def webhook(request: HttpRequest):
    try:
        base_url = settings.WEBHOOK_BASE_URL.rstrip("/")
        full_webhook_url = f"{base_url}/bot/webhook/"

        request_bot = create_bot()
        try:
            existing = await request_bot.get_subscriptions()
            removed_urls = []
            for subscription in existing.subscriptions:
                await request_bot.unsubscribe_webhook(subscription.url)
                removed_urls.append(subscription.url)

            result = await request_bot.subscribe_webhook(
                url=full_webhook_url,
                update_types=WEBHOOK_UPDATE_TYPES,
            )
            current = await request_bot.get_subscriptions()
        finally:
            await request_bot.close_session()

        active_subscriptions = [
            {
                "url": subscription.url,
                "update_types": subscription.update_types,
            }
            for subscription in current.subscriptions
        ]

        logger.info("Webhook subscribed: %s", result)
        return JsonResponse(
            {
                "ok": True,
                "registered_url": full_webhook_url,
                "removed_urls": removed_urls,
                "subscribe_result": result.model_dump(),
                "active_subscriptions": active_subscriptions,
            },
            json_dumps_params={"ensure_ascii": False, "indent": 2},
        )
    except Exception as exc:
        logger.exception("Webhook registration failed")
        return HttpResponse(
            f"Webhook registration failed: {exc}",
            status=HTTPStatus.INTERNAL_SERVER_ERROR,
        )
