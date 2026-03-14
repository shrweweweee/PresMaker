"""
Telegram-бот. Брендбук загружается из brand/config.yaml при старте.
Для форка на другую компанию — меняйте только config.yaml.

Установка:
    pip install python-telegram-bot anthropic python-pptx matplotlib pillow pandas openpyxl pyyaml

Запуск:
    TELEGRAM_TOKEN=... ANTHROPIC_API_KEY=... python bot.py

Форк для другой компании:
    BRAND_CONFIG=/path/to/other_company/config.yaml python bot.py
"""
import os, logging
from dotenv import load_dotenv
load_dotenv()
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import (
    Application, CommandHandler, MessageHandler,
    CallbackQueryHandler, ContextTypes, filters,
)
from brand.loader import brand, reload as reload_brand
from stages.session import SessionStore
from stages.pipeline import Pipeline

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
log = logging.getLogger(__name__)

store = SessionStore()
pipeline = Pipeline()


async def cmd_start(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    store.reset(update.effective_user.id)
    await update.message.reply_text(
        "Привет! Я помогу создать презентацию.\n"
        "Напишите для какой компании и на какую тему.",
    )


async def cmd_brand_info(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    """Показывает текущий активный брендбук (только для админов/инфо)."""
    b = brand
    text = (
        f"🎨 *Активный брендбук: {b.company_name}*\n\n"
        f"Язык: `{b.language}` · Тон: `{b.tone}`\n"
        f"Основной цвет: `#{b.colors.primary_hex.lstrip('#')}`\n"
        f"Акцентный цвет: `#{b.colors.accent_hex.lstrip('#')}`\n"
        f"Шрифт: `{b.typography.font_heading}`\n"
        f"Слайдов по умолчанию: `{b.slide_defaults.count}`\n\n"
        f"Конфиг: `brand/config.yaml`\n"
        f"Чтобы сменить стиль — отредактируйте файл и отправьте /reload"
    )
    await update.message.reply_text(text, parse_mode="Markdown")


async def cmd_reload(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    """Перезагружает брендбук без перезапуска бота."""
    try:
        reload_brand()
        await update.message.reply_text(
            f"✅ Брендбук перезагружен: *{brand.company_name}*\n"
            f"Цвета: `{brand.colors.primary_hex}` / `{brand.colors.accent_hex}`",
            parse_mode="Markdown"
        )
    except Exception as e:
        await update.message.reply_text(f"❌ Ошибка загрузки конфига: `{e}`", parse_mode="Markdown")


async def cmd_reset(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    store.reset(update.effective_user.id)
    await update.message.reply_text("🔄 Сессия сброшена. Напишите новую задачу.")


async def handle_message(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    uid = update.effective_user.id
    msg = update.message
    text = msg.text or msg.caption or ""

    file_bytes, file_name = None, None
    if msg.document:
        f = await msg.document.get_file()
        file_bytes = await f.download_as_bytearray()
        file_name = msg.document.file_name

    session = store.get_or_create(uid)
    await ctx.bot.send_chat_action(msg.chat_id, "typing")

    try:
        result = await pipeline.step(session, text, file_bytes, file_name)
    except Exception as e:
        log.exception("Pipeline error")
        await msg.reply_text(f"❌ Ошибка: {e}")
        return

    if result["type"] == "message":
        body = result["text"]
        try:
            await msg.reply_text(body, parse_mode="Markdown")
        except Exception:
            log.warning("Markdown parse failed, sending plain text")
            await msg.reply_text(body)

    elif result["type"] == "file":
        await ctx.bot.send_chat_action(msg.chat_id, "upload_document")
        await msg.reply_document(
            document=open(result["path"], "rb"),
            filename=result["filename"],
            caption=f"✅ {result['caption']}",
        )
        kb = InlineKeyboardMarkup([[
            InlineKeyboardButton("🔄 Новая презентация", callback_data="new"),
        ]])
        await msg.reply_text(
            "Можете попросить изменения или нажмите кнопку для новой презентации.",
            reply_markup=kb,
        )


async def handle_callback(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query
    await q.answer()
    if q.data == "new":
        store.reset(q.from_user.id)
        await q.message.reply_text("Напишите новую задачу 📝")


def main():
    log.info(f"Starting bot for: {brand.company_name}")
    app = Application.builder().token(os.environ["TELEGRAM_TOKEN"]).build()
    app.add_handler(CommandHandler("start",   cmd_start))
    app.add_handler(CommandHandler("brand",   cmd_brand_info))
    app.add_handler(CommandHandler("reload",  cmd_reload))
    app.add_handler(CommandHandler("reset",   cmd_reset))
    app.add_handler(MessageHandler(filters.ALL & ~filters.COMMAND, handle_message))
    app.add_handler(CallbackQueryHandler(handle_callback))
    app.run_polling()


if __name__ == "__main__":
    main()
