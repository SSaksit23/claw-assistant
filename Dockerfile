FROM python:3.11-slim

RUN apt-get update && apt-get install -y --no-install-recommends \
    libnss3 libnspr4 libatk1.0-0 libatk-bridge2.0-0 \
    libcups2 libdrm2 libxkbcommon0 libxcomposite1 \
    libxdamage1 libxfixes3 libxrandr2 libgbm1 libpango-1.0-0 \
    libcairo2 libasound2 libatspi2.0-0 libxshmfence1 \
    fonts-noto-cjk fonts-thai-tlwg \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt \
    && playwright install chromium

COPY . .

RUN mkdir -p data/uploads data/itineraries logs .learnings

ENV FLASK_ENV=production \
    HEADLESS_MODE=True \
    FLASK_HOST=0.0.0.0 \
    FLASK_PORT=5000

EXPOSE 5000

CMD ["python", "main.py"]
