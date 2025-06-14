FROM python:3.11-slim

# Install system packages required to build Python packages with C extensions
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
        && apt clean \
        && rm -rf /var/lib/apt/lists/*

# Upgrade pip
RUN pip install -U pip

# Copy the requirements
COPY requirements.txt /requirements.txt

# Install Python dependencies
RUN pip install -U -r /requirements.txt

# Create working directory
RUN mkdir /animerealm
WORKDIR /animerealm

# Copy the start script
COPY start.sh /start.sh

# Use the correct CMD syntax (was broken in your version)
CMD ["/bin/bash", "/start.sh"]
