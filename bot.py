"""
bot.py — Telegram bot entry point.

Commands:
  /start   — welcome + main menu
  /config  — open search parameter wizard
  /run     — scrape & send new jobs now
  /status  — show current config + stats
  /help    — usage guide
"""

import logging
import os
from datetime import datetime
from dotenv import load_dotenv

from telegram import (
    Update,
    InlineKeyboardButton,
    InlineKeyboardMarkup,
)
from telegram.ext import (
    Application,
    CommandHandler,
    CallbackQueryHandler,
    MessageHandler,
    ConversationHandler,
    ContextTypes,
    filters,
)

import db
import scraper

load_dotenv()
TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")

logging.basicConfig(
    format="%(asctime)s | %(levelname)-8s | %(name)s — %(message)s",
    level=logging.INFO,
    handlers=[
        logging.FileHandler(os.path.join("logs", "bot.log")),
        logging.StreamHandler(),
    ],
)
logger = logging.getLogger(__name__)

# ── Conversation states ───────────────────────────────────────────────────────
CHOOSE_PARAM, GET_VALUE = range(2)

# ── Searchable parameters with metadata ──────────────────────────────────────
PARAMS = {
    "site_name": {
        "label": "📡 Sites",
        "hint": 'Comma-separated list.\nOptions: linkedin, indeed\nExample: linkedin, indeed',
        "type": "list",
    },
    "search_term": {
        "label": "🔍 Search Term",
        "hint": 'What job title to search.\nExample: AI Engineer',
        "type": "str",
    },
    "google_search_term": {
        "label": "🌐 Google Search Term",
        "hint": 'Full sentence for Google.\nExample: Internship Data Science jobs Germany',
        "type": "str",
    },
    "location": {
        "label": "📍 Location",
        "hint": 'City or country.\nExample: Berlin  or  Germany',
        "type": "str",
    },
    "results_wanted": {
        "label": "📊 Results Wanted",
        "hint": 'How many jobs to fetch (number).\nExample: 50',
        "type": "int",
    },
    "country_indeed": {
        "label": "🌍 Indeed Country",
        "hint": 'Country code for Indeed.\nExample: germany',
        "type": "str",
    },
    "job_type": {
        "label": "💼 Job Type",
        "hint": 'One of: fulltime, parttime, internship, contract',
        "type": "str",
    },
    "linkedin_fetch_description": {
        "label": "📝 Fetch LinkedIn Description",
        "hint": 'Fetch full description from LinkedIn? (slower)\nType: yes or no',
        "type": "bool",
    },
}


# ── Helpers ───────────────────────────────────────────────────────────────────

def _ensure_user(update: Update):
    """Create/touch the user record from any update type."""
    user = update.effective_user
    db.update_user(user.id, {
        "username":   user.username,
        "first_name": user.first_name,
    })
    return db.get_user(user.id)


def _main_menu_keyboard():
    return InlineKeyboardMarkup([
        [
            InlineKeyboardButton("⚙️ Configure Search", callback_data="open_config"),
            InlineKeyboardButton("▶️ Run Now",          callback_data="run_now"),
        ],
        [
            InlineKeyboardButton("📋 My Status",  callback_data="status"),
            InlineKeyboardButton("❓ Help",        callback_data="help"),
        ],
    ])


def _config_keyboard():
    rows = []
    items = list(PARAMS.items())
    for i in range(0, len(items), 2):
        row = []
        for key, meta in items[i:i+2]:
            row.append(InlineKeyboardButton(meta["label"], callback_data=f"param:{key}"))
        rows.append(row)
    rows.append([InlineKeyboardButton("🔙 Back to Menu", callback_data="main_menu")])
    return InlineKeyboardMarkup(rows)


def _config_summary(user_id: int) -> str:
    cfg = db.get_search_config(user_id)
    lines = ["<b>Current Search Config:</b>"]
    for key, meta in PARAMS.items():
        val = cfg.get(key, "—")
        if isinstance(val, list):
            val = ", ".join(val)
        lines.append(f"  {meta['label']}: <code>{val}</code>")
    return "\n".join(lines)


# ── /start ────────────────────────────────────────────────────────────────────

async def cmd_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    _ensure_user(update)
    name = update.effective_user.first_name or "there"
    await update.message.reply_text(
        f"👋 Hey <b>{name}</b>! I'm your <b>Job Scout Bot</b>.\n\n"
        "I scrape LinkedIn & Indeed for you and send only <i>new</i> jobs — no duplicates.\n\n"
        "What would you like to do?",
        parse_mode="HTML",
        reply_markup=_main_menu_keyboard(),
    )


# ── /help ─────────────────────────────────────────────────────────────────────

