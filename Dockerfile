# Use python 3.11 slim image
FROM python:3.11-slim

# Install system dependencies needed for compiling python libs (sounddevice, pyaudio, openwakeword)
RUN apt-get update && apt-get install -y \
    build-essential \
    libasound2-dev \
    portaudio19-dev \
    ffmpeg \
    git \
    curl \
    && rm -rf /var/lib/apt/lists/*

# Set working directory inside container
WORKDIR /app

# Copy requirements file first to leverage docker caching
COPY requirements.txt /app/

# Install python dependencies
RUN pip install --no-cache-dir -r requirements.txt

# Copy all backend source code to the container
COPY backend/ /app/

# Copy the environment file (it will be overridden by volumes or env_file in compose)
COPY .env /app/.env

# Expose FastAPI backend port
EXPOSE 8000

# Set environment output buffering
ENV PYTHONUNBUFFERED=1

# Command to run the FastAPI app
CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8000"]
