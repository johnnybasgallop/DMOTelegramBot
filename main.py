# main.py
import asyncio
import json
import os
from datetime import datetime
from threading import Thread

import stripe
from dotenv import load_dotenv
from flask import Flask, jsonify, request
from telegram import (Bot, ChatJoinRequest, ChatPermissions,
                      ReplyKeyboardMarkup, Update)
from telegram.ext import (Application, CallbackContext, CommandHandler,
                          MessageHandler, filters)

# Import Google Sheets helpers
from google_sheets import add_data_to_sheet, init_sheet, update_data_in_sheet

# from telegram.helpers import escape_markdown  # if you need it


# ------------------------------------------------------------------------------
# 1) LOAD ENV & CONFIG
# ------------------------------------------------------------------------------
load_dotenv()
BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
STRIPE_API_KEY = os.getenv("STRIPE_API_KEY")
STRIPE_WEBHOOK_SECRET = os.getenv("STRIPE_WEBHOOK_KEY")
STRIPE_PRICE_ID = os.getenv("STRIPE_PRICE_ID")
chat_id = os.getenv("CHANNEL_ID")

# Initialize the Google Sheet
sheet = init_sheet()

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
keyboard = [["/subscribe", "/cancel"]]
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
    """Automatically approves join requests, if you want to use it."""
    try:
        await update.approve()
        print(f"✅ Approved join request from {update.from_user.id}")
    except Exception as e:
        print(f"❌ Error approving join request: {e}")

async def cancel(update: Update, context: CallbackContext):
    """
    /cancel command: Sets subscription to cancel at period end,
    updates the sheet to 'Cancel at Period End'.
    """
    user_id = update.message.from_user.id
    user_id_str = str(user_id)
    print(f"User ID: {user_id} requested cancellation")

    try:
        subscriptions = stripe.Subscription.list(limit=200)
        for subscription in subscriptions.auto_paging_iter():
            if subscription.metadata.get('telegram_id') == user_id_str:
                # schedule end-of-billing cancellation
                stripe.Subscription.modify(
                    subscription.id,
                    cancel_at_period_end=True
                )
                # Mark them in the sheet
                update_data_in_sheet(sheet, user_id_str, "Cancel at Period End")

                await update.message.reply_text(
                    "Your subscription will remain active until the end "
                    "of your current billing period, then be canceled automatically."
                )
                return
        # If no subscription found
        await update.message.reply_text(
            "No active subscription found. If you still need help, contact an admin."
        )
    except Exception as e:
        await update.message.reply_text(
            "Error canceling subscription. Are you sure you were subscribed? "
            "If you still need help, contact an admin."
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
            line_items=[{'price': STRIPE_PRICE_ID, 'quantity': 1}],
            mode='subscription',
            success_url='https://67d2acde0fd57931d93462b2--telestripe.netlify.app/success',
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
            member_limit=1,
            name="Join Group"
        )
        link_message = f"Join the group: {invite_link.invite_link}"
        await bot.send_message(chat_id=user_id, text=link_message)
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
    """Handles Stripe subscription events & updates Google Sheets accordingly."""
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
    subscription_obj = event.get("data", {}).get("object", {})
    telegram_id_str = subscription_obj.get("metadata", {}).get("telegram_id")
    price_id_object = subscription_obj.get("plan", {}).get("id")


    if telegram_id_str:
        print(f"[FLASK] Telegram ID from metadata: {telegram_id_str}")

    # Helpers for Sheet updates
    def record_subscription_in_sheet(subscription):
        """
        Gathers subscription+customer data and adds a new row to the sheet:
        [Name, Phone, TelegramID, DateStarted, NextBilling, SubType, ActiveStatus]
        """
        customer_id = subscription.get("customer")
        customer = stripe.Customer.retrieve(customer_id)
        name = customer.get("name", "N/A")
        phone = customer.get("phone", "N/A")  # or 'N/A' if not set
        email = customer.get("email", "N/A")

        date_started = datetime.now().strftime('%Y-%m-%d')
        sub_type = "Subscription"
        active_status = "Active"

        cell = sheet.find(telegram_id_str, in_column=3)  # column C = 3
        if cell:
            row = cell.row
            # Column G = 7
            sheet.update_cell(row, 6, active_status)
            print(f"Updated row {row} column 6 to '{active_status}'")
        else:
            row_data = [f"{name} ({email})", phone, telegram_id_str, date_started, sub_type, active_status]
            add_data_to_sheet(sheet, row_data)


        # columns: [Name, Phone, TelegramID, DateStarted, NextBilling, SubType, ActiveStatus]


    def update_subscription_in_sheet(new_status):
        """Updates the G column to the new_status for the given telegram_id."""
        update_data_in_sheet(sheet, telegram_id_str, new_status)

    # React to the event
    if event_type == "customer.subscription.created":
        # Create row in GSheets, invite user
        def handle_created():
            if price_id_object == STRIPE_PRICE_ID:
                record_subscription_in_sheet(subscription_obj)
                bot_app.create_task(invite_user_to_group(bot, int(telegram_id_str)))

        MAIN_LOOP.call_soon_threadsafe(handle_created)

    if event_type == "customer.subscription.deleted":
        # Mark them "Cancelled", remove from group
        def handle_deleted():
            update_subscription_in_sheet("Cancelled")
            bot_app.create_task(remove_user(bot, int(telegram_id_str)))

        MAIN_LOOP.call_soon_threadsafe(handle_deleted)

    elif event_type == "invoice.payment_failed":
        # Mark them "Payment Failed", remove from group
        def handle_failed():
            update_subscription_in_sheet("Payment Failed")
            bot_app.create_task(remove_user(bot, int(telegram_id_str)))

        MAIN_LOOP.call_soon_threadsafe(handle_failed)


    # If desired, handle invoice.payment_succeeded:
    #   def handle_succeeded():
    #       update_subscription_in_sheet("Active")
    #       # maybe re-invite user if needed?
    #   MAIN_LOOP.call_soon_threadsafe(handle_succeeded)

    return "", 200