async def cmd_help(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text = (
        "📖 <b>How to use this bot</b>\n\n"
        "<b>/start</b>  — Main menu\n"
        "<b>/config</b> — Set your search parameters\n"
        "<b>/run</b>    — Scrape jobs & receive new ones now\n"
        "<b>/status</b> — View your config & stats\n\n"
        "The bot remembers every job it has sent you. Only <i>new</i> listings appear each run.\n"
        "You can run it manually or set up a cron job on your server."
    )
    if update.message:
        await update.message.reply_text(text, parse_mode="HTML", reply_markup=_main_menu_keyboard())
    else:
        await update.callback_query.edit_message_text(text, parse_mode="HTML", reply_markup=_main_menu_keyboard())


# ── /status ───────────────────────────────────────────────────────────────────

async def cmd_status(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    _ensure_user(update)
    record = db.get_user(user_id)

    stats = (
        f"👤 <b>Your Profile</b>\n"
        f"  Username: @{record.get('username') or '—'}\n"
        f"  Member since: {record.get('created_at','—')[:10]}\n"
        f"  Last active: {record.get('last_active','—')[:16].replace('T',' ')}\n"
        f"  Total jobs found: <b>{record.get('total_jobs_found', 0)}</b>\n\n"
        + _config_summary(user_id)
    )
    if update.message:
        await update.message.reply_text(stats, parse_mode="HTML", reply_markup=_main_menu_keyboard())
    else:
        await update.callback_query.edit_message_text(stats, parse_mode="HTML", reply_markup=_main_menu_keyboard())


# ── /run ──────────────────────────────────────────────────────────────────────

async def cmd_run(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    _ensure_user(update)

    msg = update.message or update.callback_query.message
    await msg.reply_text("🔍 Searching for jobs… this may take a minute.", parse_mode="HTML")

    new_jobs = scraper.fetch_new_jobs(user_id)

    if not new_jobs:
        await msg.reply_text(
            "✅ No new jobs found since your last run.\nTry again later or adjust your config.",
            reply_markup=_main_menu_keyboard(),
        )
        return

    await msg.reply_text(f"🎉 Found <b>{len(new_jobs)}</b> new job(s)! Sending now…", parse_mode="HTML")

    # Send each job as its own message (keeps them clean and copy-pasteable)
    for job in new_jobs:
        text = scraper.format_job(job)
        try:
            await context.bot.send_message(
                chat_id=user_id,
                text=text,
                parse_mode="HTML",
                disable_web_page_preview=True,
            )
        except Exception as e:
            logger.warning("Failed to send job message: %s", e)

    await context.bot.send_message(
        chat_id=user_id,
        text=f"✅ Done! Sent <b>{len(new_jobs)}</b> job(s).",
        parse_mode="HTML",
        reply_markup=_main_menu_keyboard(),
    )


# ── Config conversation ───────────────────────────────────────────────────────

async def cmd_config(update: Update, context: ContextTypes.DEFAULT_TYPE):
    _ensure_user(update)
    await update.message.reply_text(
        "⚙️ <b>Search Configuration</b>\n\nWhich parameter do you want to set?",
        parse_mode="HTML",
        reply_markup=_config_keyboard(),
    )
    return CHOOSE_PARAM


async def config_choose_param(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    key = query.data.split(":")[1]
    context.user_data["editing_param"] = key
    meta = PARAMS[key]
    await query.edit_message_text(
        f"Setting: <b>{meta['label']}</b>\n\n{meta['hint']}\n\nSend your value:",
        parse_mode="HTML",
    )
    return GET_VALUE


async def config_get_value(update: Update, context: ContextTypes.DEFAULT_TYPE):
    key  = context.user_data.get("editing_param")
    meta = PARAMS.get(key, {})
    raw  = update.message.text.strip()

    # ── Parse according to type ───────────────────────────────────────────────
    try:
        if meta.get("type") == "list":
            value = [s.strip() for s in raw.split(",") if s.strip()]
        elif meta.get("type") == "int":
            value = int(raw)
        elif meta.get("type") == "bool":
            value = raw.lower() in ("yes", "true", "1", "y")
        else:
            value = raw
    except ValueError:
        await update.message.reply_text(
            f"⚠️ Invalid value for <b>{meta.get('label','?')}</b>. Please try again or /start to cancel.",
            parse_mode="HTML",
        )
        return GET_VALUE

    db.set_search_param(update.effective_user.id, key, value)

    await update.message.reply_text(
        f"✅ <b>{meta['label']}</b> updated to: <code>{value}</code>\n\nSet another parameter or run a search.",
        parse_mode="HTML",
        reply_markup=_config_keyboard(),
    )
    return CHOOSE_PARAM


async def config_cancel(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("❌ Configuration cancelled.", reply_markup=_main_menu_keyboard())
    return ConversationHandler.END


# ── Inline button router ──────────────────────────────────────────────────────

async def button_router(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    data = query.data

    if data == "main_menu":
        await query.edit_message_text(
            "What would you like to do?",
            reply_markup=_main_menu_keyboard(),
        )
    elif data == "open_config":
        await query.edit_message_text(
            "⚙️ <b>Search Configuration</b>\n\nWhich parameter do you want to set?",
            parse_mode="HTML",
            reply_markup=_config_keyboard(),
        )
    elif data == "run_now":
        await cmd_run(update, context)
    elif data == "status":
        await cmd_status(update, context)
    elif data == "help":
        await cmd_help(update, context)


# ── App bootstrap ─────────────────────────────────────────────────────────────

def main():
    app = Application.builder().token(TOKEN).build()

    # Conversation: /config wizard
    config_conv = ConversationHandler(
        entry_points=[CommandHandler("config", cmd_config)],
        states={
            CHOOSE_PARAM: [CallbackQueryHandler(config_choose_param, pattern=r"^param:")],
            GET_VALUE:    [MessageHandler(filters.TEXT & ~filters.COMMAND, config_get_value)],
        },
        fallbacks=[CommandHandler("start", config_cancel)],
    )

    app.add_handler(CommandHandler("start",  cmd_start))
    app.add_handler(CommandHandler("help",   cmd_help))
    app.add_handler(CommandHandler("status", cmd_status))
    app.add_handler(CommandHandler("run",    cmd_run))
    app.add_handler(config_conv)
    app.add_handler(CallbackQueryHandler(button_router))

    logger.info("Bot started. Polling…")
    app.run_polling(drop_pending_updates=True)


if __name__ == "__main__":
    main()
