import asyncio
import json
import os
from threading import Thread

import stripe
from dotenv import load_dotenv
from flask import Flask, jsonify, request
from telegram import ChatPermissions, ReplyKeyboardMarkup, Update
from telegram.ext import Application, CallbackContext, CommandHandler

# Load environment variables
load_dotenv()
BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
STRIPE_API_KEY = os.getenv("STRIPE_API_KEY")
STRIPE_WEBHOOK_SECRET = "whsec_zlO05B2igeusVhnfqUSvM7C2u3GKVvGF"
STRIPE_PRICE_ID = "price_1R1WTfKzVLA9Quz4vzJxsURX"
chat_id = "-1002402744201"

# Initialize Flask
app = Flask(__name__)
stripe.api_key = STRIPE_API_KEY

# Initialize Telegram Bot Application
telegram_app = Application.builder().token(BOT_TOKEN).build()

# ✅ Function to invite a user to the group
async def invite_user_to_group(user_id: int):
    try:
        invite_link = await telegram_app.bot.create_chat_invite_link(chat_id=chat_id, member_limit=1)
        await telegram_app.bot.send_message(user_id, f"Click this link to join the group: {invite_link.invite_link}")
        print(f"✅ Sent invite link to Telegram ID: {user_id}")
    except Exception as e:
        print(f"❌ Error inviting user {user_id}: {e}")

# ✅ Function to remove a user from the group when they cancel or fail payment
async def remove_user(user_id: int):
    try:
        await telegram_app.bot.unban_chat_member(chat_id, user_id)  # Soft kick to allow rejoining later
        print(f"❌ Removed Telegram ID: {user_id} from Group {chat_id}")
    except Exception as e:
        print(f"⚠️ Error removing user {user_id}: {e}")

# ✅ Telegram Bot Commands
async def start(update: Update, context: CallbackContext):
    start_message = (
        "Welcome! 👋\n\n"
        "Here are your available commands:\n"
        "📌 /subscribe - Subscribe to our services\n"
        "🔄 /transferfromdiscord - Input your Discord ID to gain access to Telegram channels at no extra charge\n"
        "❌ /cancel - Cancel your subscription (expires at the end of the calendar month)\n\n"
        "Please select an option below:"
    )
    await update.message.reply_text(start_message)

async def subscribe(update: Update, context: CallbackContext):
    user_id = update.message.from_user.id
    print(f"User ID: {user_id} requested subscription")
    await invite_user_to_group(user_id)

async def cancel(update: Update, context: CallbackContext):
    user_id = update.message.from_user.id
    print(f"User ID: {user_id} requested cancellation")
    await remove_user(user_id)
    await update.message.reply_text("Your subscription has been canceled, and you have been removed from the group.")

# ✅ Stripe Webhook to Handle Subscription Events
@app.route('/webhook', methods=['POST'])
def stripe_webhook():
    payload = request.data
    sig_header = request.headers.get("Stripe-Signature")

    print(f"🔔 Received webhook event: {payload}")

    try:
        event = stripe.Webhook.construct_event(payload, sig_header, STRIPE_WEBHOOK_SECRET, tolerance=600)
    except Exception as e:
        print(f"❌ Webhook Error: {e}")
        return jsonify({"error": str(e)}), 400

    event_type = event["type"]
    data = event["data"]["object"]
    telegram_id = data.get("metadata", {}).get("telegram_id")

    if telegram_id:
        telegram_id = int(telegram_id)

    print(f"🔔 Received Stripe event: {event_type} for Telegram ID: {telegram_id}")

    # ✅ Handle Subscription Events
    if event_type == "customer.subscription.created":
        asyncio.run_coroutine_threadsafe(invite_user_to_group(telegram_id), telegram_app.loop)
    elif event_type == "customer.subscription.deleted" or event_type == "invoice.payment_failed":
        asyncio.run_coroutine_threadsafe(remove_user(telegram_id), telegram_app.loop)

    return jsonify({"status": "success"}), 200

# ✅ Function to Run Flask Webhook Server
def run_flask():
    app.run(port=5004, debug=False, use_reloader=False)

# ✅ Run Telegram Bot & Flask Together Without Conflict
def run_bot():
    telegram_app.add_handler(CommandHandler("start", start))
    telegram_app.add_handler(CommandHandler("subscribe", subscribe))
    telegram_app.add_handler(CommandHandler("cancel", cancel))

    print("🤖 Telegram Bot is running...")
    telegram_app.run_polling()

if __name__ == "__main__":
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)

    # Start Flask in a separate thread
    flask_thread = Thread(target=lambda: loop.run_until_complete(run_flask()), daemon=True)
    flask_thread.start()

    # Start Telegram Bot
    run_bot()
