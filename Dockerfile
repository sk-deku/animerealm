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

# Expose port 8080 for the health check (The health check server inside main.py listens on this)
EXPOSE 8080

# Command to run the bot. We'll use Procfile to define the actual entrypoint.
# CMD ["python", "main.py"] # Command will be 'worker: python main.py' from Procfile
