# .dockerignore
__pycache__/
*.pyc
*.pyo
*.pyd
.Python
env/
venv/
.env # NEVER copy your .env file with secrets into the image
.git/
.gitignore
.dockerignore
Dockerfile
README.md
# Add any other local development files or large data files not needed by the running bot
# For example, if you have a local 'data/' folder for testing:
# data/
