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

# =====================================================
# CONFIG
# =====================================================

NETLAB_LOGIN = os.environ.get("NETLAB_LOGIN")
NETLAB_PASSWORD = os.environ.get("NETLAB_PASSWORD")
DATABASE_URL = os.environ.get("DATABASE_URL")

AUTH_WSDL = "http://services.netlab.ru/AuthenticationService?wsdl"
REST_BASE = "http://services.netlab.ru/rest/catalogsZip"
CATALOG_NAME = "catalog"

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

app = Flask(__name__)

# =====================================================
# DB
# =====================================================

def db_conn():
    return psycopg2.connect(DATABASE_URL, sslmode="require")

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
                is_deleted BOOLEAN DEFAULT FALSE
            );
            """)

            cur.execute("ALTER TABLE products ADD COLUMN IF NOT EXISTS price NUMERIC(12,2);")
            cur.execute("ALTER TABLE products ADD COLUMN IF NOT EXISTS quantity INTEGER;")
            cur.execute("ALTER TABLE products ADD COLUMN IF NOT EXISTS updated_at TIMESTAMP;")

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

    logger.info("Database schema ready")

init_db()

# =====================================================
# XML
# =====================================================

def parse_xml(xml_bytes: bytes):
    parser = etree.XMLParser(recover=True, huge_tree=True)
    return etree.parse(BytesIO(xml_bytes), parser)

NS = {"ns": "http://ws.web.netlab.com/"}

# =====================================================
# AUTH SOAP
# =====================================================

def get_token():
    client = Client(AUTH_WSDL, transport=Transport(timeout=30))
    result = client.service.authenticate(
        arg0=NETLAB_LOGIN,
        arg1=NETLAB_PASSWORD
    )

    if result["status"]["code"] != 200:
        raise RuntimeError("Netlab authentication failed")

    return result["data"]["token"]

# =====================================================
# REST
# =====================================================

def rest_get(path, token, params=None):
    params = params or {}
    params["oauth_token"] = token
    url = f"{REST_BASE}/{path}"
    r = requests.get(url, params=params, timeout=120)
    r.raise_for_status()
    return parse_xml(r.content)

# =====================================================
# LOADERS
# =====================================================

def load_categories(token):
    tree = rest_get(f"{CATALOG_NAME}.xml", token)
    rows = []

    for c in tree.xpath("//ns:category", namespaces=NS):
        rows.append((
            int(c.findtext("ns:id", namespaces=NS)),
            c.findtext("ns:name", namespaces=NS),
            c.findtext("ns:parentId", namespaces=NS)
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

def load_products(token, category_id):
    tree = rest_get(
        f"versions/2/{CATALOG_NAME}/{category_id}.xml",
        token,
        {"showDeleted": 1}
    )

    rows = []

    for g in tree.xpath("//ns:goods", namespaces=NS):
        gid = int(g.findtext("ns:id", namespaces=NS))
        deleted = False

        for p in g.xpath(".//ns:property", namespaces=NS):
            if p.findtext("ns:name", namespaces=NS) == "Deleted":
                deleted = p.findtext("ns:value", namespaces=NS) == "true"

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

def load_price(token, goods_id):
    tree = rest_get(f"goodsByUid/{goods_id}.xml", token)

    price = None
    qty = None

    for p in tree.xpath("//ns:property", namespaces=NS):
        name = p.findtext("ns:name", namespaces=NS)
        value = p.findtext("ns:value", namespaces=NS)

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

# =====================================================
# API
# =====================================================

@app.route("/api/products")
def api_products():
    rows = db_fetch_all("""
        SELECT
            p.id,
            p.price,
            p.quantity,
            c.name AS category
        FROM products p
        JOIN categories c ON c.id = p.category_id
        WHERE p.is_deleted = false
        ORDER BY p.id
        LIMIT 200
    """)
    return jsonify(rows)

# =====================================================
# DASHBOARD
# =====================================================

HTML = """
<!doctype html>
<html>
<head><meta charset="utf-8"><title>Netlab Dashboard</title></head>
<body>
<h1>Netlab products</h1>
<pre id="out"></pre>
<script>
fetch('/api/products')
.then(r => r.json())
.then(d => out.innerText = JSON.stringify(d, null, 2))
</script>
</body>
</html>
"""

@app.route("/")
def index():
    return render_template_string(HTML)

# =====================================================

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=10000)
