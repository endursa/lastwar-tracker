"""
Last War Kill Tracker - Configuration
"""
import os
import json

# --- Paths ---
GAME_EXE_PATH = r"C:\Users\herbe\AppData\Local\FunFly\Last War-Survival Game\LastWarLauncher.exe"
PROJECT_DIR = os.path.dirname(os.path.abspath(__file__))
SCREENSHOTS_DIR = os.path.join(PROJECT_DIR, "screenshots")
CREDENTIALS_DIR = os.path.join(PROJECT_DIR, "credentials")
GOOGLE_CREDENTIALS_FILE = os.path.join(CREDENTIALS_DIR, "service_account.json")

# --- Google Sheets ---
# Set your Google Sheet ID here (from the sheet URL)
# Example: https://docs.google.com/spreadsheets/d/SHEET_ID_HERE/edit
GOOGLE_SHEET_ID = ""
WORKSHEET_NAME = "Kill Tracker"

# --- Gemini API ---
# Set your Gemini API key here
GEMINI_API_KEY = ""

# --- Timing ---
GAME_LOAD_WAIT_SECONDS = 90        # Wait for game to fully load
NAVIGATION_WAIT_SECONDS = 5        # Wait between navigation actions
SCROLL_WAIT_SECONDS = 2            # Wait after scrolling
SCREENSHOT_REGION = None           # None = full screen, or (x, y, width, height)

# --- Load from environment or .env file ---
def load_config():
    """Load configuration from .env file if it exists."""
    env_file = os.path.join(PROJECT_DIR, ".env")
    if os.path.exists(env_file):
        with open(env_file, "r") as f:
            for line in f:
                line = line.strip()
                if line and not line.startswith("#") and "=" in line:
                    key, value = line.split("=", 1)
                    os.environ[key.strip()] = value.strip()

    global GEMINI_API_KEY, GOOGLE_SHEET_ID
    GEMINI_API_KEY = os.environ.get("GEMINI_API_KEY", GEMINI_API_KEY)
    GOOGLE_SHEET_ID = os.environ.get("GOOGLE_SHEET_ID", GOOGLE_SHEET_ID)


# Ensure directories exist
os.makedirs(SCREENSHOTS_DIR, exist_ok=True)
os.makedirs(CREDENTIALS_DIR, exist_ok=True)

# Load config on import
load_config()
