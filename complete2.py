import asyncio
import json
import os
from threading import Thread

import stripe
from dotenv import load_dotenv
from flask import Flask, jsonify, request
from telegram import (Bot, ChatJoinRequest, ChatPermissions,
                      ReplyKeyboardMarkup, Update)
from telegram.ext import (Application, CallbackContext, CommandHandler,
                          MessageHandler, filters)

# ------------------------------------------------------------------------------
# 1) LOAD ENV & CONFIG
# ------------------------------------------------------------------------------
load_dotenv()
BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
STRIPE_API_KEY = os.getenv("STRIPE_API_KEY")
STRIPE_WEBHOOK_SECRET = "whsec_zlO05B2igeusVhnfqUSvM7C2u3GKVvGF"
STRIPE_PRICE_ID = "price_1R1WTfKzVLA9Quz4vzJxsURX"
chat_id = "-1002402744201"  # Your Telegram group ID

# Create the PTB Application
bot_app = Application.builder().token(BOT_TOKEN).build()
bot = bot_app.bot

# GLOBAL to store the main event loop used by the bot
MAIN_LOOP = None

# Initialize Flask
app = Flask(__name__)
stripe.api_key = STRIPE_API_KEY

# ------------------------------------------------------------------------------
# 2) BOT SETUP & HANDLERS
# ------------------------------------------------------------------------------
keyboard = [["/subscribe", "/transferfromdiscord", "/cancel"]]
reply_markup = ReplyKeyboardMarkup(
    keyboard,
    resize_keyboard=True,
    one_time_keyboard=False,
    input_field_placeholder="Choose an option"
)

start_message = (
    "Welcome! 👋\n\n"
    "Here are your available commands:\n"
    "📌 /subscribe - Subscribe to our services\n"
    "🔄 /transferfromdiscord - Input your Discord ID to gain access to Telegram channels at no extra charge\n"
    "❌ /cancel - Cancel your subscription (expires at the end of the calendar month)\n\n"
    "Please select an option below:"
)

async def start(update: Update, context: CallbackContext):
    await update.message.reply_text(start_message, reply_markup=reply_markup)

async def subscribe(update: Update, context: CallbackContext):
    user_id = update.message.from_user.id
    print(f"User ID: {user_id} requested subscription")
    await send_stripe_link(bot, user_id)

async def approve_join_request(update: ChatJoinRequest, context: CallbackContext):
    """Automatically approves join requests"""
    try:
        await update.approve()
        print(f"✅ Approved join request from {update.from_user.id}")
    except Exception as e:
        print(f"❌ Error approving join request: {e}")

async def cancel(update: Update, context: CallbackContext):
    user_id = update.message.from_user.id
    print(f"User ID: {user_id} requested cancellation")
    try:
        # Find the customer's subscription
        subscriptions = stripe.Subscription.list(limit=200)
        for subscription in subscriptions.auto_paging_iter():
            if subscription.metadata.get('telegram_id') == str(user_id):
                stripe.Subscription.delete(subscription.id)
                await update.message.reply_text(
                    "Your subscription has been canceled, and you have been removed from the group."
                )
                return
        # If no active subscription found:
        await update.message.reply_text(
            "No active subscription found. If you still need help, contact an admin."
        )
    except Exception as e:
        await update.message.reply_text(
            "Error canceling subscription. Are you sure you were subscribed? If you still need help, contact an admin."
        )
        print(f"Error on cancellation: {e}")

# ------------------------------------------------------------------------------
# 3) ASYNC BOT FUNCTIONS
# ------------------------------------------------------------------------------
async def send_stripe_link(bot: Bot, user_id: int):
    """Sends user a Stripe checkout link."""
    try:
        checkout_session = stripe.checkout.Session.create(
            payment_method_types=['card'],
            line_items=[{
                'price': STRIPE_PRICE_ID,
                'quantity': 1,
            }],
            mode='subscription',
            success_url='https://your-success-url.com',
            cancel_url='https://your-cancel-url.com',
            client_reference_id=str(user_id),
            subscription_data={'metadata': {'telegram_id': str(user_id)}}
        )
        await bot.send_message(
            user_id,
            f"Click here to subscribe: {checkout_session.url}"
        )
        print(f"✅ Sent Stripe subscription link to Telegram ID: {user_id}")
    except Exception as e:
        print(f"❌ Error sending Stripe link: {e}")

