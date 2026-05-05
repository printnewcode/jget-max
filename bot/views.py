from django.http import JsonResponse, HttpRequest
from django.views.decorators.csrf import csrf_exempt
import json
import logging
from .handlers import get_dispatcher

logger = logging.getLogger("bot")

# Инициализируем диспетчер ОДИН РАЗ при запуске приложения
dp = get_dispatcher()

@csrf_exempt
async def webhook(request: HttpRequest):
    if request.method != "POST":
        # Если вы видите это в браузере — это нормально. 
        # Если бот присылает GET — проверьте настройки URL в панели MAX (слэш в конце!)
        return JsonResponse({"error": "Only POST allowed"}, status=405)

    try:
        payload = json.loads(request.body.decode("utf-8"))
        
        # В maxapi для обработки словаря из вебхука используем feed_raw_update
        # Передаем бота, привязанного к диспетчеру, и сам payload
        await dp.feed_raw_update(dp.bot, payload)
        
    except json.JSONDecodeError:
        return JsonResponse({"error": "Invalid JSON"}, status=400)
    except Exception as exc:
        logger.exception("Error processing webhook update: %s", exc)
        # Возвращаем 200, чтобы мессенджер не спамил повторами при ошибках кода
        return JsonResponse({"status": "error", "detail": str(exc)}, status=200)

    return JsonResponse({"status": "ok"})
