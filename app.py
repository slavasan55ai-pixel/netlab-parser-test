import os
import logging
import requests
from io import BytesIO
from datetime import datetime

from flask import Flask, jsonify, render_template_string
from lxml import etree
from zeep import Client
from zeep.transports import Transport

import psycopg2
from psycopg2.extras import execute_values

from apscheduler.schedulers.background import BackgroundScheduler


# -------------------------------------------------
# CONFIG
# -------------------------------------------------

NETLAB_LOGIN = os.getenv("NETLAB_LOGIN")
NETLAB_PASSWORD = os.getenv("NETLAB_PASSWORD")
DATABASE_URL = os.getenv("DATABASE_URL")

AUTH_WSDL = "http://services.netlab.ru/AuthenticationService?wsdl"
REST_BASE = "http://services.netlab.ru/rest/catalogsZip"
CATALOG_NAME = "catalog"

logging.basicConfig(level=logging.INFO)
app = Flask(__name__)


# -------------------------------------------------
# DB
# -------------------------------------------------

def db_conn():
    return psycopg2.connect(DATABASE_URL)


def db_execute(sql, params=None):
    with db_conn() as conn:
        with conn.cursor() as cur:
            cur.execute(sql, params)


def db_fetch_all(sql, params=None):
    with db_conn() as conn:
        with conn.cursor() as cur:
            cur.execute(sql, params)
            return cur.fetchall()


# -------------------------------------------------
# XML
# -------------------------------------------------

def parse_xml(xml_bytes: bytes):
    parser = etree.XMLParser(recover=True, huge_tree=True)
    return etree.parse(BytesIO(xml_bytes), parser)


NS = {"ns": "http://ws.web.netlab.com/"}


# -------------------------------------------------
# AUTH
# -------------------------------------------------

def get_token():
    client = Client(AUTH_WSDL, transport=Transport(timeout=30))
    result = client.service.authenticate(arg0=NETLAB_LOGIN, arg1=NETLAB_PASSWORD)

    if result["status"]["code"] != 200:
        raise RuntimeError("Netlab authentication failed")

    return result["data"]["token"]


# -------------------------------------------------
# REST
# -------------------------------------------------

def rest_get(path, token, params=None):
    params = params or {}
    params["oauth_token"] = token
    r = requests.get(f"{REST_BASE}/{path}", params=params, timeout=120)
    r.raise_for_status()
    return parse_xml(r.content)


# -------------------------------------------------
# CATEGORIES (2.2.3)
# -------------------------------------------------

def fetch_categories(token):
    tree = rest_get(f"{CATALOG_NAME}.xml", token)
    rows = []

    for cat in tree.xpath("//ns:category", namespaces=NS):
        rows.append((
            cat.findtext("ns:id", namespaces=NS),
            cat.findtext("ns:name", namespaces=NS),
            cat.findtext("ns:parentId", namespaces=NS)
        ))

    execute_values(
        db_conn().cursor(),
        """
        INSERT INTO categories (id, name, parent_id)
        VALUES %s
        ON CONFLICT (id) DO UPDATE
        SET name = EXCLUDED.name,
            parent_id = EXCLUDED.parent_id
        """,
        rows
    )


# -------------------------------------------------
# PRODUCTS (2.2.4)
# -------------------------------------------------

def fetch_products_by_category(token, category_id):
    tree = rest_get(f"versions/2/{CATALOG_NAME}/{category_id}.xml", token)
    rows = []

    for goods in tree.xpath("//ns:goods", namespaces=NS):
        gid = goods.findtext("ns:id", namespaces=NS)
        deleted = any(
            p.findtext("ns:name", namespaces=NS) == "Deleted" and
            p.findtext("ns:value", namespaces=NS) == "true"
            for p in goods.xpath(".//ns:property", namespaces=NS)
        )
        rows.append((gid, category_id, deleted))

    execute_values(
        db_conn().cursor(),
        """
        INSERT INTO products (id, category_id, is_deleted)
        VALUES %s
        ON CONFLICT (id) DO UPDATE
        SET is_deleted = EXCLUDED.is_deleted
        """,
        rows
    )


# -------------------------------------------------
# IMAGES (2.2.9)
# -------------------------------------------------

def fetch_images_by_category(token, category_id):
    tree = rest_get(f"goodsImagesByCategory/{category_id}.xml", token)

    for goods in tree.xpath("//ns:goods", namespaces=NS):
        gid = goods.findtext("ns:id", namespaces=NS)

        for prop in goods.xpath(".//ns:property", namespaces=NS):
            if prop.findtext("ns:name", namespaces=NS) == "Url":
                db_execute(
                    """
                    INSERT INTO product_images (goods_id, url)
                    VALUES (%s, %s)
                    ON CONFLICT DO NOTHING
                    """,
                    (gid, prop.findtext("ns:value", namespaces=NS))
                )


# -------------------------------------------------
# PRICES (2.2.10)
# -------------------------------------------------

def fetch_price(token, goods_id):
    tree = rest_get(f"goodsByUid/{goods_id}.xml", token)

    price = None
    qty = None

    for prop in tree.xpath("//ns:property", namespaces=NS):
        if prop.findtext("ns:name", namespaces=NS) == "Price":
            price = prop.findtext("ns:value", namespaces=NS)
        if prop.findtext("ns:name", namespaces=NS) == "Quantity":
            qty = prop.findtext("ns:value", namespaces=NS)

    db_execute(
        """
        INSERT INTO product_prices (goods_id, price, quantity, updated_at)
        VALUES (%s, %s, %s, NOW())
        ON CONFLICT (goods_id) DO UPDATE
        SET price = EXCLUDED.price,
            quantity = EXCLUDED.quantity,
            updated_at = NOW()
        """,
        (goods_id, price, qty)
    )


# -------------------------------------------------
# SCHEDULER
# -------------------------------------------------

def update_prices_job():
    token = get_token()
    for (gid,) in db_fetch_all("SELECT id FROM products WHERE is_deleted = false"):
        fetch_price(token, gid)


scheduler = BackgroundScheduler()
scheduler.add_job(update_prices_job, "interval", hours=1)
scheduler.start()


# -------------------------------------------------
# API
# -------------------------------------------------

@app.route("/api/products")
def api_products():
    return jsonify(
        db_fetch_all(
            """
            SELECT
                p.id,
                pr.price,
                pr.quantity,
                c.name AS category
            FROM products p
            JOIN categories c ON c.id = p.category_id
            LEFT JOIN product_prices pr ON pr.goods_id = p.id
            WHERE p.is_deleted = false
            LIMIT 200
            """
        )
    )


# -------------------------------------------------
# DASHBOARD
# -------------------------------------------------

@app.route("/")
def index():
    return render_template_string(
        "<pre>{{ data }}</pre>",
        data=api_products().get_json()
    )


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5000)

