# Use a Python image including common build dependencies
FROM python:3.11-buster

# Install necessary system packages for Python libraries (as identified by your RUN command)
# Keep this RUN command from your original Dockerfile, it was likely correct for some deps.
RUN apt update && apt upgrade -y && \
    apt install -y \
        git \
        curl \
        ffmpeg \
        gcc \
        python3-dev \
        libffi-dev \
        libssl-dev \
        build-essential \
        # Add any other identified OS dependencies here
        && apt clean \
        && rm -rf /var/lib/apt/lists/*

# Upgrade pip
RUN pip install -U pip

# Set the working directory *before* copying requirements
WORKDIR /app # Set /app as the working directory

# Copy the requirements file *before* installing, leverage Docker cache
COPY requirements.txt /app/requirements.txt

# Install Python dependencies from requirements.txt
# Ensure this uses the /app path
RUN pip install --no-cache-dir -r /app/requirements.txt

# Copy the rest of the application code into the working directory (/app)
# This includes main.py, app.py, Procfile, handlers, database folders etc.
COPY . /app

# EXPOSE the port that the health check server (Flask/Gunicorn) listens on
EXPOSE 8080
