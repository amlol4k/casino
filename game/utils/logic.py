# Здесь будут импорты функций из базы данных (get_user_rank, get_user_vip и т.д.)
# from database.db import get_user_data

async def get_tax_percent(user_id: int) -> float:
    # 1. Получаем данные (заглушка, здесь будет вызов из БД)
    # user = await get_user_data(user_id)
    
    # 2. Логика налога
    # if user['vip_status'] in ['vip_m', 'vip_l', 'vip2_m', 'vip2_l']: return 0.03
    # ranks_tax = {0: 0.07, 1: 0.06, 2: 0.05}
    # return ranks_tax.get(user['rank'], 0.07)
    
    # Пока для теста вернем базу
    return 0.07

async def get_cashback_percent(user_id: int) -> float:
    # Логика кэшбэка
    # if user['vip_status'] == 'vip2_l': return 0.60
    # ... и так далее
    return 0.25