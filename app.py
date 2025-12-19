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

AUTH_WSDL = "http://services.netlab.ru/AuthenticationService?wsdl"
REST_BASE = "http://services.netlab.ru/rest/catalogsZip"

DATABASE_URL = os.getenv("DATABASE_URL")

CATALOG_NAME = "catalog"  # используется в документации Netlab

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
# AUTH SOAP
# -------------------------------------------------

def get_token():
    transport = Transport(timeout=30)
    client = Client(AUTH_WSDL, transport=transport)

    result = client.service.authenticate(
        arg0=NETLAB_LOGIN,
        arg1=NETLAB_PASSWORD
    )

    status = result["status"]["code"]
    if status != 200:
        raise RuntimeError("Netlab auth failed")

    return result["data"]["token"]


# -------------------------------------------------
# REST HELPERS
# -------------------------------------------------

def rest_get(path, token, params=None):
    params = params or {}
    params["oauth_token"] = token

    url = f"{REST_BASE}/{path}"
    r = requests.get(url, params=params, timeout=120)
    r.raise_for_status()
    return parse_xml(r.content)


# -------------------------------------------------
# CATALOGS / CATEGORIES
# -------------------------------------------------

def fetch_catalogs(token):
    tree = rest_get("list.xml", token)
    catalogs = []

    for node in tree.xpath("//ns:catalog", namespaces=NS):
        name = node.findtext("ns:name", namespaces=NS)
        catalogs.append(name)

    return catalogs


def fetch_categories(token, catalog):
    tree = rest_get(f"{catalog}.xml", token)
    categories = []

    for cat in tree.xpath("//ns:category", namespaces=NS):
        cid = cat.findtext("ns:id", namespaces=NS)
        name = cat.findtext("ns:name", namespaces=NS)
        parent = cat.findtext("ns:parentId", namespaces=NS)

        categories.append((cid, name, parent))

    execute_values(
        db_conn().cursor(),
        """
        INSERT INTO categories (id, name, parent_id)
        VALUES %s
        ON CONFLICT (id) DO UPDATE
        SET name = EXCLUDED.name,
            parent_id = EXCLUDED.parent_id
        """,
        categories
    )


# -------------------------------------------------
# PRODUCTS (2.2.4)
# -------------------------------------------------

def fetch_products_by_category(token, catalog, category_id):
    tree = rest_get(
        f"versions/2/{catalog}/{category_id}.xml",
        token,
        {"showDeleted": 1}
    )

    products = []

    for goods in tree.xpath("//ns:goods", namespaces=NS):
        gid = goods.findtext("ns:id", namespaces=NS)
        deleted = False

        for prop in goods.xpath(".//ns:property", namespaces=NS):
            if (
                prop.findtext("ns:name", namespaces=NS) == "Deleted"
                and prop.findtext("ns:value", namespaces=NS) == "true"
            ):
                deleted = True

        products.append((gid, category_id, deleted))

    execute_values(
        db_conn().cursor(),
        """
        INSERT INTO products (id, category_id, is_deleted)
        VALUES %s
        ON CONFLICT (id) DO UPDATE
        SET is_deleted = EXCLUDED.is_deleted
        """,
        products
    )


# -------------------------------------------------
# DESCRIPTIONS (2.2.6 / 2.2.7)
# -------------------------------------------------

def fetch_goods_description(token, goods_id):
    tree = rest_get(f"goodsDescriptionByUid/{goods_id}.xml", token)

    db_execute(
        "DELETE FROM product_properties WHERE goods_id = %s",
        (goods_id,)
    )

    for prop in tree.xpath("//ns:property", namespaces=NS):
        name = prop.findtext("ns:name", namespaces=NS)
        value = prop.findtext("ns:value", namespaces=NS)

        if name and value:
            db_execute(
                """
                INSERT INTO product_properties (goods_id, name, value)
                VALUES (%s, %s, %s)
                """,
                (goods_id, name, value)
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
                url = prop.findtext("ns:value", namespaces=NS)
                db_execute(
                    """
                    INSERT INTO product_images (goods_id, url)
                    VALUES (%s, %s)
                    ON CONFLICT DO NOTHING
                    """,
                    (gid, url)
                )


# -------------------------------------------------
# PRICES (2.2.10)
# -------------------------------------------------

def fetch_price(token, goods_id):
    tree = rest_get(f"goodsByUid/{goods_id}.xml", token)

    price = None
    qty = None

    for prop in tree.xpath("//ns:property", namespaces=NS):
        name = prop.findtext("ns:name", namespaces=NS)
        value = prop.findtext("ns:value", namespaces=NS)

        if name == "Price":
            price = value
        if name == "Quantity":
            qty = value

    db_execute(
        """
        UPDATE products
        SET price = %s,
            quantity = %s,
            updated_at = NOW()
        WHERE id = %s
        """,
        (price, qty, goods_id)
    )


# -------------------------------------------------
# SCHEDULER
# -------------------------------------------------

def update_prices_job():
    token = get_token()
    goods_ids = db_fetch_all("SELECT id FROM products WHERE is_deleted = false")

    for (gid,) in goods_ids:
        fetch_price(token, gid)


scheduler = BackgroundScheduler()
scheduler.add_job(update_prices_job, "interval", hours=1)
scheduler.start()


# -------------------------------------------------
# API
# -------------------------------------------------

@app.route("/api/categories")
def api_categories():
    rows = db_fetch_all(
        "SELECT id, name, parent_id FROM categories ORDER BY name"
    )
    return jsonify(rows)


@app.route("/api/products")
def api_products():
    rows = db_fetch_all(
        """
        SELECT p.id, p.price, p.quantity, c.name
        FROM products p
        JOIN categories c ON c.id = p.category_id
        WHERE p.is_deleted = false
        LIMIT 200
        """
    )
    return jsonify(rows)


# -------------------------------------------------
# DASHBOARD
# -------------------------------------------------

HTML = """
<!doctype html>
<html>
<head><title>Netlab Dashboard</title></head>
<body>
<h1>Netlab products</h1>
<pre id="data"></pre>
<script>
fetch('/api/products')
.then(r => r.json())
.then(d => document.getElementById('data').innerText = JSON.stringify(d, null, 2));
</script>
</body>
</html>
"""

@app.route("/")
def index():
    return render_template_string(HTML)


# -------------------------------------------------

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5000)
