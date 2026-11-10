import os
import sqlite3
import logging

from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import (
    Application,
    CommandHandler,
    CallbackQueryHandler,
    MessageHandler,
    ConversationHandler,
    ContextTypes,
    filters,
)

logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    level=logging.INFO,
)
logger = logging.getLogger(__name__)

# =========================================================
# Config
# =========================================================
BOT_TOKEN = os.environ.get("BOT_TOKEN", "")
OWNER_USERNAME = "ads_official123"          # without @
OWNER_IDS = {8048582254, 8923090068}
DB_PATH = "bot_data.db"

# Conversation states
EDIT_WELCOME, EDIT_REMINDER, EDIT_IMAGE, EDIT_LINK, EDIT_TEXT = range(5)

DEFAULTS = {
    "welcome_message":  "Welcome to Bonus Specialist! 🤖\nUse /subscribe for daily AI tips.",
    "reminder_message": "💡 Here's your AI tip:",
    "interval_hours":   "0",              # 0 = off, 5, 10
    "tip_image":        "",               # Telegram file_id
    "tip_link":         "",
    "tip_text":         "AI is transforming the world. Stay curious!",
}

# =========================================================
# DB layer
# =========================================================
def init_db():
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute("CREATE TABLE IF NOT EXISTS settings (key TEXT PRIMARY KEY, value TEXT)")
    c.execute("CREATE TABLE IF NOT EXISTS admins (user_id INTEGER PRIMARY KEY)")
    c.execute("CREATE TABLE IF NOT EXISTS subscribers (chat_id INTEGER PRIMARY KEY)")
    for k, v in DEFAULTS.items():
        c.execute("INSERT OR IGNORE INTO settings (key, value) VALUES (?, ?)", (k, v))
    for uid in OWNER_IDS:
        c.execute("INSERT OR IGNORE INTO admins (user_id) VALUES (?)", (uid,))
    conn.commit()
    conn.close()

def get_setting(key, default=None):
    conn = sqlite3.connect(DB_PATH)
    row = conn.execute("SELECT value FROM settings WHERE key=?", (key,)).fetchone()
    conn.close()
    return row[0] if row else default

def set_setting(key, value):
    conn = sqlite3.connect(DB_PATH)
    conn.execute("INSERT OR REPLACE INTO settings (key, value) VALUES (?, ?)", (key, str(value)))
    conn.commit()
    conn.close()

def get_admins():
    conn = sqlite3.connect(DB_PATH)
    rows = conn.execute("SELECT user_id FROM admins").fetchall()
    conn.close()
    return {r[0] for r in rows}

def get_subscribers():
    conn = sqlite3.connect(DB_PATH)
    rows = conn.execute("SELECT chat_id FROM subscribers").fetchall()
    conn.close()
    return [r[0] for r in rows]

def add_subscriber(chat_id):
    conn = sqlite3.connect(DB_PATH)
    conn.execute("INSERT OR IGNORE INTO subscribers (chat_id) VALUES (?)", (chat_id,))
    conn.commit()
    conn.close()

def remove_subscriber(chat_id):
    conn = sqlite3.connect(DB_PATH)
    conn.execute("DELETE FROM subscribers WHERE chat_id=?", (chat_id,))
    conn.commit()
    conn.close()

def is_subscribed(chat_id):
    conn = sqlite3.connect(DB_PATH)
    row = conn.execute("SELECT 1 FROM subscribers WHERE chat_id=?", (chat_id,)).fetchone()
    conn.close()
    return row is not None

# =========================================================
# Auth
# =========================================================
def is_admin(user):
    if user is None:
        return False
    if user.username and user.username.lower() == OWNER_USERNAME.lower():
        return True
    return user.id in get_admins()

# =========================================================
# Reminder job
# =========================================================
async def send_reminder(context: ContextTypes.DEFAULT_TYPE):
    bot = context.application.bot
    subs = get_subscribers()
    if not subs:
        return
    header  = get_setting("reminder_message", DEFAULTS["reminder_message"])
    text    = get_setting("tip_text", "")
    link    = get_setting("tip_link", "")
    image   = get_setting("tip_image", "")

    caption = f"{header}\n\n{text}".strip()
    kb = InlineKeyboardMarkup([[InlineKeyboardButton("🔗 Open Link", url=link)]]) if link else None

    for chat_id in subs:
        try:
            if image:
                await bot.send_photo(chat_id=chat_id, photo=image, caption=caption, reply_markup=kb)
            else:
                await bot.send_message(chat_id=chat_id, text=caption, reply_markup=kb)
        except Exception as e:
            logger.warning(f"send_reminder to {chat_id} failed: {e}")
            # fallback: text only
            if image:
                try:
                    await bot.send_message(chat_id=chat_id, text=caption, reply_markup=kb)
                except Exception:
                    pass

