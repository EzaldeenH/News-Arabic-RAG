FROM python:3.10-slim

WORKDIR /app

# Copy requirements first for better caching
COPY requirements.txt .

# Install Python dependencies with retry
RUN pip install --no-cache-dir --retries 5 --timeout 30 -r requirements.txt \
    || pip install --no-cache-dir --retries 5 --timeout 30 -r requirements.txt

# Copy application code
COPY app ./app

# Run the bot
CMD ["python", "app/main.py"]
