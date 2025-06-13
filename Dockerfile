# Use a lightweight Python image
FROM python:3.10-slim-buster

# Set the working directory in the container
WORKDIR /app

# Copy the requirements file into the working directory
COPY requirements.txt .

# Install Python dependencies
RUN pip install --no-cache-dir -r requirements.txt

# Copy the rest of the application code into the working directory
COPY . .

# Create a dummy health check file that our Procfile/deployment can curl
# This is a very basic approach for Koyeb's simple health check
# For a real-world scenario, you'd use a proper HTTP server for the health check.
# We'll serve this file via Python's simple http server in Procfile for the check.
RUN echo "ok" > healthz

# Expose port 8080 for the health check (Koyeb typically expects this port for the check)
EXPOSE 8080

# Command to run the bot. We'll use Procfile to define the actual entrypoint.
# CMD ["python", "main.py"]
