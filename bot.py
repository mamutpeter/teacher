import os
import httpx
from dotenv import load_dotenv
from telegram import Update
from telegram.ext import Application, CommandHandler, MessageHandler, ContextTypes, filters

load_dotenv()
BOT_TOKEN = os.getenv("BOT_TOKEN")
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")

USER_LEVEL = {}

# --- OpenAI GPT Request ---
async def gpt_call(prompt, user_level="A2"):
    url = "https://api.openai.com/v1/chat/completions"
    headers = {
        "Authorization": f"Bearer {OPENAI_API_KEY}",
        "Content-Type": "application/json",
    }
    messages = [
        {
            "role": "system",
            "content": f"You are an English teacher for level {user_level}. Speak simple English. Ask questions, check answers, and help improve English.",
        },
        {"role": "user", "content": prompt}
    ]
    data = {
        "model": "gpt-3.5-turbo",
        "messages": messages,
        "max_tokens": 300,
    }
    async with httpx.AsyncClient() as client:
        resp = await client.post(url, headers=headers, json=data, timeout=20)
        answer = resp.json()["choices"][0]["message"]["content"]
    return answer

# --- Handlers ---
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    USER_LEVEL[update.effective_user.id] = "A2"
    await update.message.reply_text(
        "👋 Hi! I'm your English tutor bot for pre-intermediate (A2) level.\n"
        "Use /lesson to start a lesson.\n"
        "Use /level [A1|A2|B1] to set your level.\n"
        "Send me any message to practice!"
    )

async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "/start – Start bot\n"
        "/lesson – Start a lesson\n"
        "/level A2 – Change your level (A1/A2/B1)\n"
        "Just write any message in English to practice!"
    )

async def lesson(update: Update, context: ContextTypes.DEFAULT_TYPE):
    level = USER_LEVEL.get(update.effective_user.id, "A2")
    prompt = "Give me a simple English lesson with questions and tasks for level " + level
    reply = await gpt_call(prompt, user_level=level)
    await update.message.reply_text(reply)

async def level(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if context.args and context.args[0] in ["A1", "A2", "B1"]:
        USER_LEVEL[update.effective_user.id] = context.args[0]
        await update.message.reply_text(f"Level set to {context.args[0]}")
    else:
        await update.message.reply_text("Usage: /level A1|A2|B1")

async def chat(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    level = USER_LEVEL.get(user_id, "A2")
    prompt = update.message.text
    reply = await gpt_call(prompt, user_level=level)
    await update.message.reply_text(reply)

def main():
    app = Application.builder().token(BOT_TOKEN).build()
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("help", help_command))
    app.add_handler(CommandHandler("lesson", lesson))
    app.add_handler(CommandHandler("level", level))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, chat))
    app.run_polling()

if __name__ == "__main__":
    main()
