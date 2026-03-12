FROM python:3.11-slim

# System dependencies required by Playwright/Chromium
RUN apt-get update && apt-get install -y \
    wget gnupg ca-certificates fonts-liberation \
    libnss3 libxss1 libatk-bridge2.0-0 libgtk-3-0 \
    libasound2 libdrm2 libxcomposite1 libxdamage1 \
    libxrandr2 libgbm1 libxfixes3 \
    libpango-1.0-0 libpangocairo-1.0-0 \
    --no-install-recommends \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

# Install Python dependencies first (better layer caching)
COPY requirements.txt requirements-web.txt ./
RUN pip install --no-cache-dir -r requirements.txt -r requirements-web.txt

# Install Playwright's Chromium browser
RUN playwright install chromium

# Copy application code
COPY . .

EXPOSE 8000

CMD ["python", "run_web.py"]
