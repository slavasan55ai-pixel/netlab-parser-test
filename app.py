import os
import time
import threading
import logging
from datetime import datetime

import requests
from lxml import etree
from flask import Flask, jsonify, render_template
import psycopg2
import psycopg2.extras
from zeep import Client

# =========================================================
# CONFIG
# =========================================================
NETLAB_AUTH_WSDL = "http://services.netlab.ru/AuthenticationService?wsdl"
NETLAB_REST_BASE = "http://services.netlab.ru/rest/catalogsZip"
PRICE_UPDATE_INTERVAL = 60 * 30  # 30 минут

DATABASE_URL = os.environ["DATABASE_URL"]
NETLAB_LOGIN = os.environ["NETLAB_LOGIN"]
NETLAB_PASSWORD = os.environ["NETLAB_PASSWORD"]

# =========================================================
# LOGGING
# =========================================================
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("netlab")

# =========================================================
# APP
# =========================================================
app = Flask(__name__)

# =========================================================
# DB
# =========================================================
def get_db():
    return psycopg2.connect(
        DATABASE_URL,
        cursor_factory=psycopg2.extras.DictCursor,
        sslmode="require"
    )

def init_db():
    conn = get_db()
    cur = conn.cursor()

    cur.execute("""
    CREATE TABLE IF NOT EXISTS catalogs (
        name TEXT PRIMARY KEY
    );
    """)

    cur.execute("""
    CREATE TABLE IF NOT EXISTS categories (
        id BIGINT PRIMARY KEY,
        name TEXT,
        parent_id BIGINT,
        catalog_name TEXT
    );
    """)

    cur.execute("""
    CREATE TABLE IF NOT EXISTS products (
        id BIGINT PRIMARY KEY,
        name TEXT,
        category_id BIGINT
    );
    """)

    cur.execute("""
    CREATE TABLE IF NOT EXISTS prices (
        goods_id BIGINT PRIMARY KEY,
        price NUMERIC,
        quantity INT,
        updated_at TIMESTAMP
    );
    """)

    conn.commit()
    conn.close()

init_db()

# =========================================================
# AUTH TOKEN (SOAP)
# =========================================================
def get_token():
    client = Client(NETLAB_AUTH_WSDL)
    result = client.service.authenticate({
        "arg0": NETLAB_LOGIN,
        "arg1": NETLAB_PASSWORD
    })

    status = result["status"]["code"]
    if status != 200:
        raise RuntimeError("Netlab auth failed")

    return result["data"]["token"]

# =========================================================
# XML HELPERS
# =========================================================
def parse_xml(text):
    return etree.fromstring(text.encode("utf-8"))

def
