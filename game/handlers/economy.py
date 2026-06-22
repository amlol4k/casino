from aiogram import Router, html
from aiogram.filters import Command, CommandObject
from aiogram.types import Message
from database.db import register_user, get_balance, update_balance, use_promocode
from database.db import transfer_money, get_user_id_by_username, get_today_transfers_count, log_transfer, update_balance
from handlers.games import calculate_game_rates
from aiogram.fsm.context import FSMContext
router = Router()



@router.message(Command("start"))
async def cmd_start(message: Message):
    user_id = message.from_user.id
    username = message.from_user.username or message.from_user.first_name
    await register_user(user_id, username)
    balance = await get_balance(user_id)
    
    await message.answer(
        f"Йоу, {html.bold(message.from_user.full_name)}!\n\n"
        f"Добро пожаловать в подпольное казино. 🎰\n"
        f"Твой баланс: {html.code(f'{balance:,}')} 💵\n\n"
        f"Используй команды чата, чтобы поднимать бабло!"
    )

@router.message(Command("balance", "bal"))
async def cmd_balance(message: Message):
    user_id = message.from_user.id
    username = message.from_user.username or message.from_user.first_name
    await register_user(user_id, username)
    balance = await get_balance(user_id)
    await message.reply(f"💵 Твой баланс: {html.code(f'{balance:,}')} монет.")

# КОМ@router.message(Command("pay"))

@router.message(Command("pay"))
async def cmd_transfer(message: Message, command: CommandObject):
    sender_id = message.from_user.id
    sender_mention = message.from_user.mention_html(message.from_user.first_name)
    
    if not command.args:
        await message.reply(
            "❌ <b>Неправильный формат!</b>\n"
            "Используй: <code>/pay @username 1000</code> или ответь на сообщение получателя командой <code>/pay 1000</code>"
        )
        return

    args = command.args.split()
    receiver_id = None
    amount = 0

    # Проверяем, как переводит (реплай или тег)
    if message.reply_to_message:
        receiver_id = message.reply_to_message.from_user.id
        receiver_username = message.reply_to_message.from_user.username or message.reply_to_message.from_user.first_name
        try: amount = int(args[0])
        except ValueError:
            await message.reply("❌ Сумма перевода должна быть числом!")
            return
    else:
        if len(args) < 2:
            await message.reply("❌ Укажи пользователя и сумму! Пример: <code>/pay @alex 500</code>")
            return
        
        target_username = args[0]
        try: amount = int(args[1])
        except ValueError:
            await message.reply("❌ Сумма перевода должна быть числом!")
            return

        receiver_id = await get_user_id_by_username(target_username)
        receiver_username = target_username.replace("@", "")
        
        if not receiver_id:
            await message.reply("❌ Пользователь не найден в базе данных бота!")
            return

    if receiver_id == sender_id:
        await message.reply("❌ Нельзя переводить монеты самому себе!")
        return
    if amount <= 0:
        await message.reply("❌ Сумма перевода должна быть больше нуля!")
        return

    # === ПРОВЕРКА ЛИМИТОВ И КОМИССИИ ===
    rates = await calculate_game_rates(sender_id)
    transfers_done = await get_today_transfers_count(sender_id)

    # Проверяем, не превысил ли юзер лимит на сегодня
    if transfers_done >= rates["pay_limit"]:
        await message.reply(
            f"❌ <b>Лимит переводов исчерпан!</b>\n"
            f"Твой лимит: {rates['pay_limit']} перев./сут. Ты уже сделал: {transfers_done}.\n"
            f"Повысить лимит можно купив VIP или VIP++."
        )
        return

    # Проверяем баланс отправителя
    sender_balance = await get_balance(sender_id)
    if sender_balance < amount:
        await message.reply(f"❌ Недостаточно монет! Твой баланс: <code>{sender_balance:,}</code>")
        return

    # Расчет комиссии
    tax_rate = rates["pay_tax"]
    tax_amount = int(amount * tax_rate)
    final_amount = amount - tax_amount

    # Проводим транзакцию
    success = await transfer_money(sender_id, receiver_id, amount)
    
    if success:
        # Вычитаем комиссию и логируем перевод
        await update_balance(receiver_id, -tax_amount) 
        await log_transfer(sender_id, receiver_id, amount)
        
        # Сколько переводов осталось на сегодня
        remains = rates["pay_limit"] - (transfers_done + 1)
        
        await message.answer(
            f"✅ <b>Успешный перевод!</b>\n\n"
            f"👤 Отправитель: {sender_mention}\n"
            f"👤 Получатель: @{receiver_username}\n"
            f"💰 Отправлено: <code>{amount:,}</code> монет\n"
            f"💸 Комиссия ({int(tax_rate*100)}%): <code>{tax_amount:,}</code> монет\n"
            f"📥 Получено чистыми: <code>{final_amount:,}</code> монет\n"
            f"─────────────────────────\n"
            f"⏱ Осталось переводов на сегодня: <b>{remains}</b> из {rates['pay_limit']}"
        )
    else:
        await message.reply("❌ Ошибка транзакции.")

        
