"""Centralized configuration loaded from .env file."""

import os
from dotenv import load_dotenv

load_dotenv()


class Config:
    """Application configuration from environment variables."""

    # --- OpenAI ---
    OPENAI_API_KEY = os.getenv("OPENAI_API_KEY", "")
    OPENAI_MODEL = os.getenv("OPENAI_MODEL", "gpt-4o-mini")

    # --- QualityB2BPackage Website ---
    WEBSITE_USERNAME = os.getenv("WEBSITE_USERNAME", "")
    WEBSITE_PASSWORD = os.getenv("WEBSITE_PASSWORD", "")
    WEBSITE_URL = os.getenv("WEBSITE_URL", "https://www.qualityb2bpackage.com/")

    # Website-specific URLs
    CHARGES_FORM_URL = f"{WEBSITE_URL.rstrip('/')}/charges_group/create"
    BOOKING_URL = f"{WEBSITE_URL.rstrip('/')}/booking"
    REPORT_SELLER_URL = f"{WEBSITE_URL.rstrip('/')}/report/report_seller"
    TRAVEL_PACKAGE_URL = f"{WEBSITE_URL.rstrip('/')}/travelpackage"

    # --- LINE Messaging API ---
    LINE_CHANNEL_SECRET = os.getenv("LINE_CHANNEL_SECRET", "")
    LINE_ACCESS_TOKEN = os.getenv("LINE_ACCESS_TOKEN", "")

    # --- Flask ---
    FLASK_ENV = os.getenv("FLASK_ENV", "production")
    FLASK_DEBUG = os.getenv("FLASK_DEBUG", "False").lower() in ("true", "1", "yes")
    FLASK_PORT = int(os.getenv("FLASK_PORT", "5000"))
    SECRET_KEY = os.getenv("SECRET_KEY", "web365-clawbot-secret-key")

    # --- Logging ---
    LOG_LEVEL = os.getenv("LOG_LEVEL", "INFO")
    LOG_FILE = os.getenv("LOG_FILE", "logs/app.log")

    # --- Browser Automation ---
    HEADLESS_MODE = os.getenv("HEADLESS_MODE", "True").lower() in ("true", "1", "yes")
    BROWSER_TIMEOUT = int(os.getenv("BROWSER_TIMEOUT", "30000"))

    # --- Data paths ---
    INPUT_CSV = os.getenv("INPUT_CSV", "data/tour_charges.csv")
    OUTPUT_CSV = os.getenv("OUTPUT_CSV", "data/results.csv")
    DATA_DIR = "data"
    UPLOAD_DIR = "data/uploads"

    # --- n8n Integration ---
    N8N_ENABLED = os.getenv("N8N_ENABLED", "False").lower() in ("true", "1", "yes")
    N8N_WEBHOOK_URL = os.getenv("N8N_WEBHOOK_URL", "http://localhost:5678/webhook")
    N8N_EXPENSE_WORKFLOW_URL = os.getenv("N8N_EXPENSE_WORKFLOW_URL", "")
    N8N_CALLBACK_SECRET = os.getenv("N8N_CALLBACK_SECRET", "clawbot-callback-secret")

    # --- Ngrok ---
    NGROK_AUTHTOKEN = os.getenv("NGROK_AUTHTOKEN", "")

    # --- Itinerary Analysis ---
    OPENAI_MODEL_ANALYSIS = os.getenv("OPENAI_MODEL_ANALYSIS", "gpt-4o")
    EXA_API_KEY = os.getenv("EXA_API_KEY", "")
    GEMINI_API_KEY = os.getenv("GEMINI_API_KEY", "")
    ITINERARY_UPLOAD_DIR = os.getenv("ITINERARY_UPLOAD_DIR", "data/itineraries")

    # --- Retry settings ---
    MAX_RETRIES = 3
    RETRY_DELAY_SECONDS = 5