async def invite_user_to_group(bot: Bot, user_id: int):
    """Creates a single-use invite link and sends it to the user."""
    try:
        invite_link = await bot.create_chat_invite_link(
            chat_id=chat_id,
            member_limit=1
        )
        await bot.send_message(
            user_id,
            f"invitelink:{invite_link.invite_link} (Do not share this with anyone else!)"
        )
        print(f"✅ Sent invite link to Telegram ID: {user_id}")
    except Exception as e:
        print(f"❌ Error inviting user {user_id}: {e}")

async def remove_user(bot: Bot, user_id: int):
    """Unbans (kicks) a user from the group so they can't read messages."""
    try:
        await bot.unban_chat_member(chat_id, user_id)
        print(f"❌ Removed Telegram ID: {user_id} from Group {chat_id}")
    except Exception as e:
        print(f"⚠️ Error removing user {user_id}: {e}")

# ------------------------------------------------------------------------------
# 4) FLASK WEBHOOK
# ------------------------------------------------------------------------------
@app.route('/webhook', methods=['POST'])
def stripe_webhook():
    """Receives Stripe webhooks and schedules actions on the bot's event loop."""
    payload = request.data
    sig_header = request.headers.get("Stripe-Signature")
    print(f"\n[FLASK] Received webhook event. Payload: {payload}")
    print(f"[FLASK] Signature Header: {sig_header}")

    try:
        event = stripe.Webhook.construct_event(
            payload, sig_header, STRIPE_WEBHOOK_SECRET, tolerance=600
        )
        print(f"[FLASK] Webhook event constructed successfully:")
        print(json.dumps(event, indent=2))
    except Exception as e:
        print(f"[FLASK] Error verifying webhook: {e}")
        return jsonify({'error': str(e)}), 400

    event_type = event.get("type")
    subscription = event.get("data", {}).get("object", {})
    telegram_id = subscription.get("metadata", {}).get("telegram_id")

    if telegram_id:
        telegram_id = int(telegram_id)
        print(f"[FLASK] Telegram ID from metadata: {telegram_id}")

    # Schedule tasks on the bot's loop (MAIN_LOOP)
    # by calling MAIN_LOOP.call_soon_threadsafe(...)
    if event_type == "customer.subscription.created":
        print(f"[FLASK] Inviting member id: {telegram_id}")
        MAIN_LOOP.call_soon_threadsafe(
            lambda: bot_app.create_task(invite_user_to_group(bot, telegram_id))
        )

    elif event_type in ("customer.subscription.deleted", "invoice.payment_failed"):
        print(f"[FLASK] Removing member id: {telegram_id}")
        MAIN_LOOP.call_soon_threadsafe(
            lambda: bot_app.create_task(remove_user(bot, telegram_id))
        )

    return "", 200

def run_flask():
    """Runs the Flask server in a blocking call, used in a background thread."""
    app.run(port=5004, debug=False, use_reloader=False)

# ------------------------------------------------------------------------------
# 5) ASYNC MAIN FUNCTION FOR THE BOT
# ------------------------------------------------------------------------------
async def async_main():
    """Manually initialize, start & poll the bot without blocking the loop."""
    global MAIN_LOOP
    MAIN_LOOP = asyncio.get_running_loop()  # <- Store the bot's loop globally

    # 1) Initialize
    await bot_app.initialize()

    # 2) Add handlers
    bot_app.add_handler(CommandHandler("start", start))
    bot_app.add_handler(CommandHandler("subscribe", subscribe))
    bot_app.add_handler(CommandHandler("cancel", cancel))
    # If you want to auto-approve join requests, you'd need:
    # from telegram.ext import ChatJoinRequestHandler
    # bot_app.add_handler(ChatJoinRequestHandler(approve_join_request))

    # 3) Start the bot
    await bot_app.start()

    # 4) Start polling for updates
    await bot_app.updater.start_polling()

    print("🤖 Telegram Bot is running... (async_main)")

    # 5) Keep running until we decide to stop
    stop_event = asyncio.Event()
    await stop_event.wait()

    # 6) Stop gracefully
    await bot_app.updater.stop()
    await bot_app.stop()
    await bot_app.shutdown()

# ------------------------------------------------------------------------------
# 6) ENTRY POINT
# ------------------------------------------------------------------------------
if __name__ == "__main__":
    # Create ONE main event loop for both Flask & Bot
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)

    # Start Flask in a separate thread so it doesn't block the bot
    flask_thread = Thread(target=run_flask, daemon=True)
    flask_thread.start()

    # Run the bot in the same loop
    loop.run_until_complete(async_main())
    print("Bot has shut down.")
