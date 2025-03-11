import os

from dotenv import load_dotenv
from telegram import Update
from telegram.ext import Application, CallbackContext, MessageHandler, filters

# Load environment variables
load_dotenv()
BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")

async def get_chat_id(update: Update, context: CallbackContext):
    if update.message:
        chat_id = update.message.chat_id  # Works for groups
    elif update.channel_post:
        chat_id = update.channel_post.chat_id  # Works for channels
    else:
        print("❌ No valid chat data found.")
        return

    print(f"Chat ID: {chat_id}")  # Print in console
    await update.effective_message.reply_text(f"Chat ID: `{chat_id}`", parse_mode="Markdown")

def main():
    app = Application.builder().token(BOT_TOKEN).build()
    app.add_handler(MessageHandler(filters.ALL, get_chat_id))
    print("Bot is running... Send a message in your channel/group to get the Chat ID.")
    app.run_polling()

if __name__ == "__main__":
    main()