def run_flask():
    """Runs Flask in a blocking call (but on a separate thread)."""
    port = int(os.environ.get("PORT", 5000))
    app.run(host="0.0.0.0", port=port, debug=False, use_reloader=False)

# ------------------------------------------------------------------------------
# 5) ASYNC MAIN FUNCTION FOR THE BOT
# ------------------------------------------------------------------------------
async def async_main():
    """Manually initialize & start the bot, then poll for updates."""
    global MAIN_LOOP
    MAIN_LOOP = asyncio.get_running_loop()

    # 1) Initialize
    await bot_app.initialize()

    # 2) Handlers
    bot_app.add_handler(CommandHandler("start", start))
    bot_app.add_handler(CommandHandler("subscribe", subscribe))
    bot_app.add_handler(CommandHandler("cancel", cancel))
    # Example for auto-approve join requests:
    # from telegram.ext import ChatJoinRequestHandler
    # bot_app.add_handler(ChatJoinRequestHandler(approve_join_request))

    # 3) Start the bot
    await bot_app.start()

    # 4) Start polling
    await bot_app.updater.start_polling()
    print("🤖 Telegram Bot is running...")

    # 5) Keep running until we set an event
    stop_event = asyncio.Event()
    await stop_event.wait()

    # 6) Shut down gracefully
    await bot_app.updater.stop()
    await bot_app.stop()
    await bot_app.shutdown()

# ------------------------------------------------------------------------------
# 6) ENTRY POINT
# ------------------------------------------------------------------------------
if __name__ == "__main__":
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)

    # Start Flask in background
    flask_thread = Thread(target=run_flask, daemon=True)
    flask_thread.start()

    # Run bot in same loop
    loop.run_until_complete(async_main())
    print("Bot has shut down.")
