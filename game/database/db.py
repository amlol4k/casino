import aiosqlite
from datetime import datetime, timedelta
DB_PATH = "database/casino.db"

async def init_db():
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute("""
            CREATE TABLE IF NOT EXISTS transfer_logs (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                sender_id INTEGER,
                receiver_id INTEGER,
                amount INTEGER,
                timestamp TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """)
        await db.commit()

async def get_today_transfers_count(user_id: int) -> int:
    """Возвращает количество переводов пользователя за последние 24 часа"""
    async with aiosqlite.connect(DB_PATH) as db:
        # Считаем записи за последние сутки
        async with db.execute("""
            SELECT COUNT(*) FROM transfer_logs 
            WHERE sender_id = ? AND timestamp >= datetime('now', '-1 day')
        """, (user_id,)) as cursor:
            row = await cursor.fetchone()
            return row[0] if row else 0

async def log_transfer(sender_id: int, receiver_id: int, amount: int):
    """Записывает перевод в лог"""
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute(
            "INSERT INTO transfer_logs (sender_id, receiver_id, amount) VALUES (?, ?, ?)",
            (sender_id, receiver_id, amount)
        )
        await db.execute("""
            CREATE TABLE IF NOT EXISTS users (
                user_id INTEGER PRIMARY KEY,
                username TEXT,
                balance INTEGER DEFAULT 5000,
                rank INTEGER DEFAULT 0,
                vip_status TEXT DEFAULT 'none',
                vip_expires_at TIMESTAMP,
                ref_id INTEGER
            )
        """)
        
        # Таблица промокодов
        await db.execute("""
            CREATE TABLE IF NOT EXISTS promocodes (
                code TEXT PRIMARY KEY,
                reward INTEGER,
                uses_left INTEGER
            )
        """)
        
        # Таблица истории активаций промокодов
        await db.execute("""
            CREATE TABLE IF NOT EXISTS promo_uses (
                user_id INTEGER,
                code TEXT,
                PRIMARY KEY (user_id, code)
            )
        """)
        
        # История ставок (для кнопок "Последние 3 ставки")
        await db.execute("""
            CREATE TABLE IF NOT EXISTS bet_history (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER,
                amount INTEGER,
                FOREIGN KEY(user_id) REFERENCES users(user_id)
            )
        """)

        # Инвестиционные компании (для Safe Fund)
        await db.execute("""
            CREATE TABLE IF NOT EXISTS companies (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                owner_id INTEGER,
                total_deposit INTEGER,
                current_investments INTEGER DEFAULT 0,
                status TEXT DEFAULT 'active'
            )
        """)

        # Создаем тестовый промокод при первом запуске
        await db.execute("""
            INSERT OR IGNORE INTO promocodes (code, reward, uses_left) 
            VALUES ('CASINO2026', 10000, 50)
        """)
        
        await db.commit()


async def add_bet_to_history(user_id: int, amount: int):
    """Сохраняет ставку в историю и держит там только уникальные последние 3 ставки"""
    async with aiosqlite.connect(DB_PATH) as db:
        # Удаляем точно такую же ставку из истории, если она была (чтобы не дублировать кнопки)
        await db.execute("DELETE FROM bet_history WHERE user_id = ? AND amount = ?", (user_id, amount))
        # Вставляем новую ставку
        await db.execute("INSERT INTO bet_history (user_id, amount) VALUES (?, ?)", (user_id, amount))
        
        # Лишние старые ставки (если записей больше 10 для юзера) подчищаем, чтобы база не раздувалась
        await db.execute("""
            DELETE FROM bet_history WHERE user_id = ? AND id NOT IN (
                SELECT id FROM bet_history WHERE user_id = ? ORDER BY id DESC LIMIT 5
            )
        """, (user_id, user_id))
        await db.commit()

async def get_last_bets(user_id: int) -> list:
    """Возвращает список из последних 3 уникальных ставок игрока"""
    async with aiosqlite.connect(DB_PATH) as db:
        async with db.execute(
            "SELECT amount FROM bet_history WHERE user_id = ? ORDER BY id DESC LIMIT 3", 
            (user_id,)
        ) as cursor:
            rows = await cursor.fetchall()
            return [row[0] for row in rows] if rows else []
