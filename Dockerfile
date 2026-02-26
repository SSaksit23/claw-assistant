FROM python:3.12-slim

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Install Chromium + all its OS dependencies in one step,
# then add CJK/Thai fonts for document rendering.
RUN playwright install --with-deps chromium \
    && apt-get install -y --no-install-recommends \
       fonts-noto-cjk fonts-thai-tlwg \
    && rm -rf /var/lib/apt/lists/*

COPY . .

RUN mkdir -p data/uploads data/itineraries logs .learnings

ENV FLASK_ENV=production \
    HEADLESS_MODE=True \
    FLASK_HOST=0.0.0.0 \
    FLASK_PORT=5000

EXPOSE 5000

CMD ["python", "main.py"]
