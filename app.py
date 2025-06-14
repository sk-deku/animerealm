from flask import Flask

app = Flask(__name__)


@app.route('/')
def hello_world():
  return 'Hello, from Flask Health Check!', 200


@app.route('/healthz')
def health_check():
    return'DEKU', 200

if __name__ == '__main__':
  print("DEBUG: Running app.py directly, but NOT starting development server (local run only).")
