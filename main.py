import os
import logging
import requests
from flask import Flask, jsonify

from config import config
from core.dependencies import event_manager
# Import event_handler to register the routes
import core.event_handler

app = Flask(__name__)

@app.errorhandler
def msg_error_handler(ex):
    logging.error(ex)
    response = jsonify(message=str(ex))
    response.status_code = (
        ex.response.status_code if isinstance(ex, requests.HTTPError) else 500
    )
    return response

@app.route("/", methods=["POST"])
def callback_event_handler():
    event_handler, event = event_manager.get_handler_with_event(
        config.VERIFICATION_TOKEN, 
        config.ENCRYPT_KEY
    )
    return event_handler(event)

if __name__ == "__main__":
    print(f"🚀 Starting Flask app on {config.HOST}:{config.PORT}")
    app.run(host=config.HOST, port=config.PORT, debug=config.DEBUG)
