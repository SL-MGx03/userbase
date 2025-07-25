import os
import io
import logging
import time
from datetime import datetime
from dotenv import load_dotenv
from pymongo import MongoClient
from pymongo.errors import ConnectionFailure, ConfigurationError

from telegram import Update, WebAppInfo, InputFile, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import Application, CommandHandler, CallbackQueryHandler, ContextTypes

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
    """Gets an environment variable or raises an error if it's not found."""
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

# --- MongoDB Connection ---
try:
    client = MongoClient(MONGO_DATABASE_URL)
    db = client['sltoon_bot_db'] # Explicitly select the database
    telegram_users_collection = db.telegram_users
    # Verify connection
    client.admin.command('ping')
    logger.info(f"MongoDB connection successful to database '{db.name}'.")
except (ConnectionFailure, ConfigurationError) as e:
    logger.error(f"MongoDB connection or configuration failed: {e}")
    exit(1)

# --- Core Helper Functions ---
def is_admin(user_id: int) -> bool:
    """Checks if a user's ID is in the list of sudo owners."""
    return user_id in SUDO_OWNER_IDS

async def save_or_update_user(user):
    """Saves or updates a user's details in the MongoDB collection."""
    if not user: return
    try:
        result = telegram_users_collection.update_one(
            {'telegram_id': user.id},
            {
                '$set': {
                    'first_name': user.first_name, 'last_name': user.last_name,
                    'username': user.username, 'is_bot': user.is_bot,
                    'updated_at': datetime.utcnow()
                },
                '$setOnInsert': { 'telegram_id': user.id, 'created_at': datetime.utcnow() }
            },
            upsert=True # This creates the user if they don't exist
        )
        if result.upserted_id:
             logger.info(f"New user saved: {user.first_name} (ID: {user.id})")
        else:
             logger.info(f"User updated: {user.first_name} (ID: {user.id})")
    except Exception as e:
        logger.error(f"MongoDB error in save_or_update_user for user {user.id}: {e}")

# --- User-Facing Handlers ---

async def start_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handles the /start command. This is a primary way to register users."""
    user = update.effective_user
    await save_or_update_user(user)

    # Send a confirmation message
    await update.message.reply_text("✅ Thank you! Bot is updated and will receive all future updates.")

async def confirmation_button_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handles the click from the 'Confirm you are not a robot' button."""
    query = update.callback_query
    user = query.from_user
    
    # Acknowledge the button press to stop the loading icon
    await query.answer()
    
    # Save the user's data
    await save_or_update_user(user)
    
    # Edit the original message to show a confirmation
    await query.edit_message_text(text="✅ Confirmed! Thank you for staying with us.")

# --- SECURED Admin Commands ---

async def ping_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Admin command to check bot and DB latency."""
    if not is_admin(update.effective_user.id): return
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
    """Admin command to get a list of all user IDs."""
    if not is_admin(update.effective_user.id): return
    try:
        users_cursor = telegram_users_collection.find({}, {'telegram_id': 1, '_id': 0})
        user_ids = [str(doc['telegram_id']) for doc in users_cursor]
        if not user_ids:
            await update.message.reply_text("The database is empty. No users have registered yet.")
            return
        report_content = ", ".join(user_ids)
        file_buffer = io.BytesIO(report_content.encode('utf-8'))
        file_buffer.name = 'telegram_user_ids.txt'
        await update.message.reply_document(document=InputFile(file_buffer))
    except Exception as e:
        logger.error(f"Error in /id command: {e}")
        await update.message.reply_text("An error occurred while generating the report.")

async def full_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Admin command to get a detailed report of all users."""
    if not is_admin(update.effective_user.id): return
    try:
        users_cursor = telegram_users_collection.find({})
        report_lines = [f"Full Name, Username, Telegram ID"]
        user_count = 0
        for user in users_cursor:
            user_count += 1
            full_name = f"{user.get('first_name', '')} {user.get('last_name', '')}".strip()
            username = f"@{user.get('username')}" if user.get('username') else "N/A"
            report_lines.append(f"{full_name}, {username}, {user.get('telegram_id')}")
        
        if user_count == 0:
            await update.message.reply_text("The database is empty. No users have registered yet.")
            return
            
        report_content = "\n".join(report_lines)
        file_buffer = io.BytesIO(report_content.encode('utf-8'))
        file_buffer.name = 'full_user_report.txt'
        await update.message.reply_document(
            document=InputFile(file_buffer),
            caption=f"Total users registered: {user_count}"
        )
    except Exception as e:
        logger.error(f"Error in /full command: {e}")
        await update.message.reply_text("An error occurred while generating the report.")

# --- Main Bot Setup ---
def main():
    """Starts the bot and sets up the handlers."""
    application = Application.builder().token(TELEGRAM_BOT_TOKEN).build()
    
    # --- Register Handlers ---
    # 1. User registration handlers
    application.add_handler(CommandHandler("start", start_command))
    application.add_handler(CallbackQueryHandler(confirmation_button_handler, pattern='^confirm_robot_check$'))
    
    # 2. Admin command handlers
    application.add_handler(CommandHandler("ping", ping_command))
    application.add_handler(CommandHandler("id", id_command))
    application.add_handler(CommandHandler("full", full_command))

    utc_time_str = datetime.utcnow().strftime('%Y-%m-%d %H:%M:%S')
    logger.info("==================================================")
    logger.info(f"Bot starting up for user: {CURRENT_USER_LOGIN}")
    logger.info(f"Startup Time (UTC): {utc_time_str}")
    logger.info("Bot is now polling for updates...")
    logger.info("==================================================")
    
    application.run_polling()

if __name__ == '__main__':
    main()
