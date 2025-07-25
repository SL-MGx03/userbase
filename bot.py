import os
import io
import logging
import time
from datetime import datetime
from dotenv import load_dotenv
from pymongo import MongoClient
from pymongo.errors import ConnectionFailure, ConfigurationError

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

# --- Environment Variable Setup ---
def get_env_var(var_name):
    value = os.getenv(var_name)
    if not value:
        raise ValueError(f"CRITICAL ERROR: The environment variable '{var_name}' is not set.")
    return value

try:
    TELEGRAM_BOT_TOKEN = get_env_var("TELEGRAM_BOT_TOKEN")
    SUDO_TELEGRAM_IDS_STR = get_env_var("SUDO_TELEGRAM_IDS")
    MONGO_DATABASE_URL = get_env_var("MONGO_DATABASE_URL")
except ValueError as e:
    logger.error(e)
    exit(1)

CURRENT_USER_LOGIN = "SL-MGx03"
SUDO_OWNER_IDS = set(map(int, SUDO_TELEGRAM_IDS_STR.split(',')))

# --- (IMPROVED) MongoDB Connection ---
try:
    client = MongoClient(MONGO_DATABASE_URL)
    
    # The line below is the fix.
    # We explicitly select the database named 'sltoon_bot_db'.
    # If this database doesn't exist, MongoDB will create it automatically on the first write.
    db = client['sltoon_bot_db']
    
    telegram_users_collection = db.telegram_users
    
    # Verify the connection is successful.
    client.admin.command('ping')
    logger.info(f"MongoDB connection successful to database '{db.name}'.")

except (ConnectionFailure, ConfigurationError) as e:
    logger.error(f"MongoDB connection or configuration failed: {e}")
    logger.error("Please ensure your MONGO_DATABASE_URL is correct and that the cluster is active.")
    exit(1)


# --- Helper Function to Check for Admin ---
def is_admin(user_id: int) -> bool:
    return user_id in SUDO_OWNER_IDS

# --- User Data Handling (Existing Feature) ---
async def save_or_update_user(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    if not user: return
    try:
        telegram_users_collection.update_one(
            {'telegram_id': user.id},
            {
                '$set': {
                    'first_name': user.first_name, 'last_name': user.last_name,
                    'username': user.username, 'is_bot': user.is_bot,
                    'updated_at': datetime.utcnow()
                },
                '$setOnInsert': { 'telegram_id': user.id, 'created_at': datetime.utcnow() }
            },
            upsert=True
        )
    except Exception as e:
        logger.error(f"MongoDB error in save_or_update_user: {e}")

# --- Bot Command Handlers ---

async def start_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "Welcome! Tap the button below to open the SL Toon Web App.",
        reply_markup={
            "inline_keyboard": [[
                {"text": "🚀 Open SL Toon", "web_app": WebAppInfo(url="https://sltoon.slmgx.live")}
            ]]
        }
    )

async def ping_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    start_time = time.monotonic()
    message = await update.message.reply_text("Pinging...")
    bot_latency = (time.monotonic() - start_time) * 1000
    db_start_time = time.monotonic()
    try:
        db.command('ping')
        db_latency = (time.monotonic() - db_start_time) * 1000
        db_status = f"Database ping: {db_latency:.2f} ms"
    except Exception as e:
        logger.error(f"Database ping failed: {e}")
        db_status = "Database ping: FAILED"
    await message.edit_text(f"Pong! 🏓\n\nBot latency: {bot_latency:.2f} ms\n{db_status}")

async def id_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_admin(update.effective_user.id):
        await update.message.reply_text("❌ Access Denied. This command is for sudo owners only.")
        return
    try:
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
    application = Application.builder().token(TELEGRAM_BOT_TOKEN).build()
    application.add_handler(CommandHandler("start", start_command))
    application.add_handler(CommandHandler("ping", ping_command))
    application.add_handler(CommandHandler("id", id_command))
    application.add_handler(CommandHandler("full", full_command))
    application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, save_or_update_user))

    utc_time_str = datetime.utcnow().strftime('%Y-%m-%d %H:%M:%S')
    logger.info("==================================================")
    logger.info(f"Bot starting up for user: {CURRENT_USER_LOGIN}")
    logger.info(f"Startup Time (UTC): {utc_time_str}")
    logger.info("==================================================")
    
    application.run_polling()

if __name__ == '__main__':
    main()
