# handlers/__init__.py
# Pyrogram loads all modules imported in this file as plugins
# Add any handler modules you create here

from . import common_handlers
from . import admin_handlers
from . import browse_handler
from . import search_handler
from . import download_handler
from . import request_handler
from . import content_handler
from . import watchlist_handler
from . import tokens_handler
from . import callback_handlers

# Note: We'll uncomment these imports as we create the respective files.
# For now, only common_handlers is needed to start.
