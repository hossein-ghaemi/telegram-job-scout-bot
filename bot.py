"""
bot.py — Telegram Job Scout Bot
All config flow uses pure CallbackQueryHandler + context.user_data.
No ConversationHandler — works from both /config command and menu buttons.
"""

import logging
import os
from dotenv import load_dotenv

from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import (
    Application,
    CommandHandler,
    CallbackQueryHandler,
    MessageHandler,
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

# ── Search parameters ─────────────────────────────────────────────────────────
PARAMS = {
    "site_name": {
        "label": "📡 Sites",
        "hint": "Comma-separated list.\nOptions: linkedin, indeed\nExample: <code>linkedin, indeed</code>",
        "type": "list",
    },
    "search_term": {
        "label": "🔍 Search Term",
        "hint": "Job title to search.\nExample: <code>AI Engineer</code>",
        "type": "str",
    },
    "google_search_term": {
        "label": "🌐 Google Term",
        "hint": "Full sentence for Google search.\nExample: <code>Internship Data Science jobs Germany</code>",
        "type": "str",
    },
    "location": {
        "label": "📍 Location",
        "hint": "City or country.\nExample: <code>Berlin</code> or <code>Germany</code>",
        "type": "str",
    },
    "results_wanted": {
        "label": "📊 Results Wanted",
        "hint": "How many jobs to fetch.\nExample: <code>50</code>",
        "type": "int",
    },
    "country_indeed": {
        "label": "🌍 Indeed Country",
        "hint": "Country for Indeed.\nExample: <code>germany</code>",
        "type": "str",
    },
    "job_type": {
        "label": "💼 Job Type",
        "hint": "One of:\n<code>fulltime</code>  <code>parttime</code>  <code>internship</code>  <code>contract</code>",
        "type": "str",
    },
    "linkedin_fetch_description": {
        "label": "📝 LinkedIn Description",
        "hint": "Fetch full description from LinkedIn? (slower)\nType: <code>yes</code> or <code>no</code>",
        "type": "bool",
    },
}

# ── Keyboards ─────────────────────────────────────────────────────────────────

def _main_menu_keyboard():
    return InlineKeyboardMarkup([
        [
            InlineKeyboardButton("⚙️ Configure Search", callback_data="open_config"),
            InlineKeyboardButton("▶️ Run Now",           callback_data="run_now"),
        ],
        [
            InlineKeyboardButton("📋 My Status", callback_data="status"),
            InlineKeyboardButton("❓ Help",       callback_data="help"),
        ],
    ])


def _config_keyboard():
    rows = []
    items = list(PARAMS.items())
    for i in range(0, len(items), 2):
        row = [
            InlineKeyboardButton(meta["label"], callback_data=f"param:{key}")
            for key, meta in items[i:i+2]
        ]
        rows.append(row)
    rows.append([InlineKeyboardButton("🔙 Back to Menu", callback_data="main_menu")])
    return InlineKeyboardMarkup(rows)


def _back_to_config_keyboard():
    return InlineKeyboardMarkup([[
        InlineKeyboardButton("🔙 Back to Config", callback_data="open_config"),
        InlineKeyboardButton("🏠 Main Menu",      callback_data="main_menu"),
    ]])

# ── Helpers ───────────────────────────────────────────────────────────────────

def _ensure_user(update: Update):
    user = update.effective_user
    db.update_user(user.id, {"username": user.username, "first_name": user.first_name})
    return db.get_user(user.id)


def _config_summary(user_id: int) -> str:
    cfg = db.get_search_config(user_id)
    lines = ["<b>⚙️ Current Search Config:</b>"]
    for key, meta in PARAMS.items():
        val = cfg.get(key, "—")
        if isinstance(val, list):
            val = ", ".join(val)
        lines.append(f"  {meta['label']}: <code>{val}</code>")
    return "\n".join(lines)


def _parse_value(raw: str, param_type: str):
    if param_type == "list":
        return [s.strip() for s in raw.split(",") if s.strip()]
    elif param_type == "int":
        return int(raw)
    elif param_type == "bool":
        return raw.lower() in ("yes", "true", "1", "y")
    else:
        return raw

# ── Commands ──────────────────────────────────────────────────────────────────

async def cmd_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    context.user_data.clear()   # reset any pending config state
    _ensure_user(update)
    name = update.effective_user.first_name or "there"
    await update.message.reply_text(
        f"👋 Hey <b>{name}</b>! I'm your <b>Job Scout Bot</b>.\n\n"
        "I scrape LinkedIn & Indeed and send only <i>new</i> jobs — no duplicates.\n\n"
        "What would you like to do?",
        parse_mode="HTML",
        reply_markup=_main_menu_keyboard(),
    )


async def cmd_config(update: Update, context: ContextTypes.DEFAULT_TYPE):
    context.user_data.pop("awaiting_param", None)
    _ensure_user(update)
    await update.message.reply_text(
        "⚙️ <b>Search Configuration</b>\n\nTap a parameter to change it:",
        parse_mode="HTML",
        reply_markup=_config_keyboard(),
    )


async def cmd_run(update: Update, context: ContextTypes.DEFAULT_TYPE):
    context.user_data.pop("awaiting_param", None)
    user_id = update.effective_user.id
    _ensure_user(update)
    msg = update.message
    await msg.reply_text("🔍 Searching for jobs… this may take a minute.")
    await _do_scrape(context, user_id, msg.chat_id)


async def cmd_status(update: Update, context: ContextTypes.DEFAULT_TYPE):
    context.user_data.pop("awaiting_param", None)
    user_id = update.effective_user.id
    _ensure_user(update)
    record = db.get_user(user_id)
    text = (
        f"👤 <b>Your Profile</b>\n"
        f"  Username: @{record.get('username') or '—'}\n"
        f"  Member since: {record.get('created_at','—')[:10]}\n"
        f"  Last active: {record.get('last_active','—')[:16].replace('T',' ')} UTC\n"
        f"  Total jobs found: <b>{record.get('total_jobs_found', 0)}</b>\n\n"
        + _config_summary(user_id)
    )
    await update.message.reply_text(text, parse_mode="HTML", reply_markup=_main_menu_keyboard())


async def cmd_help(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text = (
        "📖 <b>How to use this bot</b>\n\n"
        "<b>/start</b>  — Main menu\n"
        "<b>/config</b> — Configure search parameters\n"
        "<b>/run</b>    — Scrape jobs now\n"
        "<b>/status</b> — View your config &amp; stats\n\n"
        "Only <i>new</i> jobs are sent each run — no duplicates ever."
    )
    await update.message.reply_text(text, parse_mode="HTML", reply_markup=_main_menu_keyboard())

# ── Scrape helper (shared by button + command) ────────────────────────────────

async def _do_scrape(context: ContextTypes.DEFAULT_TYPE, user_id: int, chat_id: int):
    new_jobs = scraper.fetch_new_jobs(user_id)
    if not new_jobs:
        await context.bot.send_message(
            chat_id=chat_id,
            text="✅ No new jobs found since your last run.\nTry again later or adjust your config.",
            reply_markup=_main_menu_keyboard(),
        )
        return

    await context.bot.send_message(
        chat_id=chat_id,
        text=f"🎉 Found <b>{len(new_jobs)}</b> new job(s)! Sending now…",
        parse_mode="HTML",
    )
    for job in new_jobs:
        try:
            await context.bot.send_message(
                chat_id=chat_id,
                text=scraper.format_job(job),
                parse_mode="HTML",
                disable_web_page_preview=True,
            )
        except Exception as e:
            logger.warning("Failed to send job: %s", e)

    await context.bot.send_message(
        chat_id=chat_id,
        text=f"✅ Done! Sent <b>{len(new_jobs)}</b> job(s).",
        parse_mode="HTML",
        reply_markup=_main_menu_keyboard(),
    )

# ── Inline button handler ─────────────────────────────────────────────────────

async def button_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    data  = query.data
    user_id = update.effective_user.id
    _ensure_user(update)

    # ── Main menu navigation ──────────────────────────────────────────────────
    if data == "main_menu":
        context.user_data.pop("awaiting_param", None)
        await query.edit_message_text(
            "What would you like to do?",
            reply_markup=_main_menu_keyboard(),
        )

    elif data == "open_config":
        context.user_data.pop("awaiting_param", None)
        await query.edit_message_text(
            "⚙️ <b>Search Configuration</b>\n\nTap a parameter to change it:",
            parse_mode="HTML",
            reply_markup=_config_keyboard(),
        )

    elif data == "run_now":
        await query.edit_message_text("🔍 Searching for jobs… this may take a minute.")
        await _do_scrape(context, user_id, query.message.chat_id)

    elif data == "status":
        record = db.get_user(user_id)
        text = (
            f"👤 <b>Your Profile</b>\n"
            f"  Username: @{record.get('username') or '—'}\n"
            f"  Member since: {record.get('created_at','—')[:10]}\n"
            f"  Last active: {record.get('last_active','—')[:16].replace('T',' ')} UTC\n"
            f"  Total jobs found: <b>{record.get('total_jobs_found', 0)}</b>\n\n"
            + _config_summary(user_id)
        )
        await query.edit_message_text(text, parse_mode="HTML", reply_markup=_main_menu_keyboard())

    elif data == "help":
        await query.edit_message_text(
            "📖 <b>How to use this bot</b>\n\n"
            "<b>/start</b>  — Main menu\n"
            "<b>/config</b> — Configure search parameters\n"
            "<b>/run</b>    — Scrape jobs now\n"
            "<b>/status</b> — View your config &amp; stats\n\n"
            "Only <i>new</i> jobs are sent each run — no duplicates ever.",
            parse_mode="HTML",
            reply_markup=_main_menu_keyboard(),
        )

    # ── Param selected → ask for value ────────────────────────────────────────
    elif data.startswith("param:"):
        key = data.split(":", 1)[1]
        if key not in PARAMS:
            await query.answer("Unknown parameter.", show_alert=True)
            return
        context.user_data["awaiting_param"] = key
        meta = PARAMS[key]
        current = db.get_search_config(user_id).get(key, "—")
        if isinstance(current, list):
            current = ", ".join(current)
        await query.edit_message_text(
            f"⚙️ <b>{meta['label']}</b>\n\n"
            f"{meta['hint']}\n\n"
            f"Current value: <code>{current}</code>\n\n"
            f"✏️ <i>Type your new value below:</i>",
            parse_mode="HTML",
            reply_markup=_back_to_config_keyboard(),
        )

# ── Free-text message handler (captures param values) ────────────────────────

async def text_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    key = context.user_data.get("awaiting_param")

    # Not in config mode — give a nudge
    if not key:
        await update.message.reply_text(
            "Use the menu to interact with me 👇",
            reply_markup=_main_menu_keyboard(),
        )
        return

    meta = PARAMS[key]
    raw  = update.message.text.strip()

    try:
        value = _parse_value(raw, meta["type"])
    except ValueError:
        await update.message.reply_text(
            f"⚠️ Invalid value for <b>{meta['label']}</b>.\n\n{meta['hint']}\n\nTry again:",
            parse_mode="HTML",
        )
        return

    db.set_search_param(update.effective_user.id, key, value)
    context.user_data.pop("awaiting_param", None)

    display = ", ".join(value) if isinstance(value, list) else str(value)
    await update.message.reply_text(
        f"✅ <b>{meta['label']}</b> set to: <code>{display}</code>\n\nSet another or run a search.",
        parse_mode="HTML",
        reply_markup=_config_keyboard(),
    )

# ── App bootstrap ─────────────────────────────────────────────────────────────

def main():
    app = Application.builder().token(TOKEN).build()

    app.add_handler(CommandHandler("start",  cmd_start))
    app.add_handler(CommandHandler("config", cmd_config))
    app.add_handler(CommandHandler("run",    cmd_run))
    app.add_handler(CommandHandler("status", cmd_status))
    app.add_handler(CommandHandler("help",   cmd_help))
    app.add_handler(CallbackQueryHandler(button_handler))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, text_handler))

    logger.info("Bot started. Polling…")
    app.run_polling(drop_pending_updates=True)


if __name__ == "__main__":
    main()