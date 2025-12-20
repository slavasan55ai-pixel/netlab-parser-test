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
logger = logging.getLogger("app")

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


def init_db():
    """Создаёт минимально необходимую схему"""
    with db_conn() as conn:
        with conn.cursor() as cur:
            cur.execute("""
            CREATE TABLE IF NOT EXISTS categories (
                id BIGINT PRIMARY KEY,
                name TEXT NOT NULL,
                parent_id BIGINT
            );
            """)

            cur.execute("""
            CREATE TABLE IF NOT EXISTS products (
                id BIGINT PRIMARY KEY,
                category_id BIGINT REFERENCES categories(id),
                is_deleted BOOLEAN DEFAULT FALSE,
                price NUMERIC(12,2),
                quantity INTEGER,
                updated_at TIMESTAMP
            );
            """)

            cur.execute("""
            CREATE TABLE IF NOT EXISTS product_properties (
                id SERIAL PRIMARY KEY,
                goods_id BIGINT REFERENCES products(id),
                name TEXT,
                value TEXT
            );
            """)

            cur.execute("""
            CREATE TABLE IF NOT EXISTS product_images (
                id SERIAL PRIMARY KEY,
                goods_id BIGINT REFERENCES products(id),
                url TEXT
            );
            """)

    logger.info("DB schema ensured")


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

    if result["status"]["code"] != 200:
        raise RuntimeError("Netlab authentication failed")

    return result["data"]["token"]

# -------------------------------------------------
# REST
# -------------------------------------------------

def rest_get(path, token, params=None):
    params = params or {}
    params["oauth_token"] = token

    url = f"{REST_BASE}/{path}"
    r = requests.get(url, params=params, timeout=120)
    r.raise_for_status()
    return parse_xml(r.content)

# -------------------------------------------------
# CATEGORIES
# -------------------------------------------------

def fetch_categories(token):
    tree = rest_get(f"{CATALOG_NAME}.xml", token)
    rows = []

    for cat in tree.xpath("//ns:category", namespaces=NS):
        rows.append((
            int(cat.findtext("ns:id", namespaces=NS)),
            cat.findtext("ns:name", namespaces=NS),
            cat.findtext("ns:parentId", namespaces=NS)
        ))

    with db_conn() as conn:
        with conn.cursor() as cur:
            execute_values(
                cur,
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
    tree = rest_get(
        f"versions/2/{CATALOG_NAME}/{category_id}.xml",
        token,
        {"showDeleted": 1}
    )

    rows = []

    for goods in tree.xpath("//ns:goods", namespaces=NS):
        gid = int(goods.findtext("ns:id", namespaces=NS))
        deleted = False

        for prop in goods.xpath(".//ns:property", namespaces=NS):
            if prop.findtext("ns:name", namespaces=NS) == "Deleted":
                deleted = prop.findtext("ns:value", namespaces=NS) == "true"

        rows.append((gid, category_id, deleted))

    with db_conn() as conn:
        with conn.cursor() as cur:
            execute_values(
                cur,
                """
                INSERT INTO products (id, category_id, is_deleted)
                VALUES %s
                ON CONFLICT (id) DO UPDATE
                SET is_deleted = EXCLUDED.is_deleted
                """,
                rows
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
        elif name == "Quantity":
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
# API
# -------------------------------------------------

@app.route("/api/categories")
def api_categories():
    return jsonify(
        db_fetch_all(
            "SELECT id, name, parent_id FROM categories ORDER BY name"
        )
    )


@app.route("/api/products")
def api_products():
    return jsonify(
        db_fetch_all(
            """
            SELECT
                p.id,
                p.price,
                p.quantity,
                c.name AS category
            FROM products p
            JOIN categories c ON c.id = p.category_id
            WHERE p.is_deleted = false
            ORDER BY p.updated_at DESC NULLS LAST
            LIMIT 200
            """
        )
    )

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
.then(d => document.getElementById('data').innerText =
    JSON.stringify(d, null, 2));
</script>
</body>
</html>
"""

@app.route("/")
def index():
    return render_template_string(HTML)

# -------------------------------------------------
# BOOTSTRAP
# -------------------------------------------------

init_db()

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5000)
