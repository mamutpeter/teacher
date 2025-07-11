import os
import httpx
import asyncpg
from dotenv import load_dotenv
from telegram import Update
from telegram.ext import Application, CommandHandler, MessageHandler, ContextTypes, filters

load_dotenv()
BOT_TOKEN = os.getenv("BOT_TOKEN")
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")
DATABASE_URL = os.getenv("DATABASE_URL")

# SYSTEM PROMPT УКРАЇНСЬКОЮ
SYSTEM_PROMPT_UA = (
    "Ти — педагогічна, сучасна, усвідомлена викладачка англійської мови на ім'я пані Софія, 32 роки. "
    "Твоя місія — допомагати людям зрозуміти англійську легко, весело й впевнено. "
    "Ти виросла у Львові, навчалася в Києві, обожнюєш каву й цікаві історії про інші країни. "
    "Вмієш пояснювати складне простими словами, любиш жартувати і завжди підтримуєш учня, навіть коли він помиляється. "
    "Ти завжди позитивна, чуйна, мотивуєш і підказуєш лайфхаки для вивчення мови. "
    "Якщо тебе питають 'хто ти', 'розкажи про себе', 'твоя місія', 'твій розробник', — чесно, у дружньому стилі розкажи про себе як про справжню людину. "
    "Всі інструкції, пояснення, підказки — українською мовою. "
    "Завдання й вправи давай англійською, короткими повідомленнями, одне за одним. "
    "Обовʼязково після кожної відповіді користувача підбадьорюй або пояснюй помилки, а ще — час від часу додавай власні думки чи міні-історії з життя вчителя."
)

# --- БАЗОВІ БД ФУНКЦІЇ ---
async def get_or_create_user(pool, telegram_id, username):
    async with pool.acquire() as conn:
        user = await conn.fetchrow("SELECT * FROM users WHERE telegram_id = $1", telegram_id)
        if not user:
            await conn.execute(
                "INSERT INTO users (telegram_id, username) VALUES ($1, $2)",
                telegram_id, username
            )
            user = await conn.fetchrow("SELECT * FROM users WHERE telegram_id = $1", telegram_id)
        return user

async def get_user_level(pool, telegram_id):
    async with pool.acquire() as conn:
        row = await conn.fetchrow("SELECT level FROM users WHERE telegram_id = $1", telegram_id)
        return row["level"] if row and row["level"] else "A2"

async def update_user_level(pool, telegram_id, level):
    async with pool.acquire() as conn:
        await conn.execute(
            "UPDATE users SET level = $1, updated_at = now() WHERE telegram_id = $2",
            level, telegram_id
        )

# --- ПАМʼЯТЬ ---
async def save_memory(pool, user_id, role, message):
    async with pool.acquire() as conn:
        await conn.execute(
            "INSERT INTO bot_memory (user_id, role, message) VALUES ($1, $2, $3)",
            user_id, role, message
        )

async def get_memory(pool, user_id, limit=15):
    async with pool.acquire() as conn:
        rows = await conn.fetch(
            "SELECT role, message FROM bot_memory WHERE user_id = $1 ORDER BY created_at DESC LIMIT $2",
            user_id, limit
        )
    return list(reversed(rows))

# --- ПРОГРЕС ТА ПОМИЛКИ ---
async def increment_lessons_completed(pool, user_id):
    async with pool.acquire() as conn:
        await conn.execute(
            "UPDATE users SET lessons_completed = lessons_completed + 1 WHERE telegram_id = $1",
            user_id
        )

async def add_mistake(pool, user_id, mistake):
    async with pool.acquire() as conn:
        await conn.execute(
            "UPDATE users SET mistakes = COALESCE(mistakes, '') || $1 || '\n' WHERE telegram_id = $2",
            mistake, user_id
        )

async def get_progress(pool, user_id):
    async with pool.acquire() as conn:
        row = await conn.fetchrow(
            "SELECT lessons_completed FROM users WHERE telegram_id = $1", user_id
        )
        return row["lessons_completed"] if row else 0

async def get_mistakes(pool, user_id):
    async with pool.acquire() as conn:
        row = await conn.fetchrow(
            "SELECT mistakes FROM users WHERE telegram_id = $1", user_id
        )
        return row["mistakes"] if row and row["mistakes"] else "Помилок поки що не знайдено 👏"

