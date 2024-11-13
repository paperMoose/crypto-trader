import pytest
import os
from dotenv import load_dotenv

@pytest.fixture(autouse=True)
def check_credentials():
    """Skip live tests if credentials are not available"""
    load_dotenv()
    if not (os.getenv("GEMINI_API_KEY") and os.getenv("GEMINI_API_SECRET")):
        pytest.skip("Gemini API credentials not found in environment") 