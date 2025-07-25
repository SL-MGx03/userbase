import os
import io
import logging
import time
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
CURRENT_USER_LOGIN = "SL-MGx03" # As requested

if not all([TELEGRAM_BOT_TOKEN, SUDO_TELEGRAM_IDS_STR, MONGO_DATABASE_URL]):
    raise ValueError("One or more required environment variables are not set.")

# Convert admin IDs to a set for fast checking
SUDO_OWNER_IDS = set(map(int, SUDO_TELEGRAM_IDS_STR.split(',')))

# --- MongoDB Connection ---
try:
    client = MongoClient(MONGO_DATABASE_URL)
    db = client.get_database() 
    telegram_users_collection = db.telegram_users
    client.admin.command('ping')
    logger.info("MongoDB connection successful.")
except ConnectionFailure as e:
    logger.error(f"MongoDB connection failed: {e}")
    raise

# --- Helper Function to Check for Admin ---
def is_admin(user_id: int) -> bool:
    return user_id in SUDO_OWNER_IDS

# --- User Data Handling (Existing Feature) ---
async def save_or_update_user(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Saves or updates user data in MongoDB using an efficient 'upsert'."""
    user = update.effective_user
    if not user:
        return
    try:
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
                '$setOnInsert': { 'telegram_id': user.id, 'created_at': datetime.utcnow() }
            },
            upsert=True
        )
    except Exception as e:
        logger.error(f"MongoDB error in save_or_update_user: {e}")

# --- Bot Command Handlers ---

async def start_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handles the /start command and shows the Web App button."""
    await update.message.reply_text(
        "Welcome! Tap the button below to open the SL Toon Web App.",
        reply_markup={
            "inline_keyboard": [[
                {"text": "🚀 Open SL Toon", "web_app": WebAppInfo(url="https://sltoon.slmgx.live")}
            ]]
        }
    )

async def ping_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """(NEW) Checks bot and database latency."""
    start_time = time.
