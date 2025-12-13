import os
import requests
from flask import Flask, jsonify

app = Flask(__name__)

NETLAB_LOGIN = os.getenv("NETLAB_LOGIN")
NETLAB_PASSWORD = os.getenv("NETLAB_PASSWORD")

BASE_URL = "https://api.netlab.ru"

@app.route("/")
def index():
    if not NETLAB_LOGIN or not NETLAB_PASSWORD:
        return jsonify({
            "status": "error",
            "message": "NETLAB_LOGIN / NETLAB_PASSWORD not set",
            "hint": "Add them in Render → Environment"
        }), 500

    try:
        response = requests.get(
            f"{BASE_URL}/categories",
            auth=(NETLAB_LOGIN, NETLAB_PASSWORD),
            timeout=15
        )

        return jsonify({
            "status": "ok",
            "http_status": response.status_code,
            "data": response.json()
        })

    except Exception as e:
        return jsonify({
            "status": "error",
            "exception": str(e)
        }), 500