# КОМАНДА АКТИВАЦИИ ПРОМОКОДА
@router.message(Command("promo"))
async def cmd_promo(message: Message, command: CommandObject):
    user_id = message.from_user.id
    username = message.from_user.username or message.from_user.first_name
    await register_user(user_id, username)
    
    if not command.args:
        await message.reply("❌ Введи промокод! Пример: /promo CASINO2026")
        return
        
    # Переводим в верхний регистр, чтобы регистр букв не имел значения (casino2026 и CASINO2026 будут работать одинаково)
    code = command.args.upper().strip()
    
    result = await use_promocode(user_id, code)
    
    if result == "not_found":
        await message.reply("❌ Такого промокода не существует!")
    elif result == "expired":
        await message.reply("❌ У этого промокода закончились активации!")
    elif result == "already_used":
        await message.reply("❌ Ты уже активировал этот промокод!")
    else:
        await message.reply(
            f"✅ Промокод успешно активирован!\n"
            f"На твой баланс зачислено: {html.code(f'+{result:,}')} 💵"
        )


# Замени этот ID на свой реальный ID (узнаешь у @userinfobot)
ADMIN_ID = 1600354632 

@router.message(Command("addpromo"))
async def cmd_add_promo(message: Message, command: CommandObject):
    if message.from_user.id != ADMIN_ID:
        return # Игнорируем всех, кроме тебя

    if not command.args or len(command.args.split()) != 3:
        await message.reply("❌ Формат: /addpromo КОД СУММА АКТИВАЦИЙ\nПример: /addpromo ЛЕТО 5000 10")
        return

    code, reward, uses = command.args.split()
    
    # Добавляем в базу
    import aiosqlite
    async with aiosqlite.connect("database/casino.db") as db:
        await db.execute(
            "INSERT OR REPLACE INTO promocodes (code, reward, uses_left) VALUES (?, ?, ?)",
            (code.upper(), int(reward), int(uses))
        )
        await db.commit()
    
    await message.reply(f"✅ Промокод {html.code(code.upper())} на {reward} монет создан!")

@router.message(Command("balance", "bal"))
async def cmd_balance(message: Message):
    # Если ответили на сообщение, смотрим баланс того, кому ответили
    if message.reply_to_message:
        target_id = message.reply_to_message.from_user.id
        target_name = message.reply_to_message.from_user.first_name
        balance = await get_balance(target_id)
        await message.reply(f"💵 Баланс {html.bold(target_name)}: {html.code(f'{balance:,}')} монет.")
    else:
        # Иначе смотрим свой баланс
        user_id = message.from_user.id
        balance = await get_balance(user_id)
        await message.reply(f"💵 Твой баланс: {html.code(f'{balance:,}')} монет.")

        
@router.message(Command("profile", "p"))
async def cmd_profile(message: Message, state: FSMContext):
    user_id = message.from_user.id
    username = message.from_user.username or message.from_user.first_name
    
    await register_user(user_id, username)

    # Собираем все данные юзера
    balance = await get_balance(user_id)
    rates = await calculate_game_rates(user_id)
    transfers_today = await get_today_transfers_count(user_id)
    
    # Достаем текущий стрик побед из сессии
    data = await state.get_data()
    win_streak = data.get("win_streak", 0)

    # Оформляем статус текстом
    from database.db import get_user_rates_data
    _, vip_raw = await get_user_rates_data(user_id)
    
    if vip_raw == "vip_plus":
        status_text = "VIP++ 👑💎"
    elif vip_raw == "vip":
        status_text = "VIP 👑"
    else:
        status_text = "Обычный 👤"

    remains = rates["pay_limit"] - transfers_today

    await message.answer(
        f"👤 <b>ИГРОВОЙ ПРОФИЛЬ: {message.from_user.first_name}</b>\n"
        f"─────────────────────────\n"
        f"💵 Баланс: <code>{balance:,}</code> 💵\n"
        f"👑 Статус: <b>{status_text}</b>\n\n"
        f"📊 <b>Статистика:</b>\n"
        f"🔥 Серия побед: <b>{win_streak}</b>\n"
        f"💸 Переводов сегодня: <b>{transfers_today} / {rates['pay_limit']}</b> (Осталось: {remains})\n\n"
        f"🛠 <b>Твои игровые условия:</b>\n"
        f"📉 Налог на выигрыш: <b>{int(rates['tax']*100)}%</b>\n"
        f"💸 Комиссия /pay: <b>{int(rates['pay_tax']*100)}%</b>\n"
        f"↩️ Возврат при лузе: <b>{int(rates['cashback']*100)}%</b>"
    )