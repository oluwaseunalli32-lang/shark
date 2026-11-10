import os
import logging
import random
from datetime import time, timezone

from telegram import Update
from telegram.ext import Application, CommandHandler, ContextTypes
from dotenv import load_dotenv

# Load environment variables (for local testing)
load_dotenv()

# Enable logging
logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    level=logging.INFO,
)
logger = logging.getLogger(__name__)

# List of daily AI tips
AI_TIPS = [
    "💡 AI Tip: 'Zero-shot learning' means an AI can perform a task it was never explicitly trained on. Try asking ChatGPT to write in a completely new style!",
    "🧠 Did you know? Neural networks are inspired by the human brain, but they don't 'think'—they just find complex patterns in data.",
    "🚀 Free Tool: Use 'Hugging Face' to experiment with thousands of open-source AI models for free.",
    "🤖 AI Tip: When prompting an AI, always give it a 'role' (e.g., 'Act as a senior Python developer') to get much better answers.",
    "📊 AI is great at analyzing data, but it can 'hallucinate' (make up facts). Always double-check critical information!",
]


# --- COMMAND HANDLERS ---

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Sends a welcome message with AI disclosure (Telegram policy compliance)."""
    welcome_text = (
        "👋 Welcome to **Bonus Specialist**!\n\n"
        "🤖 **Transparency Note:** I am an AI-powered educational bot. "
        "I share free daily tips about Artificial Intelligence to help you learn.\n\n"
        "📚 Type /subscribe to get my daily AI tip at 09:00 UTC.\n"
        "🔒 Type /privacy to view our Privacy Policy.\n"
        "🛑 Type /stop to stop receiving messages."
    )
    await update.message.reply_text(welcome_text, parse_mode="Markdown")


async def privacy(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Provides a basic Privacy Policy (mandatory for Telegram ads)."""
    policy = (
        "🔒 **Privacy Policy for Bonus Specialist**\n\n"
        "1. **Data Collected:** We store your Telegram User ID solely to deliver "
        "the messages you requested.\n"
        "2. **Usage:** We do not sell your data or use it for third-party advertising.\n"
        "3. **Opt-out:** You can delete your data by typing /stop or blocking the bot.\n"
        "4. **Contact:** For any questions, contact the bot owner."
    )
    await update.message.reply_text(policy, parse_mode="Markdown")


async def subscribe(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Subscribes the user to the daily job queue."""
    chat_id = update.effective_chat.id

    # Check if a job already exists for this user
    current_jobs = context.job_queue.get_jobs_by_name(str(chat_id))
    if current_jobs:
        await update.message.reply_text(
            "✅ You are already subscribed to the daily AI tips!"
        )
        return

    # Schedule the daily job at 09:00 UTC
    context.job_queue.run_daily(
        send_daily_tip,
        time=time(hour=9, minute=0, tzinfo=timezone.utc),
        chat_id=chat_id,
        name=str(chat_id),
        data={"chat_id": chat_id},
    )
    await update.message.reply_text(
        "🎉 Subscribed! You will receive a new AI tip every day at 09:00 UTC. "
        "Type /stop to unsubscribe."
    )


async def stop(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Unsubscribes the user by removing their job."""
    chat_id = update.effective_chat.id
    current_jobs = context.job_queue.get_jobs_by_name(str(chat_id))

    if not current_jobs:
        await update.message.reply_text("You are not currently subscribed.")
        return

    for job in current_jobs:
        job.schedule_removal()

    await update.message.reply_text(
        "🔕 You have unsubscribed. You will no longer receive daily tips. "
        "Send /subscribe to rejoin."
    )


# --- DAILY JOB FUNCTION ---

async def send_daily_tip(context: ContextTypes.DEFAULT_TYPE):
    """Sends a random tip to the subscribed user."""
    job = context.job
    chat_id = job.data["chat_id"]

    # Pick a random tip
    tip = random.choice(AI_TIPS)

    try:
        await context.bot.send_message(
            chat_id=chat_id,
            text=tip,
            parse_mode="Markdown",
        )
    except Exception as e:
        logger.error(f"Failed to send tip to {chat_id}: {e}")


# --- MAIN APPLICATION ---

def main():
    # Get token from Environment Variables (Render provides this)
    token = os.getenv("BOT_TOKEN")
    if not token:
        raise ValueError(
            "No BOT_TOKEN found. Set it in Render Environment Variables."
        )

    # Build the Application
    application = Application.builder().token(token).build()

    # Add command handlers
    application.add_handler(CommandHandler("start", start))
    application.add_handler(CommandHandler("privacy", privacy))
    application.add_handler(CommandHandler("subscribe", subscribe))
    application.add_handler(CommandHandler("stop", stop))

    # Start the bot (polling mode is required for Background Workers)
    logger.info("Bot is starting...")
    application.run_polling(allowed_updates=Update.ALL_TYPES)


if __name__ == "__main__":
    main()
