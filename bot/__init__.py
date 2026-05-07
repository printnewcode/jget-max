from django.conf import settings
from maxapi import Bot, Dispatcher


bot = Bot(token=settings.MAX_BOT_TOKEN, auto_requests=False)
dp = Dispatcher()
dp.bot = bot


def create_bot() -> Bot:
    return Bot(token=settings.MAX_BOT_TOKEN, auto_requests=False)
