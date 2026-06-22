import asyncio
from aiogram import Router, html, F
from aiogram.filters import Command, CommandObject
from aiogram.types import Message, InlineKeyboardButton, CallbackQuery
from aiogram.utils.keyboard import InlineKeyboardBuilder
from aiogram.fsm.context import FSMContext
from database.db import (
    register_user, get_balance, set_user_vip, update_balance, 
    get_user_rates_data, get_last_bets, add_bet_to_history
)

router = Router()
MAX_BET = 1000000

# Переписанная под aiogram 3.x клавиатура с историей
def get_game_keyboard(last_bets: list):
    builder = InlineKeyboardBuilder()
    
    # Ряд 1: Быстрые номиналы
    builder.add(
        InlineKeyboardButton(text="100", callback_data="bet_100"),
        InlineKeyboardButton(text="1,000", callback_data="bet_1000"),
        InlineKeyboardButton(text="10,000", callback_data="bet_10000")
    )
    builder.adjust(3)
    
    # Ряд 2: Кнопки истории (если они есть в базе)
    if last_bets:
        history_buttons = [
            InlineKeyboardButton(text=f"⏱ {b:,}", callback_data=f"bet_{b}") 
            for b in last_bets
        ]
        builder.row(*history_buttons)
        
    return builder.as_markup()



async def calculate_game_rates(user_id: int):
    # Достаем только статус VIP (ранги убрали)
    from database.db import get_user_rates_data
    _, vip_status = await get_user_rates_data(user_id) # Первую переменную (ранг) игнорируем
    
    if vip_status is None:
        vip_status = "none"

    # Настройки под каждый статус
    if vip_status == "vip_plus":
        return {
            "tax": 0.01,          # 1% налог на выигрыш
            "cashback": 0.60,     # 60% кэшбэк
            "max_bet": 999999999, # Безлимит
            "pay_tax": 0.06,      # 6% комиссия на перевод
            "pay_limit": 7        # 7 переводов в день
        }
    elif vip_status == "vip":
        return {
            "tax": 0.03,          # 3% налог на выигрыш
            "cashback": 0.45,     # 45% кэшбэк
            "max_bet": 999999999, # Безлимит
            "pay_tax": 0.07,      # 7% комиссия на перевод
            "pay_limit": 5        # 5 переводов в день
        }
    else: # Обычный игрок ("none")
        return {
            "tax": 0.07,          # 7% налог на выигрыш
            "cashback": 0.25,     # 25% кэшбэк
            "max_bet": MAX_BET,   # 1,000,000
            "pay_tax": 0.09,      # 9% комиссия на перевод
            "pay_limit": 3        # 3 перевода в день
        }   
