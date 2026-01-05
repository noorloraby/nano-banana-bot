# Use official Playwright image with Python (includes browsers)
FROM mcr.microsoft.com/playwright/python:v1.49.0-jammy

# Prevent interactive prompts during apt-get install
ENV DEBIAN_FRONTEND=noninteractive
ENV TZ=UTC

WORKDIR /app

# Install Google Chrome (for better stealth - channel="chrome" support)
# Also install noVNC and x11vnc for visual login access
RUN apt-get update && apt-get install -y --no-install-recommends \
    wget gnupg x11vnc xvfb novnc tzdata \
    && ln -fs /usr/share/zoneinfo/UTC /etc/localtime \
    && dpkg-reconfigure -f noninteractive tzdata \
    && wget -q -O - https://dl.google.com/linux/linux_signing_key.pub | apt-key add - \
    && echo "deb [arch=amd64] http://dl.google.com/linux/chrome/deb/ stable main" > /etc/apt/sources.list.d/google-chrome.list \
    && apt-get update \
    && apt-get install -y google-chrome-stable \
    && rm -rf /var/lib/apt/lists/*

# Copy requirements first for layer caching
COPY requirements.txt .

# Install Python dependencies
RUN pip install --no-cache-dir -r requirements.txt

# Install playwright-stealth (specific version for compatibility)
RUN pip install playwright-stealth==1.0.6

# Copy application code
COPY bot.py browser_client.py config.py ./

# Copy user_data if it exists (will contain fresh Linux profile after first login)
COPY user_data/ ./user_data/

# Create temp directory
RUN mkdir -p temp

# Set environment variables for container
# Set HEADLESS=False for first run to login, then change to True
ENV HEADLESS=False
ENV USER_DATA_DIR=/app/user_data
ENV DISPLAY=:99

# Expose noVNC port for browser access
EXPOSE 6080

# Script to start Xvfb + VNC + bot
CMD Xvfb :99 -screen 0 1280x800x24 & \
    x11vnc -display :99 -forever -shared -rfbport 5900 & \
    /usr/share/novnc/utils/launch.sh --vnc localhost:5900 --listen 6080 & \
    sleep 2 && python bot.py
