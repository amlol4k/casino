import asyncio
import logging
from aiogram import Bot, Dispatcher
from aiogram.client.default import DefaultBotProperties
from aiogram.enums import ParseMode

from handlers.economy import router as economy_router
from handlers.games import router as games_router
from database.db import init_db

TOKEN = "8615456141:AAE-5BpmVVoXchl5UmONU-_HzwCbyIP2Jwc"

async def main():
    #logging.basicConfig(level=logging.INFO)
    
    await init_db()
    
    bot = Bot(token=TOKEN, default=DefaultBotProperties(parse_mode=ParseMode.HTML))
    dp = Dispatcher()

    # Подключаем оба роутера. Очередность важна: бот будет проверять хэндлеры сверху вниз
    dp.include_router(economy_router)
    dp.include_router(games_router)

    print("=== Бот успешно запущен с играми и экономикой! ===")
    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())