# Обновленный движок с системой Винстриков!
async def play_slots(message: Message, user_id: int, bet: int, user_mention: str, state: FSMContext):
    balance = await get_balance(user_id)
    
    # --- ВОТ ОНИ, ИСПРАВЛЕННЫЕ 4 СТРОЧКИ ---
    rates = await calculate_game_rates(user_id)
    tax = rates["tax"]
    cashback_rate = rates["cashback"]
    user_max_bet = rates["max_bet"]
    # ---------------------------------------

    last_bets = await get_last_bets(user_id)
    kb = get_game_keyboard(last_bets)

    # ... весь остальной код функции ниже оставляй без изменений!

    if bet <= 0:
        await message.answer("❌ Ставка должна быть больше нуля!", reply_markup=kb)
        return
    if bet > user_max_bet:
        await message.answer(f"❌ Максимальная ставка для твоего ранга — {html.code(f'{user_max_bet:,}')} монет!", reply_markup=kb)
        return
    if bet > balance:
        await message.answer(f"❌ Недостаточно монет! Твой баланс: {html.code(f'{balance:,}')}", reply_markup=kb)
        return

    # === БЛОК ПОЛНОЙ ОЧИСТКИ ===
    data = await state.get_data()
    old_dice_id = data.get("last_dice_msg_id")
    old_text_id = data.get("last_game_msg_id")
    
    # Достаем текущий винстрик (если его нет в памяти — будет 0)
    current_streak = data.get("win_streak", 0)
    
    if old_dice_id:
        try: await message.chat.delete_message(old_dice_id)
        except Exception: pass
    if old_text_id:
        try: await message.chat.delete_message(old_text_id)
        except Exception: pass  

    # Списываем баланс и пишем в историю
    await add_bet_to_history(user_id, bet)
    await update_balance(user_id, -bet)

    # Крутим
    dice_msg = await message.answer_dice(emoji="🎰")
    await state.update_data(last_dice_msg_id=dice_msg.message_id)
    
    await asyncio.sleep(2.2)

    # Раскодировка дайса
    val = dice_msg.dice.value - 1
    reel1 = val % 4          
    reel2 = (val // 4) % 4   
    reel3 = val // 16        

    updated_bets = await get_last_bets(user_id)
    updated_kb = get_game_keyboard(updated_bets)

    result_msg = None

    # Расчет бонусного множителя за серию побед (+5% за каждый шаг стрика)
    # Максимум ограничим +50% (10 побед подряд), чтобы экономика не сломалась
    streak_bonus = min(current_streak * 0.05, 0.50) 

    # 1. СУПЕР-ДЖЕКПОТ (777)
    if reel1 == 3 and reel2 == 3 and reel3 == 3:
        current_streak += 1  # Продлеваем стрик
        
        base_mult = 7.0 + streak_bonus
        raw_win = bet * base_mult
        win_amount = int(raw_win * (1 - tax))
        await update_balance(user_id, win_amount)
        
        streak_text = f"\n🔥 Серия побед: {html.bold(current_streak)} (Бонус к множителю: +{int(streak_bonus*100)}%)" if current_streak > 1 else ""
        result_msg = await message.answer(
            f"🔥 {user_mention}, {html.bold('777 ДЖЕКПОТ!!!')}\n"
            f"Множитель: {base_mult:.2f}x\n"
            f"Выигрыш (налог {int(tax*100)}%): {html.code(f'+{win_amount:,}')} 💵{streak_text}",
            reply_markup=updated_kb
        )

    # 2. ОБЫЧНЫЙ ДЖЕКПОТ (3 в ряд)
    elif reel1 == reel2 == reel3:
        current_streak += 1  # Продлеваем стрик
        
        base_mult = 3.0 + streak_bonus  # Поднял базовый с 2.0 до 3.0, чтобы было сочнее!
        raw_win = bet * base_mult
        win_amount = int(raw_win * (1 - tax))
        await update_balance(user_id, win_amount)
        
        streak_text = f"\n🔥 Серия побед: {html.bold(current_streak)} (Бонус к множителю: +{int(streak_bonus*100)}%)" if current_streak > 1 else ""
        result_msg = await message.answer(
            f"🎉 {user_mention}, {html.bold('ВЫИГРЫШ!')} (Три в ряд)\n"
            f"Множитель: {base_mult:.2f}x\n"
            f"Получено (налог {int(tax*100)}%): {html.code(f'+{win_amount:,}')} 💵{streak_text}",
            reply_markup=updated_kb
        )

    # 3. МЯГКИЙ ВЫИГРЫШ (2 в ряд)
    elif reel1 == reel2 or reel2 == reel3 or reel1 == reel3:
        current_streak += 1  # Продлеваем стрик
        
        base_mult = 1.5 + streak_bonus  # Поднял базовый с 1.2 до 1.5! Теперь 100 монет принесут 150+баланс
        raw_win = bet * base_mult
        win_amount = int(raw_win * (1 - tax))
        await update_balance(user_id, win_amount)
        
        streak_text = f"\n🔥 Серия побед: {html.bold(current_streak)} (Бонус к множителю: +{int(streak_bonus*100)}%)" if current_streak > 1 else ""
        result_msg = await message.answer(
            f"✨ {user_mention}, {html.bold('НЕПЛОХО!')} (Два символа)\n"
            f"Множитель: {base_mult:.2f}x\n"
            f"Выигрыш (налог {int(tax*100)}%): {html.code(f'+{win_amount:,}')} 💵{streak_text}",
            reply_markup=updated_kb
        )

    # 4. ПОЛНЫЙ ПРОИГРЫШ
    else:
        # Проиграл — стрик сгорает в ноль
        current_streak = 0 
        
        cashback = int(bet * cashback_rate)
        await update_balance(user_id, cashback)
        result_msg = await message.answer(
            f"😢 {user_mention}, {html.bold('ПРОИГРЫШ')}\n"
            f"Серия побед сброшена! 💨\n"
            f"Потеряно: {html.code(f'-{bet - cashback:,}')} 💵\n"
            f"Вернулся моментальный кэшбэк ({int(cashback_rate*100)}%): {html.code(f'+{cashback:,}')}",
            reply_markup=updated_kb
        )

    # Сохраняем и ID сообщения, и ОБНОВЛЕННЫЙ винстрик в FSM
    await state.update_data(
        last_game_msg_id=result_msg.message_id,
        win_streak=current_streak
    )

# Обработчик текста (/slots)
@router.message(Command("slots", "slot"))
async def cmd_slots(message: Message, command: CommandObject, state: FSMContext):
    user_id = message.from_user.id
    user_mention = message.from_user.mention_html(message.from_user.first_name)
    username = message.from_user.username or message.from_user.first_name

    await register_user(user_id, username)

    if not command.args:
        last_bets = await get_last_bets(user_id)
        kb = get_game_keyboard(last_bets)
        
        # Если юзер просто вызвал меню заново, тоже удалим старое окно игры, чтобы не плодить копии
        data = await state.get_data()
        old_msg_id = data.get("last_game_msg_id")
        if old_msg_id:
            try:
                await message.chat.delete_message(old_msg_id)
            except Exception:
                pass

        menu_msg = await message.reply(
            f"❌ Напиши ставку! Пример: /slots 100 (Макс: {MAX_BET:,})\n"
            f"Или выбери быструю ставку ниже 👇",
            reply_markup=kb
        )
        await state.update_data(last_game_msg_id=menu_msg.message_id)
        return

    try:
        bet = int(command.args)
    except ValueError:
        last_bets = await get_last_bets(user_id)
        await message.reply("❌ Ставка должна быть чистым числом!", reply_markup=get_game_keyboard(last_bets))
        return

    # Удаляем само текстовое сообщение пользователя с командой /slots 100, чтобы в чате была идеальная чистота
    try:
        await message.delete()
    except Exception:
        pass

    await play_slots(message, user_id, bet, user_mention, state)


# Обработчик нажатия инлайн-кнопок
@router.callback_query(F.data.startswith("bet_"))
async def callback_bet_slots(callback: CallbackQuery, state: FSMContext):
    user_id = callback.from_user.id
    user_mention = callback.from_user.mention_html(callback.from_user.first_name)
    username = callback.from_user.username or callback.from_user.first_name

    await register_user(user_id, username)

    try:
        bet = int(callback.data.split("_")[1])
    except (ValueError, IndexError):
        await callback.answer("❌ Ошибка ставки!", show_alert=True)
        return

    await callback.answer("🎰 Ставка принята!")
    # Передаем callback.message и состояние state в движок
    await play_slots(callback.message, user_id, bet, user_mention, state)




# Переписанное меню доната
@router.message(Command("donate", "shop"))
async def cmd_donate(message: Message):
    builder = InlineKeyboardBuilder()
    
    # Кнопки для обычного VIP
    builder.add(
        InlineKeyboardButton(text="VIP на 7 дней [500k 💵]", callback_data="buy_coin_vip_7"),
        InlineKeyboardButton(text="VIP на 30 дней [70 ⭐️]", callback_data="buy_stars_vip_30"),
        InlineKeyboardButton(text="VIP Навсегда [1,220 ⭐️]", callback_data="buy_stars_vip_0")
    )
    # Кнопки для эксклюзивного VIP++
    builder.add(
        InlineKeyboardButton(text="VIP++ на 30 дней [150 ⭐️]", callback_data="buy_stars_vipplus_30"),
        InlineKeyboardButton(text="VIP++ Навсегда [1,550 ⭐️]", callback_data="buy_stars_vipplus_0")
    )
    builder.adjust(1) 

    await message.answer(
        f"🛒 <b>МАГАЗИН ПРИВИЛЕГИЙ</b>\n"
        f"─────────────────────\n"
        f"👑 <b>VIP Статус:</b>\n"
        f" ├ Налог на игры: <b>3%</b> | Кэшбэк: <b>45%</b>\n"
        f" └ Переводы: <b>5 в день</b> (Комиссия 7%)\n"
        f" 💵 <i>Цены: 500k монет (7 дн.)</i>\n"
        f" ⭐️ <i>Цены: 70 ⭐️ (30 дн.)"
        f" ⭐️ 1,220 ⭐️ (Навсегда)</i>\n\n"
        f"👑💎 <b>VIP++ Статус (ЭКСКЛЮЗИВ):</b>\n"
        f" ├ Налог на игры: <b>1%</b> | Кэшбэк: <b>60%</b>\n"
        f" └ Переводы: <b>7 в день</b> (Комиссия 6%)\n"
        f" ⭐️ <i>Цены: 150 ⭐️ (30 дн.)"
        f"⭐️ 1,550 ⭐️ (Навсегда)</i>\n"
        f"─────────────────────\n"
        f"👇 Выберите интересующий тариф:",
        reply_markup=builder.as_markup()
    )   



@router.callback_query(F.data == "buy_coin_vip_7")
async def callback_buy_coin_vip(callback: CallbackQuery):
    user_id = callback.from_user.id
    balance = await get_balance(user_id)
    cost = 500000

    if balance < cost:
        await callback.answer(
            f"❌ Недостаточно монет! На балансе: {balance:,}, а нужно {cost:,}", 
            show_alert=True
        )
        return

    # Списываем 500k и даем статус на 7 дней
    await update_balance(user_id, -cost)
    await set_user_vip(user_id, "vip", days=7)

    await callback.message.edit_text(
        f"🎉 <b>VIP АКТИВИРОВАН!</b> 🎉\n\n"
        f"👤 Игрок: {callback.from_user.mention_html()}\n"
        f"👑 Срок действия: <b>7 дней</b>\n"
        f"💰 Списание: <code>-{cost:,}</code> монет.\n\n"
        f"Лимиты и бонусы уже обновлены в твоем <code>/profile</code>!"
    )
    await callback.answer("🔥 Успешно куплено!")

from aiogram.types import LabeledPrice, PreCheckoutQuery

@router.callback_query(F.data.startswith("buy_stars_"))
async def callback_buy_stars_invoice(callback: CallbackQuery):
    _, _, choice, days_str = callback.data.split("_")
    days = int(days_str)

    # Настраиваем конфигурацию чеков под твои цены
    config = {
        "vip": {
            30: {"title": "VIP на 30 дней", "stars": 70, "status": "vip"},
            0: {"title": "VIP Навсегда", "stars": 1220, "status": "vip"}
        },
        "vipplus": {
            30: {"title": "VIP++ на 30 дней", "stars": 150, "status": "vip_plus"},
            0: {"title": "VIP++ Навсегда", "stars": 1550, "status": "vip_plus"}
        }
    }

    tariff = config.get(choice, {}).get(days)
    if not tariff:
        await callback.answer("❌ Тариф не найден!", show_alert=True)
        return

    # Payload, который бот получит ПОСЛЕ успешной оплаты (чтобы понять, кому и что выдать)
    payload = f"set_vip_{tariff['status']}_{days}"

    # Выставляем счет в Telegram Stars
    await callback.message.answer_invoice(
        title=tariff["title"],
        description=f"Покупка премиум-статуса. Активация происходит автоматически.",
        prices=[LabeledPrice(label="XTR", amount=tariff["stars"])],
        provider_token="", # Для Telegram Stars токен провайдера ВСЕГДА пустой!
        currency="XTR",    # Валюта Telegram Stars
        payload=payload
    )
    await callback.answer()

# Обязательный шаг 1: подтверждение от бота, что платеж принят (вызывается в момент нажатия «Оплатить»)
@router.pre_checkout_query()
async def process_pre_checkout(pre_checkout_query: PreCheckoutQuery):
    await pre_checkout_query.answer(ok=True)

# Обязательный шаг 2: ловим успешный платеж и реально выдаем VIP в базу
@router.message(F.successful_payment)
async def process_successful_payment(message: Message):
    payload = message.successful_payment.invoice_payload
    # Парсим наш payload, например: "set_vip_vip_plus_30"
    _, _, status, days_str = payload.split("_")
    days = int(days_str)
    
    user_id = message.from_user.id
    
    # Выдаем привилегию!
    await set_user_vip(user_id, status, days=days)
    
    status_display = "VIP++ 👑💎" if status == "vip_plus" else "VIP 👑"
    duration_display = "Навсегда" if days == 0 else f"{days} дней"

    await message.answer(
        f"🚀 <b>ПЛАТЕЖ ПРОШЕЛ УСПЕШНО!</b> 🚀\n\n"
        f"Спасибо за поддержку проекта! Тебе выдан статус <b>{status_display}</b>.\n"
        f"⏱ Срок: <b>{duration_display}</b>\n\n"
        f"Проверь свои новые бонусы в <code>/profile</code>!"
    )