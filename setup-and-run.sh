#!/bin/bash

# Nano Banana Bot - Setup and Run Script for Linux Desktop Server
# This script will set up the environment and run the Telegram bot

set -e  # Exit on any error

echo "========================================"
echo "  Nano Banana Bot - Linux Setup Script"
echo "========================================"
echo ""

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

# Check if running as root (not recommended)
if [ "$EUID" -eq 0 ]; then
    echo -e "${YELLOW}Warning: Running as root is not recommended.${NC}"
fi

# Get the directory where the script is located
SCRIPT_DIR="$( cd "$( dirname "${BASH_SOURCE[0]}" )" && pwd )"
cd "$SCRIPT_DIR"

echo "Working directory: $SCRIPT_DIR"
echo ""

# Function to check if a command exists
command_exists() {
    command -v "$1" >/dev/null 2>&1
}

# Step 1: Check for Python 3
echo "Step 1: Checking for Python 3..."
if command_exists python3; then
    PYTHON_VERSION=$(python3 --version)
    echo -e "${GREEN}✓ $PYTHON_VERSION found${NC}"
else
    echo -e "${RED}✗ Python 3 not found. Please install Python 3.9 or higher.${NC}"
    echo "  Ubuntu/Debian: sudo apt install python3 python3-pip python3-venv"
    echo "  Fedora: sudo dnf install python3 python3-pip"
    exit 1
fi

# Step 2: Check for pip
echo "Step 2: Checking for pip..."
if command_exists pip3; then
    echo -e "${GREEN}✓ pip3 found${NC}"
else
    echo -e "${YELLOW}pip3 not found. Attempting to install...${NC}"
    sudo apt-get update && sudo apt-get install -y python3-pip || {
        echo -e "${RED}✗ Failed to install pip3. Please install manually.${NC}"
        exit 1
    }
fi

# Step 3: Create virtual environment if it doesn't exist
echo "Step 3: Setting up virtual environment..."
if [ ! -d ".venv" ]; then
    echo "Creating virtual environment..."
    python3 -m venv .venv
    echo -e "${GREEN}✓ Virtual environment created${NC}"
else
    echo -e "${GREEN}✓ Virtual environment already exists${NC}"
fi

# Activate virtual environment
source .venv/bin/activate
echo -e "${GREEN}✓ Virtual environment activated${NC}"

# Step 4: Install Python dependencies
echo "Step 4: Installing Python dependencies..."
pip install --upgrade pip
pip install -r requirements.txt
pip install playwright-stealth==1.0.6
echo -e "${GREEN}✓ Python dependencies installed${NC}"

# Step 5: Install Playwright browsers and system dependencies
echo "Step 5: Installing Playwright browsers..."
playwright install chromium
echo -e "${GREEN}✓ Playwright Chromium installed${NC}"

echo "Step 6: Installing Playwright system dependencies..."
sudo playwright install-deps chromium || {
    echo -e "${YELLOW}Warning: Could not install system dependencies automatically.${NC}"
    echo "You may need to run: sudo playwright install-deps chromium"
}
echo -e "${GREEN}✓ System dependencies installed${NC}"

# Step 7: Check for .env file
echo "Step 7: Checking for .env file..."
if [ ! -f ".env" ]; then
    echo -e "${YELLOW}⚠ .env file not found. Creating template...${NC}"
    cat > .env << EOF
# Telegram Bot Token from @BotFather
TELEGRAM_TOKEN=your_telegram_token_here

# Set to True for headless mode (no GUI), False for visible browser
HEADLESS=False

# User data directory for browser profile
USER_DATA_DIR=./user_data
EOF
    echo -e "${YELLOW}Please edit .env and add your TELEGRAM_TOKEN before running the bot.${NC}"
    echo ""
    echo -e "${RED}✗ Setup incomplete. Edit .env file and run this script again.${NC}"
    exit 1
else
    echo -e "${GREEN}✓ .env file found${NC}"
    
    # Check if TELEGRAM_TOKEN is set
    if grep -q "your_telegram_token_here" .env 2>/dev/null; then
        echo -e "${RED}✗ TELEGRAM_TOKEN not configured in .env file.${NC}"
        echo "Please edit .env and add your actual Telegram bot token."
        exit 1
    fi
fi

# Step 8: Create necessary directories
echo "Step 8: Creating necessary directories..."
mkdir -p temp
mkdir -p user_data
echo -e "${GREEN}✓ Directories created${NC}"

# Step 9: Run the bot
echo ""
echo "========================================"
echo -e "${GREEN}  Setup Complete! Starting the bot...${NC}"
echo "========================================"
echo ""
echo "Note: On first run, you'll need to log into Google in the browser window."
echo "      After logging in, the session will be saved for future runs."
echo ""
echo "Press Ctrl+C to stop the bot."
echo ""

# Run the bot
python bot.py
