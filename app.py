# app.py
from flask import Flask
import logging # Can add basic logging here for Flask startup info

# Basic Flask logger for debugging Flask itself
app_logger = logging.getLogger(__name__) # Logger for this file
app_logger.setLevel(logging.INFO) # Or DEBUG for more Flask server logs

app = Flask(__name__) # __name__ is standard for Flask app instance name


@app.route('/') # You can also map /healthz directly here if preferred
def hello_world():
  # Simple response for health check. Koyeb usually checks a specific path like /healthz.
  # Let's make the route specific for the health check
  return 'Hello, from Flask Health Check!', 200 # Return status code 200 (OK) explicitly

if __name__ == '__main__':
  # This block will NOT run when Gunicorn/Waitress runs app.py on Koyeb
  # It's only for running with the simple Flask development server (not suitable for production)
  print("DEBUG: Running Flask development server (for local testing only)...")
  # You might need to bind to 0.0.0.0 to be accessible from outside container on local run
  app.run(host='0.0.0.0', port=8080)
  print("DEBUG: Flask development server stopped.")
