from django.http import JsonResponse, HttpRequest
from django.conf import settings
from django.views.decorators.csrf import csrf_exempt
import json
import logging
from .handlers import get_dispatcher

logger = logging.getLogger("bot")

# Инициализируем диспетчер ОДИН РАЗ при запуске приложения
dp = get_dispatcher()

@csrf_exempt
async def webhook(request: HttpRequest):
    try:
        payload = json.loads(request.body.decode("utf-8"))
        
        # В maxapi для обработки словаря из вебхука используем feed_raw_update
        # Передаем бота, привязанного к диспетчеру, и сам payload
        result = await dp.bot.subscribe_webhook(url=f"{settings.WEBHOOK_BASE_URL}")
        print(result)
    except json.JSONDecodeError:
        return JsonResponse({"error": "Invalid JSON"}, status=400)
    except Exception as exc:
        logger.exception("Error processing webhook update: %s", exc)
        # Возвращаем 200, чтобы мессенджер не спамил повторами при ошибках кода
        return JsonResponse({"status": "error", "detail": str(exc)}, status=200)

    return JsonResponse({"status": "ok"})