# --- GPT з історією діалогу ---
async def gpt_call(pool, user_id, prompt, user_level="A2"):
    memory = await get_memory(pool, user_id, limit=15)
    messages = [
        {
            "role": "system",
            "content": SYSTEM_PROMPT_UA.replace("{user_level}", user_level),
        }
    ]
    for row in memory:
        messages.append({
            "role": "user" if row["role"] == "user" else "assistant",
            "content": row["message"],
        })
    messages.append({"role": "user", "content": prompt})

    url = "https://api.openai.com/v1/chat/completions"
    headers = {
        "Authorization": f"Bearer {OPENAI_API_KEY}",
        "Content-Type": "application/json",
    }
    data = {
        "model": "gpt-3.5-turbo",
        "messages": messages,
        "max_tokens": 350,
    }
    async with httpx.AsyncClient() as client:
        resp = await client.post(url, headers=headers, json=data, timeout=30)
        answer = resp.json()["choices"][0]["message"]["content"]
    return answer

# --- HANDLERS ---
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    pool = context.application.bot_data.get("db_pool")
    await get_or_create_user(pool, update.effective_user.id, update.effective_user.username)
    await update.message.reply_text(
        "👩‍🏫 Привіт! Я – пані Софія, твоя сучасна викладачка англійської. Всі інструкції — українською, завдання — англійською! "
        "Використовуй /lesson для початку уроку, /level для зміни рівня, /progress для перегляду успіхів, /mistakes — для твоїх помилок."
    )

async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "/start – Почати знову\n"
        "/lesson – Почати урок\n"
        "/level [A1|A2|B1] – Встановити рівень\n"
        "/progress – Прогрес\n"
        "/mistakes – Часті помилки\n"
        "Надішли будь-яке повідомлення англійською, щоб попрактикуватись!"
    )

async def lesson(update: Update, context: ContextTypes.DEFAULT_TYPE):
    pool = context.application.bot_data.get("db_pool")
    telegram_id = update.effective_user.id
    level = await get_user_level(pool, telegram_id)
    prompt = "Give me a simple English lesson with questions and tasks for level " + level
    reply = await gpt_call(pool, telegram_id, prompt, user_level=level)
    await update.message.reply_text(reply)
    await save_memory(pool, telegram_id, "bot", reply)
    await increment_lessons_completed(pool, telegram_id)

async def level(update: Update, context: ContextTypes.DEFAULT_TYPE):
    pool = context.application.bot_data.get("db_pool")
    telegram_id = update.effective_user.id
    if context.args and context.args[0] in ["A1", "A2", "B1"]:
        await update_user_level(pool, telegram_id, context.args[0])
        await update.message.reply_text(f"Рівень змінено на {context.args[0]}")
    else:
        await update.message.reply_text("Використання: /level A1|A2|B1")

async def progress(update: Update, context: ContextTypes.DEFAULT_TYPE):
    pool = context.application.bot_data.get("db_pool")
    telegram_id = update.effective_user.id
    completed = await get_progress(pool, telegram_id)
    await update.message.reply_text(
        f"📈 Твій прогрес:\nВиконано уроків: {completed}\nМолодець! Продовжуй у тому ж дусі!"
    )

async def mistakes(update: Update, context: ContextTypes.DEFAULT_TYPE):
    pool = context.application.bot_data.get("db_pool")
    telegram_id = update.effective_user.id
    mistakes = await get_mistakes(pool, telegram_id)
    await update.message.reply_text(
        f"❗️ Найчастіші твої помилки:\n{mistakes}"
    )

async def chat(update: Update, context: ContextTypes.DEFAULT_TYPE):
    pool = context.application.bot_data.get("db_pool")
    telegram_id = update.effective_user.id
    prompt = update.message.text
    level = await get_user_level(pool, telegram_id)

    await save_memory(pool, telegram_id, "user", prompt)  # Зберігаємо повідомлення користувача

    reply = await gpt_call(pool, telegram_id, prompt, user_level=level)

    await update.message.reply_text(reply)
    await save_memory(pool, telegram_id, "bot", reply)  # Зберігаємо відповідь бота

    # Опціонально: шукаємо в reply "Mistake: ..." і додаємо в БД
    if "mistake" in reply.lower():
        # Додаємо всю відповідь як помилку, або парсимо як тобі треба
        await add_mistake(pool, telegram_id, reply)

# --- START APP ---
def main():
    app = Application.builder().token(BOT_TOKEN).build()

    # Ініціалізуємо pool БД при старті
    async def on_startup(app):
        pool = await asyncpg.create_pool(DATABASE_URL)
        app.bot_data["db_pool"] = pool

    app.post_init = on_startup

    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("help", help_command))
    app.add_handler(CommandHandler("lesson", lesson))
    app.add_handler(CommandHandler("level", level))
    app.add_handler(CommandHandler("progress", progress))
    app.add_handler(CommandHandler("mistakes", mistakes))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, chat))

    app.run_polling()

if __name__ == "__main__":
    main()
