# app.py
from http.server import BaseHTTPRequestHandler, HTTPServer

class HealthHandler(BaseHTTPRequestHandler):
    def do_GET(self):
        if self.path == "/healthz":
            self.send_response(200)
            self.end_headers()
            self.wfile.write(b"ok")
        else:
            self.send_response(404)
            self.end_headers()

server_address = ('', 8080)
httpd = HTTPServer(server_address, HealthHandler)
print("Starting health check server on port 8080...")
httpd.serve_forever()
