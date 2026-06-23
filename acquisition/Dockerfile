FROM python:3.11-slim

WORKDIR /app

# Install system dependencies for curl_cffi (TLS), MinIO, and PDF processing
RUN apt-get update && apt-get install -y --no-install-recommends \
    curl \
    libgl1-mesa-glx \
    libglib2.0-0 \
    libsm6 \
    libxext6 \
    libxrender-dev \
    libgomp1 \
    && rm -rf /var/lib/apt/lists/*

# Upgrade pip
RUN pip install --no-cache-dir --upgrade pip

# Install Python dependencies
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy application code
COPY app/ app/
COPY worker/ worker/

# Expose port
EXPOSE 8000

# Default: run API server
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]