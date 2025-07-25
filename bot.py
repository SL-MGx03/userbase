import os
import io
import logging
from datetime import datetime
from dotenv import load_dotenv
from pymongo import MongoClient
from pymongo.errors import ConnectionFailure

from telegram import Update, WebAppInfo, InputFile
from telegram.ext import Application, CommandHandler, MessageHandler, filters, ContextTypes

# Load environment variables from a .env file for local development
load_dotenv()

# --- Logging Setup ---
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)
logger = logging.getLogger(__name__)

# --- Environment Variable and Database Setup ---
TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
SUDO_TELEGRAM_IDS_STR = os.getenv("SUDO_TELEGRAM_IDS")
MONGO_DATABASE_URL = os.getenv("MONGO_DATABASE_URL")

if not all([TELEGRAM_BOT_TOKEN, SUDO_TELEGRAM_IDS_STR, MONGO_DATABASE_URL]):
    raise ValueError("One or more required environment variables are not set.")

# Convert admin IDs to a set for fast checking
SUDO_OWNER_IDS = set(map(int, SUDO_TELEGRAM_IDS_STR.split(',')))

# --- MongoDB Connection ---
try:
    # This is the new connection logic for MongoDB
    client = MongoClient(MONGO_DATABASE_URL)
    # The database name will be taken from your connection string, or you can specify it
    db = client.get_database() 
    telegram_users_collection = db.telegram_users
    # The following line verifies that the connection is successful.
    client.admin.command('ping')
    logger.info("MongoDB connection successful.")
except ConnectionFailure as e:
    logger.error(f"MongoDB connection failed: {e}")
    raise

# --- Helper Function to Check for Admin ---
def is_admin(user_id: int) -> bool:
    return user_id in SUDO_OWNER_IDS

# --- User Data Handling ---
async def save_or_update_user(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Saves or updates user data in MongoDB using an efficient 'upsert'."""
    user = update.effective_user
    if not user:
        return

    try:
        # update_one with upsert=True is the perfect "find and update, or create if not found" operation
        telegram_users_collection.update_one(
            {'telegram_id': user.id},
            {
                '$set': {
                    'first_name': user.first_name,
                    'last_name': user.last_name,
                    'username': user.username,
                    'is_bot': user.is_bot,
                    'updated_at': datetime.utcnow()
                },
                '$setOnInsert': {
                    'telegram_id': user.id,
                    'created_at': datetime.utcnow()
                }
            },
            upsert=True
        )
    except Exception as e:
        logger.error(f"MongoDB error in save_or_update_user: {e}")

# --- Bot Command Handlers ---
async def start_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handles the /start command."""
    await update.message.reply_text(
        "Welcome! Tap the button below to open the SL Toon Web App.",
        reply_markup={
            "inline_keyboard": [[
                {"text": "🚀 Open SL Toon", "web_app": WebAppInfo(url="https://sltoon.slmgx.live")}
            ]]
        }
    )

async def id_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Admin command: sends a .txt file of all user IDs from MongoDB."""
    if not is_admin(update.effective_user.id):
        await update.message.reply_text("❌ Access Denied. This command is for sudo owners only.")
        return

    try:
        # Find all documents, but only return the 'telegram_id' field
        users_cursor = telegram_users_collection.find({}, {'telegram_id': 1, '_id': 0})
        user_ids = [str(doc['telegram_id']) for doc in users_cursor]

        if not user_ids:
            await update.message.reply_text("No users found in the database yet.")
            return

        report_content = ", ".join(user_ids)
        file_buffer = io.BytesIO(report_content.encode('utf-8'))
        file_buffer.name = 'telegram_user_ids.txt'
        
        await update.message.reply_document(document=InputFile(file_buffer))
    except Exception as e:
        logger.error(f"Error in /id command: {e}")
        await update.message.reply_text("An error occurred while generating the report.")

async def full_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Admin command: sends a detailed .txt report of all users from MongoDB."""
    if not is_admin(update.effective_user.id):
        await update.message.reply_text("❌ Access Denied. This command is for sudo owners only.")
        return

    try:
        users_cursor = telegram_users_collection.find({})
        report_lines = []
        for user in users_cursor:
            full_name = f"{user.get('first_name', '')} {user.get('last_name', '')}".strip()
            username = f"@{user.get('username')}" if user.get('username') else "N/A"
            report_lines.append(f"{full_name}, {username}, {user.get('telegram_id')}")

        if not report_lines:
            await update.message.reply_text("No users found in the database yet.")
            return
            
        report_content = "\n".join(report_lines)
        file_buffer = io.BytesIO(report_content.encode('utf-8'))
        file_buffer.name = 'full_user_report.txt'
        
        await update.message.reply_document(document=InputFile(file_buffer))
    except Exception as e:
        logger.error(f"Error in /full command: {e}")
        await update.message.reply_text("An error occurred while generating the report.")

# --- Main Bot Setup ---
def main():
    """Start the bot."""
    application = Application.builder().token(TELEGRAM_BOT_TOKEN).build()

    # Add handlers
    application.add_handler(CommandHandler("start", start_command))
    application.add_handler(CommandHandler("id", id_command))
    application.add_handler(CommandHandler("full", full_command))
    
    # This handler must be last. It catches all messages to save user data.
    application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, save_or_update_user))

    logger.info(f"Bot for SL-MGx03 starting up... (UTC: {datetime.utcnow().strftime('%Y-%m-%d %H:%M:%S')})")
    application.run_polling()

if __name__ == '__main__':
    main()
