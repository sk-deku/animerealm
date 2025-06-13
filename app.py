from flask import Flask

app = Flask(name)

@app.route('/')

def hello_world():
  return 'DEKU'

if name == 'main':

  app.run()
