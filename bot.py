import os
from gtts import gTTS
from dotenv import load_dotenv
from telegram import Update, KeyboardButton, ReplyKeyboardMarkup
from telegram.ext import Application, CommandHandler, MessageHandler, ContextTypes, filters

load_dotenv()
BOT_TOKEN = os.getenv("BOT_TOKEN")

# Travel-фрази (приклади, доповнюй своїми)
TRAVEL_PHRASES = {
    "готель": [
        {
            "en": "I'd like to check in, please.",
            "ua": "Я хочу заселитися, будь ласка.",
            "tip": "Звернення до рецепції."
        },
        {
            "en": "Do you have a reservation?",
            "ua": "У вас є бронювання?",
            "tip": "Питання від адміністратора."
        },
        {
            "en": "Can I have the Wi-Fi password?",
            "ua": "Можна пароль від Wi-Fi?",
            "tip": "Попросити інтернет."
        }
    ],
    "таксі": [
        {
            "en": "How much does it cost to go to the airport?",
            "ua": "Скільки коштує доїхати до аеропорту?",
            "tip": "Питання про ціну."
        },
        {
            "en": "Please take me to this address.",
            "ua": "Відвезіть мене за цією адресою, будь ласка.",
            "tip": "Показати адресу водію."
        }
    ]
    # Додавай ще теми!
}

TOPICS_LIST = list(TRAVEL_PHRASES.keys())

def get_voice_filename(user_id):
    return f"voice_{user_id}.mp3"

async def send_travel_phrase(update: Update, en, ua, tip):
    await update.message.reply_text(f"🇬🇧 {en}\n🇺🇦 {ua}\n💡 {tip}")
    filename = get_voice_filename(update.effective_user.id)
    tts = gTTS(en, lang='en')
    tts.save(filename)
    with open(filename, 'rb') as voice:
        await update.message.reply_voice(voice)
    os.remove(filename)

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    keyboard = [
        [KeyboardButton("Навчання"), KeyboardButton("Довідник")]
    ]
    reply_markup = ReplyKeyboardMarkup(keyboard, resize_keyboard=True)
    await update.message.reply_text(
        "Привіт! Я travel-бот з англійської для подорожей 🌍\n\n"
        "👉 Хочеш швидко навчитись — обери 'Навчання'.\n"
        "👉 Потрібна фраза зараз — обери 'Довідник'.",
        reply_markup=reply_markup
    )
    context.user_data["mode"] = None

async def handle_text(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text = update.message.text.lower().strip()
    if text in ["навчання", "/learn"]:
        context.user_data["mode"] = "learn"
        context.user_data["learn_topic"] = 0
        context.user_data["learn_phrase"] = 0
        await show_next_phrase(update, context)
    elif text in ["довідник", "/browse"]:
        context.user_data["mode"] = "browse"
        await show_topics(update)
    elif text in TOPICS_LIST:
        await show_topic_phrases(update, text)
    elif context.user_data.get("mode") == "learn":
        await show_next_phrase(update, context)
    else:
        await find_phrase(update, text)

async def show_topics(update: Update):
    topics = [f"• {k.title()}" for k in TOPICS_LIST]
    await update.message.reply_text(
        "Оберіть тему або напишіть її назву українською:\n" + "\n".join(topics)
    )

async def show_topic_phrases(update: Update, topic):
    phrases = TRAVEL_PHRASES.get(topic, [])
    if not phrases:
        await update.message.reply_text("У цій темі поки що немає фраз.")
        return
    for p in phrases:
        await send_travel_phrase(update, p["en"], p["ua"], p["tip"])

async def show_next_phrase(update: Update, context: ContextTypes.DEFAULT_TYPE):
    topic_idx = context.user_data.get("learn_topic", 0)
    phrase_idx = context.user_data.get("learn_phrase", 0)
    if topic_idx >= len(TOPICS_LIST):
        await update.message.reply_text("Ви пройшли всі теми! 👏")
        return
    topic = TOPICS_LIST[topic_idx]
    phrases = TRAVEL_PHRASES[topic]
    if phrase_idx >= len(phrases):
        context.user_data["learn_topic"] = topic_idx + 1
        context.user_data["learn_phrase"] = 0
        await show_next_phrase(update, context)
        return
    p = phrases[phrase_idx]
    await send_travel_phrase(update, p["en"], p["ua"], p["tip"])
    context.user_data["learn_phrase"] = phrase_idx + 1

async def find_phrase(update: Update, query):
    query = query.lower()
    results = []
    for topic, phrases in TRAVEL_PHRASES.items():
        for p in phrases:
            if query in p["en"].lower() or query in p["ua"].lower():
                results.append(p)
    if not results:
        await update.message.reply_text("Фразу не знайдено. Спробуйте інше слово.")
    else:
        for p in results:
            await send_travel_phrase(update, p["en"], p["ua"], p["tip"])

def main():
    app = Application.builder().token(BOT_TOKEN).build()
    app.add_handler(CommandHandler("start", start))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_text))
    app.run_polling()

if __name__ == "__main__":
    main()
