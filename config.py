import os
from dotenv import load_dotenv

load_dotenv()

TELEGRAM_TOKEN = os.getenv("TELEGRAM_TOKEN")
HEADLESS = os.getenv("HEADLESS", "False").lower() == "true"
USER_DATA_DIR = os.getenv("USER_DATA_DIR", "./user_data")
TIMEOUT_MS = 120000  # 120 seconds timeout for generation
SECOND_IMAGE_WAIT_TIMEOUT_SECONDS = int(os.getenv("SECOND_IMAGE_WAIT_TIMEOUT_SECONDS", "10"))  # Seconds to wait for additional images after first one is found

# API Server Configuration
API_KEY = os.getenv("API_KEY")  # Required for API authentication
API_PORT = int(os.getenv("API_PORT", "8000"))  # Port for FastAPI server
URL = "https://labs.google/flow/nano-banana"  # Placeholder URL - User didn't specify exact URL, verifying assumption
# Actually, the user described "Google Labs Flow's Nano Banana interface".
# I will assume a URL or just navigate to google labs and handle redirection.
# Wait, let's keep it configurable.
