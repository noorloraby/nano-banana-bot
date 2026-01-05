import os
from dotenv import load_dotenv

load_dotenv()

TELEGRAM_TOKEN = os.getenv("TELEGRAM_TOKEN")
HEADLESS = os.getenv("HEADLESS", "False").lower() == "true"
USER_DATA_DIR = os.getenv("USER_DATA_DIR", "./user_data")
TIMEOUT_MS = 120000  # 60 seconds timeout for generation
URL = "https://labs.google/flow/nano-banana"  # Placeholder URL - User didn't specify exact URL, verifying assumption
# Actually, the user described "Google Labs Flow's Nano Banana interface".
# I will assume a URL or just navigate to google labs and handle redirection.
# Wait, let's keep it configurable.
