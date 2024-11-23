# Use NVIDIA CUDA base image for GPU support
FROM nvidia/cuda:11.8.0-cudnn8-runtime-ubuntu22.04

# Set environment variables
ENV DEBIAN_FRONTEND=noninteractive
ENV PYTHONUNBUFFERED=1
ENV PYTHONDONTWRITEBYTECODE=1

# Install system dependencies
RUN apt-get update && apt-get install -y \
    python3.10 \
    python3-pip \
    ffmpeg \
    git \
    && rm -rf /var/lib/apt/lists/*

# Set working directory
WORKDIR /app

# Copy requirements file
COPY requirements.txt .

# Install Python dependencies
RUN pip3 install --no-cache-dir -r requirements.txt

# Copy the application code
COPY . .

# Create directories for temporary files and cache
RUN mkdir -p /tmp/transcription \
    && mkdir -p /root/.cache/whisper \
    && mkdir -p /root/.cache/huggingface

# Set default command
CMD ["python3", "main.py"]