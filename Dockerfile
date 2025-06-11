# Dockerfile

# 1. Choose a base Python image
# Using a slim version to keep image size down
FROM python:3.11-slim

# 2. Set the working directory in the container
WORKDIR /app

# 3. Set environment variables (optional, can also be set in Koyeb dashboard)
# ENV PYTHONUNBUFFERED 1 # Ensures print statements and logs are sent straight to terminal
# ENV TELEGRAM_BOT_TOKEN "" # Better to set sensitive vars in Koyeb's interface

# 4. Install system dependencies (if any)
# For example, if python-levenshtein or other C extensions need build tools:
# RUN apt-get update && apt-get install -y --no-install-recommends \
#     build-essential \
#  && rm -rf /var/lib/apt/lists/*
# (Uncomment and modify if you find specific system deps are needed during pip install)

# 5. Copy requirements.txt first to leverage Docker cache
COPY requirements.txt .

# 6. Install Python dependencies
# Using --no-cache-dir to reduce image size
RUN pip install --no-cache-dir -r requirements.txt

# 7. Copy the rest of the application code into the container
COPY . .
# This copies:
# main.py
# bot/ (directory)
# configs/ (directory)
# database/ (directory)
# .env.example (though .env itself should not be copied if it contains secrets)

# 8. Expose the port your health check server listens on (from settings.py)
# This should match settings.HEALTH_CHECK_PORT
EXPOSE 8080

# 9. Define the command to run your application
# This will execute main.py when the container starts
CMD ["python", "main.py"]
