import os

from dotenv import load_dotenv
from telegram import Bot, ChatPermissions, ReplyKeyboardMarkup, Update
from telegram.ext import (Application, CallbackContext, CommandHandler,
                          MessageHandler, filters)

chat_id = "-1002251747215"

# Load environment variables
load_dotenv()
BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")  # Make sure to set this in a .env file

keyboard = [["/subscribe", "/transferfromdiscord", "/cancel"]]
reply_markup = ReplyKeyboardMarkup(keyboard, resize_keyboard=True, one_time_keyboard=False, input_field_placeholder="Choose an option")


start_message =(
        "Welcome! 👋\n\n"
        "Here are your available commands:\n"
        "📌 /subscribe - Subscribe to our services\n"
        "🔄 /transferfromdiscord - Input your Discord ID to gain access to Telegram channels at no extra charge\n"
        "❌ /cancel - Cancel your subscription (expires at the end of the calendar month)\n\n"
        "Please select an option below:"
    )


async def invite_user_to_group(bot: Bot, chat_id: int, user_id: int):
    try:
        # Generate a single-use invite link
        invite_link = await bot.create_chat_invite_link(chat_id=chat_id, member_limit=1)
        # Send the invite link to the user
        await bot.send_message(user_id, f"Click this link to join the group: {invite_link.invite_link}")

        print(f"✅ Sent invite link to Telegram ID: {user_id}")

    except Exception as e:
        print(f"❌ Error inviting user {user_id}: {e}")

async def cancel(update: Update, context:CallbackContext):
    user_id = update.message.from_user.id
    bot = Bot(token=os.getenv("TELEGRAM_BOT_TOKEN"))

    try:
        # await bot.ban_chat_member(chat_id=chat_id, user_id=user_id)
        await bot.unban_chat_member(chat_id=chat_id, user_id=user_id)

        # await bot.kick_chat_member(chat_id=chat_id, user_id=user_id)
        await update.message.reply_text("You have been removed from the group")
    except Exception as e:
        print(f"ERROR removing user: {user_id} from group: {chat_id}", e)


async def start(update: Update, context: CallbackContext):
    await update.message.reply_text(start_message, reply_markup=reply_markup)

# Define the /subscribe command handler
async def subscribe(update: Update, context: CallbackContext):
    bot = Bot(token=os.getenv("TELEGRAM_BOT_TOKEN"))
    user_id = update.message.from_user.id  # Get user ID
    print(f"User ID: {user_id}")
    await update.message.reply_text("Hello")
    await invite_user_to_group(context.bot, chat_id=chat_id, user_id=user_id)

# Main function to start the bot
def main():
    app = Application.builder().token(BOT_TOKEN).build()
    # Add command handler
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("subscribe", subscribe))
    app.add_handler(CommandHandler("cancel", cancel))

    print("Bot is running...")
    app.run_polling()

if __name__ == "__main__":
    main()
