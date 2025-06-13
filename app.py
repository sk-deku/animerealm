# app.py
import threading
from http.server import BaseHTTPRequestHandler, HTTPServer
from main import run_bot  # <- make sure your bot's main logic is in a function like run_bot()

class HealthHandler(BaseHTTPRequestHandler):
    def do_GET(self):
        if self.path == "/healthz":
            self.send_response(200)
            self.end_headers()
            self.wfile.write(b"ok")
        else:
            self.send_response(404)
            self.end_headers()

def start_health_server():
    server_address = ('', 8080)
    httpd = HTTPServer(server_address, HealthHandler)
    print("Starting health check server on port 8080...")
    httpd.serve_forever()

if __name__ == "__main__":
    # Run bot in a separate thread
    threading.Thread(target=run_bot).start()

    # Start health check server (main thread)
    start_health_server()
