import os
import pickle
from datetime import datetime

import gspread
from google.auth.transport.requests import Request
from google_auth_oauthlib.flow import InstalledAppFlow

# If you're using a service account instead, you'd do:
# from oauth2client.service_account import ServiceAccountCredentials

# Adjust these for your project:
TOKEN_PATH = "token_telegram.pickle"
CREDENTIALS_PATH = "client_secret_telegram.json"
SHEET_NAME = "DMOSubSheetTelegram"  # The name of your Google Sheet workbook
SHEET_TAB = "Master"                    # The sheet/tab name (if you have multiple)

SCOPES = [
    "https://www.googleapis.com/auth/spreadsheets",
    "https://www.googleapis.com/auth/drive"
]

def authenticate_gspread():
    """
    Checks if we already have valid credentials in TOKEN_PATH.
    If not, prompts an OAuth flow to authenticate with Google.
    """
    creds = None

    # Load existing creds if possible
    if os.path.exists(TOKEN_PATH):
        with open(TOKEN_PATH, "rb") as token:
            creds = pickle.load(token)

    # If no creds or creds invalid, do a fresh auth flow
    if not creds or not creds.valid:
        if creds and creds.expired and creds.refresh_token:
            creds.refresh(Request())
        else:
            flow = InstalledAppFlow.from_client_secrets_file(CREDENTIALS_PATH, SCOPES)
            creds = flow.run_local_server(port=0)

        # Save the credentials for next time
        with open(TOKEN_PATH, "wb") as token:
            pickle.dump(creds, token)

    return creds

def init_sheet():
    """
    Authenticates with Google and opens the desired sheet.
    Returns a gspread Worksheet object.
    """
    creds = authenticate_gspread()
    client = gspread.authorize(creds)
    # If you only have one tab, .sheet1
    # If a specific named tab, do .worksheet(SHEET_TAB)
    sheet = client.open(SHEET_NAME).worksheet(SHEET_TAB)
    return sheet

def add_data_to_sheet(sheet, data_list):
    """
    Appends a row to the bottom of the sheet.
    data_list example:
      [Name, Phone, TelegramID, DateStarted, NextBilling, SubType, ActiveStatus]
    """
    print(f"Adding row to sheet: {data_list}")
    sheet.append_row(data_list, value_input_option="RAW")

def update_data_in_sheet(sheet, telegram_id_str, new_status):
    """
    Finds the row with the matching Telegram ID in column C (3)
    and updates the Active Status in column G (7).
    """
    print(f"Updating row for Telegram ID '{telegram_id_str}' to status '{new_status}'")
    cell = sheet.find(telegram_id_str, in_column=3)  # column C = 3
    if cell:
        row = cell.row
        # Column G = 7
        sheet.update_cell(row, 6, new_status)
        print(f"Updated row {row} column 6 to '{new_status}'")
    else:
        print(f"No matching Telegram ID '{telegram_id_str}' found in column C.")