def reschedule_reminder(app: Application):
    for job in app.job_queue.get_jobs_by_name("daily_reminder"):
        job.schedule_removal()
    try:
        hours = int(get_setting("interval_hours", "0"))
    except ValueError:
        hours = 0
    if hours > 0:
        # first run after one full interval
        app.job_queue.run_repeating(
            send_reminder,
            interval=hours * 3600,
            first=hours * 3600,
            name="daily_reminder",
        )
        logger.info(f"Reminder scheduled every {hours}h")
    else:
        logger.info("Reminder disabled")

# =========================================================
# User commands
# =========================================================
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(get_setting("welcome_message", DEFAULTS["welcome_message"]))

async def privacy(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "Privacy Policy:\n"
        "This bot stores your chat ID only to deliver AI tips. "
        "No message content or personal data is stored. "
        "Use /stop anytime to unsubscribe."
    )

async def subscribe(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat_id = update.effective_chat.id
    if is_subscribed(chat_id):
        await update.message.reply_text("✅ You're already subscribed.")
        return
    add_subscriber(chat_id)
    hrs = get_setting("interval_hours", "0")
    if hrs == "0":
        await update.message.reply_text("✅ Subscribed! (Reminders are currently paused — admin will enable them.)")
    else:
        await update.message.reply_text(f"✅ Subscribed! You'll get a tip every {hrs} hours.")

async def stop(update: Update, context: ContextTypes.DEFAULT_TYPE):
    remove_subscriber(update.effective_chat.id)
    await update.message.reply_text("🛑 Unsubscribed.")

# =========================================================
# Admin panel UI
# =========================================================
def admin_panel_markup():
    hrs = get_setting("interval_hours", "0")
    label = {"0": "Off", "5": "Every 5h", "10": "Every 10h"}.get(hrs, f"{hrs}h")
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("✏️ Welcome Message", callback_data="adm_welcome")],
        [InlineKeyboardButton("✏️ Reminder Message", callback_data="adm_reminder")],
        [InlineKeyboardButton("🖼 Image",            callback_data="adm_image")],
        [InlineKeyboardButton("🔗 Link",             callback_data="adm_link")],
        [InlineKeyboardButton("📝 Tip Text",         callback_data="adm_text")],
        [InlineKeyboardButton(f"⏰ Interval: {label}", callback_data="adm_interval")],
        [InlineKeyboardButton("👥 Subscribers",      callback_data="adm_subs")],
        [InlineKeyboardButton("❌ Close",             callback_data="adm_close")],
    ])

def interval_markup():
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("🔕 Off",             callback_data="int_0")],
        [InlineKeyboardButton("⏰ Every 5 hours",   callback_data="int_5")],
        [InlineKeyboardButton("⏰ Every 10 hours",  callback_data="int_10")],
        [InlineKeyboardButton("⬅️ Back",            callback_data="adm_back")],
    ])

async def admin_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_admin(update.effective_user):
        await update.message.reply_text("❌ Not authorized.")
        return
    await update.message.reply_text("🛠 *Admin Panel*", parse_mode="Markdown", reply_markup=admin_panel_markup())

# --- Non-editing callbacks (menu / interval / subscribers) ---
async def admin_menu_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query
    await q.answer()
    if not is_admin(q.from_user):
        await q.edit_message_text("❌ Not authorized.")
        return

    data = q.data

    if data == "adm_back":
        await q.edit_message_text("🛠 *Admin Panel*", parse_mode="Markdown", reply_markup=admin_panel_markup())

    elif data == "adm_close":
        await q.edit_message_text("✅ Admin panel closed.")

    elif data == "adm_interval":
        await q.edit_message_text("⏰ Choose reminder interval:", reply_markup=interval_markup())

    elif data.startswith("int_"):
        hrs = data.split("_", 1)[1]
        set_setting("interval_hours", hrs)
        reschedule_reminder(context.application)
        label = {"0": "Off", "5": "Every 5 hours", "10": "Every 10 hours"}.get(hrs, hrs)
        await q.edit_message_text(f"✅ Interval set to: {label}\n\n🛠 *Admin Panel*",
                                  parse_mode="Markdown", reply_markup=admin_panel_markup())

    elif data == "adm_subs":
        await q.edit_message_text(f"👥 Subscribers: {len(get_subscribers())}\n\n🛠 *Admin Panel*",
                                  parse_mode="Markdown", reply_markup=admin_panel_markup())

