import os

from dotenv import load_dotenv
from telegram import Update
from telegram.ext import Application, CallbackContext, MessageHandler, filters

# Load environment variables
load_dotenv()
BOT_TOKEN = "7228976753:AAHldynEq_drME-p1yzRKbMN5tmx5eWKkO8"

async def get_chat_id(update: Update, context: CallbackContext):
    chat_id = update.message.chat_id
    print(f"Chat ID: {chat_id}")  # Print it in the console
    await update.message.reply_text(f"Chatid: `{chat_id}`", parse_mode="Markdown")

def main():
    app = Application.builder().token(BOT_TOKEN).build()
    app.add_handler(MessageHandler(filters.ALL, get_chat_id))
    print("Bot is running... Send a message in your channel to get the Chat ID.")
    app.run_polling()

if __name__ == "__main__":
    main()
