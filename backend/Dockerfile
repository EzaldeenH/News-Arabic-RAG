FROM python:3.10-slim

WORKDIR /app

# Install system dependencies
RUN apt-get update && apt-get install -y \
    curl \
    && rm -rf /var/lib/apt/lists/*

# Copy requirements first for better caching
COPY requirements.txt .

# Install Python dependencies with retry and faster index
RUN pip install --no-cache-dir --retries 5 --timeout 30 -r requirements.txt \
    || pip install --no-cache-dir --retries 5 --timeout 30 -r requirements.txt \
    || pip install --no-cache-dir --retries 5 --timeout 30 -r requirements.txt

# Copy application code
COPY app ./app

# Expose port
EXPOSE 8000

# Health check
HEALTHCHECK --interval=30s --timeout=10s --start-period=5s --retries=3 \
    CMD curl -f http://localhost:8000/api/v1/health || exit 1

# Run the application
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
