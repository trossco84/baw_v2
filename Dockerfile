FROM python:3.12-slim

WORKDIR /app

# System deps for Playwright Chromium + Xvfb
RUN apt-get update && apt-get install -y --no-install-recommends \
    xvfb \
    xauth \
    libnss3 libnspr4 \
    libatk1.0-0 libatk-bridge2.0-0 \
    libcups2 \
    libdrm2 \
    libxkbcommon0 \
    libxcomposite1 libxdamage1 libxfixes3 \
    libxrandr2 \
    libgbm1 \
    libasound2 \
    libpangocairo-1.0-0 libpango-1.0-0 \
    libcairo2 \
    libgtk-3-0 \
    libx11-6 libx11-xcb1 libxcb1 \
    libxext6 libxshmfence1 \
    ca-certificates curl \
    && rm -rf /var/lib/apt/lists/*

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Install chromium into the image
RUN python -m playwright install chromium

COPY . .

EXPOSE 8080
CMD ["python", "-m", "uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8080"]
