# Stage 1: Build dependencies (can include build tools)
FROM python:3.11-slim as builder

WORKDIR /app

# Install build dependencies
RUN apt-get update && apt-get install -y --no-install-recommends \
    gcc \
    && rm -rf /var/lib/apt/lists/*

# Copy requirements and install Python dependencies
COPY requirements.txt .
RUN pip install --user --no-cache-dir -r requirements.txt

# Stage 2: Runtime (minimal image)
FROM python:3.11-slim

WORKDIR /app

# Set environment variables
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PORT=8080 \
    PATH=/root/.local/bin:$PATH

# Copy only the installed Python packages from builder
COPY --from=builder /root/.local /root/.local

# Copy application code
COPY . .

# Expose the port that Cloud Run will use
EXPOSE 8080

# Use gunicorn to run the Flask app
# Cloud Run sets the PORT environment variable automatically
CMD exec gunicorn --bind :$PORT --workers 1 --threads 8 --timeout 0 web.app:app
