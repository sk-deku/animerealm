FROM python:3.10-slim-buster

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

# Set up healthz file for Koyeb health check (optional)
RUN echo "ok" > healthz

EXPOSE 8080

CMD ["python", "app.py"]
