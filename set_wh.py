import asyncio
from maxapi import Bot


async def set_webhook():
    bot = Bot(token="f9LHodD0cOK4m-CXdXPxdHAKn5NQVewD_8V0Hva9BiH6FVQZQLCeoQoN_gPdKi2mWUmEmdyPpeDn8Z1vKYCL")
    # ОБЯЗАТЕЛЬНО: https и слэш в конце
    url = "https://5kdqel-188-225-126-34.ru.tuna.am/" 
    # await bot.unsubscribe_webhook() # Сначала удаляем старый
    result = await bot.subscribe_webhook(url=url)
    print(f"Результат: {result}")

asyncio.run(set_webhook())
