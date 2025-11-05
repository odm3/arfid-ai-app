# Dockerfile for Flask Web Application
FROM python:3.12-slim

# Set working directory
WORKDIR /app

# Install system dependencies
RUN apt-get update && apt-get install -y \
    gcc \
    && rm -rf /var/lib/apt/lists/*

# Copy requirements first for better caching
COPY requirements.txt .

# Install Python dependencies
RUN pip install --no-cache-dir -r requirements.txt

# Copy application code
COPY app.py .

# Expose port (Lightsail will map this)
EXPOSE 8000

# Set environment variables
ENV PYTHONUNBUFFERED=1

# Run Gunicorn with the same config as Heroku
CMD ["gunicorn", "app:app", "--bind", "0.0.0.0:8000", "--timeout", "180", "--workers", "2", "--log-file=-"]
