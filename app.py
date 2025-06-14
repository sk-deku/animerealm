# app.py
from flask import Flask
import logging # Can add basic logging here

# Basic Flask logger for debugging Flask startup if needed by Gunicorn
app_logger = logging.getLogger(__name__)
app_logger.setLevel(logging.INFO) # Gunicorn typically captures INFO+

app = Flask(__name__)

# Root path - Optional, not used by health check, but common
@app.route('/')
def root_path():
  # Standard default Flask response for '/'
  app_logger.debug("Root path / accessed.")
  return 'AnimeRealm Bot Health Check Endpoint - Hit /healthz', 200


# This is the primary health check endpoint Koyeb will hit.
@app.route('/healthz')
def health_check():
    # Just return a simple 200 OK quickly.
    app_logger.debug("Health check request received on /healthz.") # Log that the check hit this handler
    return 'OK', 200 # Standard HTTP status code 200 for OK

# This __main__ block is for local development 'python app.py'.
# Gunicorn (for Koyeb production health-server) will NOT run this block.
# Ensure no Flask development server is started here.
if __name__ == '__main__':
  print("DEBUG APP: Running app.py directly (local dev mode).")
  print("DEBUG APP: **NOT STARTING FLASK DEVELOPMENT SERVER IN PRODUCTION.**")

  # Example of running Flask development server *locally* for testing app.py itself
  # REMOVE or COMMENT OUT for production use (handled by Gunicorn Procfile entry)
  # app.run(host='0.0.0.0', port=8080, debug=True)
