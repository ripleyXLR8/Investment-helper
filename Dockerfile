FROM python:3.11-slim

WORKDIR /app

# Install system dependencies
RUN apt-get update && apt-get install -y --no-install-recommends \
    gcc \
    python3-dev \
    && rm -rf /var/lib/apt/lists/*

# Copy requirements and install
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy application code
COPY app/ .

# Create data directory
RUN mkdir -p /app/data

# Expose Flask port
EXPOSE 5000

# Healthcheck configuration
HEALTHCHECK --interval=1m --timeout=10s --start-period=30s --retries=3 \
    CMD find /tmp/heartbeat -mmin -2 | grep -q heartbeat || exit 1

# Run the application
CMD ["python", "main.py"]