# --- Entry point: click an "Edit …" button ---
async def admin_edit_entry(update: Update, context: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query
    await q.answer()
    if not is_admin(q.from_user):
        await q.edit_message_text("❌ Not authorized.")
        return ConversationHandler.END

    data = q.data

    if data == "adm_welcome":
        await q.edit_message_text(
            f"Current welcome message:\n\n{get_setting('welcome_message')}\n\n"
            "Send the new welcome message (or /cancel):"
        )
        return EDIT_WELCOME

    if data == "adm_reminder":
        await q.edit_message_text(
            f"Current reminder message:\n\n{get_setting('reminder_message')}\n\n"
            "Send the new reminder message (or /cancel):"
        )
        return EDIT_REMINDER

    if data == "adm_image":
        cur = "Currently set." if get_setting("tip_image") else "No image set."
        await q.edit_message_text(f"🖼 {cur}\n\nSend a new photo (or /cancel):")
        return EDIT_IMAGE

    if data == "adm_link":
        await q.edit_message_text(
            f"Current link: {get_setting('tip_link') or '(none)'}\n\n"
            "Send the new URL starting with http(s):// — or send 'none' to clear (or /cancel):"
        )
        return EDIT_LINK

    if data == "adm_text":
        await q.edit_message_text(
            f"Current tip text:\n\n{get_setting('tip_text')}\n\n"
            "Send the new tip text (or /cancel):"
        )
        return EDIT_TEXT

    return ConversationHandler.END

# --- State handlers ---
async def edit_welcome(update: Update, context: ContextTypes.DEFAULT_TYPE):
    set_setting("welcome_message", update.message.text)
    await update.message.reply_text("✅ Welcome message updated.", reply_markup=admin_panel_markup())
    return ConversationHandler.END

async def edit_reminder(update: Update, context: ContextTypes.DEFAULT_TYPE):
    set_setting("reminder_message", update.message.text)
    await update.message.reply_text("✅ Reminder message updated.", reply_markup=admin_panel_markup())
    return ConversationHandler.END

async def edit_image(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not update.message.photo:
        await update.message.reply_text("⚠️ Please send a photo.")
        return EDIT_IMAGE
    set_setting("tip_image", update.message.photo[-1].file_id)
    await update.message.reply_text("✅ Image updated.", reply_markup=admin_panel_markup())
    return ConversationHandler.END

async def edit_link(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text = update.message.text.strip()
    low = text.lower()
    if low in ("none", "clear", "remove"):
        set_setting("tip_link", "")
    elif not (text.startswith("http://") or text.startswith("https://")):
        await update.message.reply_text("⚠️ Send a URL starting with http:// or https:// (or 'none' to clear).")
        return EDIT_LINK
    else:
        set_setting("tip_link", text)
    await update.message.reply_text("✅ Link updated.", reply_markup=admin_panel_markup())
    return ConversationHandler.END

async def edit_text(update: Update, context: ContextTypes.DEFAULT_TYPE):
    set_setting("tip_text", update.message.text)
    await update.message.reply_text("✅ Tip text updated.", reply_markup=admin_panel_markup())
    return ConversationHandler.END

async def cancel(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("❌ Cancelled.", reply_markup=admin_panel_markup())
    return ConversationHandler.END

# =========================================================
# Main
# =========================================================
async def post_init(app: Application):
    init_db()
    reschedule_reminder(app)

def main():
    if not BOT_TOKEN:
        logger.error("BOT_TOKEN env var not set")
        return

    app = Application.builder().token(BOT_TOKEN).post_init(post_init).build()

    # User commands
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("privacy", privacy))
    app.add_handler(CommandHandler("subscribe", subscribe))
    app.add_handler(CommandHandler("stop", stop))

    # Admin command
    app.add_handler(CommandHandler("admin", admin_cmd))

    # Admin conversation (register BEFORE generic callback handler)
    conv = ConversationHandler(
        entry_points=[
            CallbackQueryHandler(
                admin_edit_entry,
                pattern="^(adm_welcome|adm_reminder|adm_image|adm_link|adm_text)$",
            ),
        ],
        states={
            EDIT_WELCOME:  [MessageHandler(filters.TEXT & ~filters.COMMAND, edit_welcome)],
            EDIT_REMINDER: [MessageHandler(filters.TEXT & ~filters.COMMAND, edit_reminder)],
            EDIT_IMAGE:    [MessageHandler(filters.PHOTO, edit_image)],
            EDIT_LINK:     [MessageHandler(filters.TEXT & ~filters.COMMAND, edit_link)],
            EDIT_TEXT:     [MessageHandler(filters.TEXT & ~filters.COMMAND, edit_text)],
        },
        fallbacks=[CommandHandler("cancel", cancel)],
    )
    app.add_handler(conv)

    # Menu / interval callbacks
    app.add_handler(CallbackQueryHandler(
        admin_menu_callback,
        pattern="^(adm_back|adm_close|adm_interval|adm_subs|int_0|int_5|int_10)$",
    ))

    logger.info("Bot starting…")
    app.run_polling()

if __name__ == "__main__":
    main()