async def register_user(user_id: int, username: str):
    async with aiosqlite.connect(DB_PATH) as db:
        # Указываем дефолтные ранг и вип прямо при инсерте, чтобы наверняка
        await db.execute(
            """INSERT OR IGNORE INTO users (user_id, username, balance, rank, vip_status) 
               VALUES (?, ?, ?, ?, ?)""",
            (user_id, username, 5000, 0, 'none')
        )
        await db.commit()
async def get_balance(user_id: int) -> int:
    async with aiosqlite.connect(DB_PATH) as db:
        async with db.execute("SELECT balance FROM users WHERE user_id = ?", (user_id,)) as cursor:
            row = await cursor.fetchone()
            if row:
                return row[0]
            return 0

async def update_balance(user_id: int, amount: int):
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute(
            "UPDATE users SET balance = balance + ? WHERE user_id = ?",
            (amount, user_id)
        )
        await db.commit()

# === НОВАЯ ФУНКЦИЯ ДЛЯ КАЗИНО: Получение ранга и VIP из базы ===
async def get_user_rates_data(user_id: int):
    async with aiosqlite.connect(DB_PATH) as db:
        async with db.execute("SELECT rank, vip_status FROM users WHERE user_id = ?", (user_id,)) as cursor:
            row = await cursor.fetchone()
            if row:
                return row[0], row[1]  # Возвращает (rank, vip_status)
            return 0, "none"    




async def set_user_vip(user_id: int, vip_status: str, days: int = 30):
    """Выдает VIP. Если days == 0, подписка становится бесконечной (NULL)"""
    if days > 0:
        expire_date = (datetime.now() + timedelta(days=days)).strftime('%Y-%m-%d %H:%M:%S')
    else:
        expire_date = None # Навсегда
    
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute(
            "UPDATE users SET vip_status = ?, vip_expires_at = ? WHERE user_id = ?",
            (vip_status, expire_date, user_id)
        )
        await db.commit()


# Функция активации промокода
async def use_promocode(user_id: int, code: str) -> str | int:
    async with aiosqlite.connect(DB_PATH) as db:
        async with db.execute("SELECT reward, uses_left FROM promocodes WHERE code = ?", (code,)) as cursor:
            promo = await cursor.fetchone()
            if not promo:
                return "not_found"
            reward, uses_left = promo
            
        if uses_left <= 0:
            return "expired"
            
        async with db.execute("SELECT 1 FROM promo_uses WHERE user_id = ? AND code = ?", (user_id, code)) as cursor:
            if await cursor.fetchone():
                return "already_used"
                
        await db.execute("UPDATE promocodes SET uses_left = uses_left - 1 WHERE code = ?", (code,))
        await db.execute("INSERT INTO promo_uses (user_id, code) VALUES (?, ?)", (user_id, code))
        await db.execute("UPDATE users SET balance = balance + ? WHERE user_id = ?", (reward, user_id))
        await db.commit()
        
        return reward
    

async def transfer_money(sender_id: int, receiver_id: int, amount: int) -> bool:
    """Проводит транзакцию перевода денег между пользователями"""
    async with aiosqlite.connect(DB_PATH) as db:
        # Проверяем баланс отправителя еще раз для безопасности
        async with db.execute("SELECT balance FROM users WHERE user_id = ?", (sender_id,)) as cursor:
            row = await cursor.fetchone()
            if not row or row[0] < amount:
                return False
        
        # Списываем у отправителя полную сумму
        await db.execute("UPDATE users SET balance = balance - ? WHERE user_id = ?", (amount, sender_id))
        # Начисляем получателю (налог вычтем уже в самом хендлере перед вызовом этой функции)
        await db.execute("UPDATE users SET balance = balance + ? WHERE user_id = ?", (amount, receiver_id))
        
        await db.commit()
        return True

async def get_user_id_by_username(username: str) -> int | None:
    """Ищет ID пользователя по его тегу (без @)"""
    # Очищаем юзернейм от возможной собачки
    clean_username = username.replace("@", "").lower()
    async with aiosqlite.connect(DB_PATH) as db:
        # Используем LOWER для регистронезависимого поиска
        async with db.execute("SELECT user_id FROM users WHERE LOWER(username) = ?", (clean_username,)) as cursor:
            row = await cursor.fetchone()
            return row[0] if row else None