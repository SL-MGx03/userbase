import os
import io
import logging
from dotenv import load_dotenv

from telegram import Update, WebAppInfo, InputFile
from telegram.ext import Application, CommandHandler, MessageHandler, filters, ContextTypes

from models import SessionLocal, TelegramUser, init_db

# Load environment variables from a .env file for local development
load_dotenv()

# Set up logging to see bot activity and errors
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)
logger = logging.getLogger(__name__)

# --- Environment Variable Validation ---
TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
SUDO_TELEGRAM_IDS_STR = os.getenv("SUDO_TELEGRAM_IDS")

if not TELEGRAM_BOT_TOKEN or not SUDO_TELEGRAM_IDS_STR:
    raise ValueError("TELEGRAM_BOT_TOKEN and SUDO_TELEGRAM_IDS must be set in environment variables.")

# Convert the comma-separated string of IDs into a set of integers for fast lookups
SUDO_OWNER_IDS = set(map(int, SUDO_TELEGRAM_IDS_STR.split(',')))


# --- Helper Function to Check for Admin ---
def is_admin(user_id: int) -> bool:
    """Checks if a user's ID is in the list of sudo owners."""
    return user_id in SUDO_OWNER_IDS


# --- User Data Handling ---
async def save_or_update_user(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """
    This function runs on every message to save user data to the database.
    It's our middleware for user tracking.
    """
    user = update.effective_user
    if not user:
        return

    db_session = SessionLocal()
    try:
        db_user = db_session.query(TelegramUser).filter(TelegramUser.telegram_id == user.id).first()

        if db_user:
            # User exists, update their info if it has changed
            db_user.first_name = user.first_name
            db_user.last_name = user.last_name
            db_user.username = user.username
        else:
            # User is new, create a new record
            new_user = TelegramUser(
                telegram_id=user.id,
                first_name=user.first_name,
                last_name=user.last_name,
                username=user.username,
                is_bot=user.is_bot
            )
            db_session.add(new_user)
        
        db_session.commit()
    except Exception as e:
        logger.error(f"Database error in save_or_update_user: {e}")
        db_session.rollback()
    finally:
        db_session.close()


# --- Bot Command Handlers ---
async def start_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handles the /start command."""
    await update.message.reply_text(
        "Welcome! Tap the button below to open the SL Toon Web App.",
        reply_markup={
            "inline_keyboard": [[
                {
                    "text": "🚀 Open SL Toon",
                    "web_app": WebAppInfo(url="https://sltoon.slmgx.live")
                }
            ]]
        }
    )

async def id_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Admin command: sends a .txt file of all user IDs."""
    if not is_admin(update.effective_user.id):
        await update.message.reply_text("❌ Access Denied. This command is for sudo owners only.")
        return

    db_session = SessionLocal()
    try:
        users = db_session.query(TelegramUser.telegram_id).all()
        if not users:
            await update.message.reply_text("No users found in the database yet.")
            return

        user_ids = ", ".join(str(user.telegram_id) for user in users)
        
        # Create an in-memory file
        file_buffer = io.BytesIO(user_ids.encode('utf-8'))
        file_buffer.name = 'telegram_user_ids.txt'
        
        await update.message.reply_document(document=InputFile(file_buffer))

    except Exception as e:
        logger.error(f"Error in /id command: {e}")
        await update.message.reply_text("An error occurred while generating the report.")
    finally:
        db_session.close()

async def full_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Admin command: sends a detailed .txt report of all users."""
    if not is_admin(update.effective_user.id):
        await update.message.reply_text("❌ Access Denied. This command is for sudo owners only.")
        return

    db_session = SessionLocal()
    try:
        users = db_session.query(TelegramUser).all()
        if not users:
            await update.message.reply_text("No users found in the database yet.")
            return

        report_lines = []
        for user in users:
            full_name = f"{user.first_name} {user.last_name or ''}".strip()
            username = f"@{user.username}" if user.username else "N/A"
            report_lines.append(f"{full_name}, {username}, {user.telegram_id}")

        report_content = "\n".join(report_lines)
        
        # Create an in-memory file
        file_buffer = io.BytesIO(report_content.encode('utf-8'))
        file_buffer.name = 'full_user_report.txt'
        
        await update.message.reply_document(document=InputFile(file_buffer))

    except Exception as e:
        logger.error(f"Error in /full command: {e}")
        await update.message.reply_text("An error occurred while generating the report.")
    finally:
        db_session.close()


# --- Main Bot Setup ---
def main():
    """Start the bot."""
    # First, ensure the database table exists.
    init_db()

    application = Application.builder().token(TELEGRAM_BOT_TOKEN).build()

    # Add handlers
    application.add_handler(CommandHandler("start", start_command))
    application.add_handler(CommandHandler("id", id_command))
    application.add_handler(CommandHandler("full", full_command))
    
    # This handler must be last. It catches all messages to save user data.
    application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, save_or_update_user))

    logger.info("Bot is starting...")
    application.run_polling()


if __name__ == '__main__':
    main()
