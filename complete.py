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

# Load environment variables
load_dotenv()
BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
STRIPE_API_KEY = os.getenv("STRIPE_API_KEY")
STRIPE_WEBHOOK_SECRET = "whsec_zlO05B2igeusVhnfqUSvM7C2u3GKVvGF"
STRIPE_PRICE_ID = "price_1R1WTfKzVLA9Quz4vzJxsURX"
chat_id = "-1002402744201"  # Your Telegram group ID

bot = Bot(token=os.getenv("TELEGRAM_BOT_TOKEN"))
# telegram_bot = Application.builder().token(BOT_TOKEN).build()
# bot = telegram_bot.bot
# Initialize Flask app for Stripe Webhooks
app = Flask(__name__)
stripe.api_key = STRIPE_API_KEY

# Telegram Bot Setup
keyboard = [["/subscribe", "/transferfromdiscord", "/cancel"]]
reply_markup = ReplyKeyboardMarkup(keyboard, resize_keyboard=True, one_time_keyboard=False, input_field_placeholder="Choose an option")

start_message = (
    "Welcome! 👋\n\n"
    "Here are your available commands:\n"
    "📌 /subscribe - Subscribe to our services\n"
    "🔄 /transferfromdiscord - Input your Discord ID to gain access to Telegram channels at no extra charge\n"
    "❌ /cancel - Cancel your subscription (expires at the end of the calendar month)\n\n"
    "Please select an option below:"
)

# ✅ Function to generate and send a Stripe payment link
async def send_stripe_link(bot: Bot, user_id: int):
    try:
        checkout_session = stripe.checkout.Session.create(
            payment_method_types=['card'],
            line_items=[{
                'price': STRIPE_PRICE_ID,  # Replace with your Stripe price ID
                'quantity': 1,
            }],
            mode='subscription',
            success_url='https://your-success-url.com',  # Change this
            cancel_url='https://your-cancel-url.com',  # Change this
            client_reference_id=str(user_id),  # Store Telegram ID for tracking
            subscription_data={
                'metadata': {'telegram_id': str(user_id)}
            }
        )

        await bot.send_message(user_id, f"Click here to subscribe: {checkout_session.url}")
        print(f"✅ Sent Stripe subscription link to Telegram ID: {user_id}")

    except Exception as e:
        print(f"❌ Error sending Stripe link: {e}")

# ✅ Function to invite user to the group
async def invite_user_to_group(bot: Bot, user_id: int):
    try:
        invite_link = await bot.create_chat_invite_link(chat_id=chat_id, member_limit=1)
        await bot.send_message(user_id, f"invitelink:{invite_link.invite_link}(Do not share this with anyone else)")
        print(f"✅ Sent invite link to Telegram ID: {user_id}")

    except Exception as e:
        print(f"❌ Error inviting user {user_id}: {e}")

# ✅ Function to remove a user from the group when they cancel or fail payment
async def remove_user(bot: Bot, user_id: int):
    try:
        await bot.unban_chat_member(chat_id, user_id)  # Soft kick to allow rejoining later
        print(f"❌ Removed Telegram ID: {user_id} from Group {chat_id}")

    except Exception as e:
        print(f"⚠️ Error removing user {user_id}: {e}")

# ✅ Telegram Bot Commands
async def start(update: Update, context: CallbackContext):
    await update.message.reply_text(start_message, reply_markup=reply_markup)

async def subscribe(update: Update, context: CallbackContext):
    bot = context.bot
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
    bot = context.bot
    user_id = update.message.from_user.id
    print(f"User ID: {user_id} requested cancellation")
    # await remove_user(bot, user_id)
    print(f"Received cancel command from {user_id}")
    try:
        # Find the customer's subscription
        subscriptions = stripe.Subscription.list(limit=200)
        for subscription in subscriptions.auto_paging_iter():
            if subscription.metadata.get('telegram_id') == str(user_id):
                stripe.Subscription.delete(subscription.id)
                await update.message.reply_text("Your subscription has been canceled, and you have been removed from the group.")

    except Exception as e:
        await update.message.reply_text(f'Error canceling subscription, Are you sure your subscribed already? if you still need help, contact an admin')


# ✅ Stripe Webhook to Handle Subscription Events
@app.route('/webhook', methods=['POST'])
def stripe_webhook():
    payload = request.data
    sig_header = request.headers.get("Stripe-Signature")
    print(f"Received webhook event. Payload: {payload}")
    print(f"Signature Header: {sig_header}")

    try:
        event = stripe.Webhook.construct_event(
            payload, sig_header, STRIPE_WEBHOOK_SECRET, tolerance=600
        )
        print(f"Webhook event constructed successfully: {json.dumps(event, indent=2)}")
    except ValueError as e:
        print(f"Webhook construct event ValueError: {e}")
        return jsonify({'error': str(e)}), 400
    except stripe.error.SignatureVerificationError as e:
        print(f"Webhook construct event SignatureVerificationError: {e}")
        return jsonify({'error': str(e)}), 400

    # Extract event data
    event_type = event.get("type")
    # data = event.get("data", {}).get("object", {})
    # telegram_id = data.get("metadata", {}).get("telegram_id")


    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    # ✅ Handle Subscription Events
    if event_type == "customer.subscription.created":
        subscription = event['data']['object']
        telegram_id = subscription['metadata'].get('telegram_id', None)
        print(f"Inviting member id: {telegram_id}")
        loop.run_until_complete(invite_user_to_group(bot, int(telegram_id)))


    elif event_type == "customer.subscription.deleted" or event_type == "invoice.payment_failed":
        subscription = event['data']['object']
        telegram_id = subscription['metadata'].get('telegram_id', None)
        loop.run_until_complete(remove_user(bot, int(telegram_id)))

    return "", 200

# ✅ Run Flask Webhook Server
def run_flask():
    app.run(port=5004, debug=False, use_reloader=False)

def run_bot():
    bot_app = Application.builder().token(BOT_TOKEN).build()
    bot_app.add_handler(CommandHandler("start", start))
    bot_app.add_handler(CommandHandler("subscribe", subscribe))
    bot_app.add_handler(CommandHandler("cancel", cancel))

    bot_app.run_polling()
    print("🤖 Telegram Bot is running...")

# ✅ Run Telegram Bot & Flask Together Without Conflict

if __name__ == "__main__":
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)

    # Run the Flask app in a separate thread
    flask_thread = Thread(target=lambda: loop.run_until_complete(run_flask()))
    flask_thread.start()
    run_bot()

# def main():
#     loop = asyncio.new_event_loop()
#     asyncio.set_event_loop(loop)

#     bot_app = Application.builder().token(BOT_TOKEN).build()
#     bot_app.add_handler(CommandHandler("start", start))
#     bot_app.add_handler(CommandHandler("subscribe", subscribe))
#     bot_app.add_handler(CommandHandler("cancel", cancel))

#     print("🤖 Telegram Bot is running...")

#     # Start Flask in a separate thread to avoid event loop conflicts
#     flask_thread = Thread(target=run_flask, daemon=True)
#     flask_thread.start()
