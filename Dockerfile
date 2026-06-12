FROM python:3.11-slim

# Install dependencies and Google Chrome
RUN apt-get update && apt-get install -y wget unzip \
    && wget -q https://dl.google.com/linux/direct/google-chrome-stable_current_amd64.deb \
    && apt-get install -y ./google-chrome-stable_current_amd64.deb \
    && rm google-chrome-stable_current_amd64.deb \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

# Install Python dependencies
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy application files
COPY . .

# Run gunicorn
# Note: Render provides the PORT environment variable dynamically
CMD gunicorn backend_scraper:app --workers=1 --threads=4 --timeout=120 --bind=0.0.0.0:$PORT
