# Test Procfile - For Debugging ONLY
release: python -m http.server 8080 & sleep 30 ; cat healthz
worker: sleep infinity # Prevent the worker from starting while debugging release

#worker: python main.py
#release: python -m http.server 8080
