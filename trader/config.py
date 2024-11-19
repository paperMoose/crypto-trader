from dotenv import load_dotenv
load_dotenv()
import os
import time

# API Credentials
API_KEY = os.getenv("GEMINI_API_KEY")
API_SECRET = os.getenv("GEMINI_API_SECRET").encode()

# Base URL for Gemini API
BASE_URL = "https://api.gemini.com"

# Database settings
DATABASE_URL = os.getenv("DATABASE_URL", "postgresql://gemini_bot:gemini_bot_password@localhost:5433/gemini_bot")

# Add function to generate valid nonce
def get_nonce():
    # Generate nonce based on current timestamp in seconds
    # Gemini expects seconds, not milliseconds
    return str(int(time.time()))
