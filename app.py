import os
import logging
from datetime import datetime
from flask import Flask, render_template_string
import psycopg2
import psycopg2.extras

from zeep import Client, Settings
from zeep.transports import Transport
from zeep.plugins import HistoryPlugin
from requests import Session
from requests.auth import HTTPBasicAuth

# =========================================================
# LOGGING
# =========================================================
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

SOAP_LOG_DIR = "logs/soap"
os.makedirs(SOAP_LOG_DIR, exist_ok=True)

def save_soap_log(history: HistoryPlugin):
    if not history.last_sent or not history.last_received:
        return

    ts = datetime.utcnow().strftime("%Y%m%d_%H%M%S_%f")
    with open(f"{SOAP_LOG_DIR}/{ts}_request.xml", "w", encoding="utf-8") as f:
        f.write(history.last_sent["envelope"].decode())

    with open(f"{SOAP_LOG_DIR}/{ts}_response.xml", "w", encoding="utf-8") as f:
        f.write(history.last_received["envelope"].decode())

# =========================================================
# FLASK
# =========================================================
app = Flask(__name__)

# =========================================================
# DATABASE
# =========================================================
def get_db():
    return psycopg2.connect(
        os.environ["DATABASE_URL"],
        cursor_factory=psycopg2.extras.DictCursor,
        sslmode="require"
    )

def init_db():
    conn = get_db()
    cur = conn.cursor()

    cur.execute("""
    CREATE TABLE IF NOT EXISTS categories (
        id BIGINT PRIMARY KEY,
        name TEXT NOT NULL
    );
    """)

    cur.execute("""
    CREATE TABLE IF NOT EXISTS products (
        id BIGINT PRIMARY KEY,
        name TEXT NOT NULL,
        vendor TEXT,
        category_id BIGINT REFERENCES categories(id),
        image_url TEXT
    );
    """)

    conn.commit()
    cur.close()
    conn.close()

init_db()

# =========================================================
# NETLAB SOAP
# =========================================================
def get_netlab_client():
    session = Session()
    session.auth = HTTPBasicAuth(
        os.environ["NETLAB_LOGIN"],
        os.environ["NETLAB_PASSWORD"]
    )

    history = HistoryPlugin()
    transport = Transport(session=session, timeout=30)
    settings = Settings(strict=False, xml_huge_tree=True)

    client = Client(
        wsdl=os.environ["NETLAB_WSDL"],
        transport=transport,
        settings=settings,
        plugins=[history]
    )

    return client, history

def load_netlab_catalog():
    client, history = get_netlab_client()

    # ⚠️ Метод должен быть проверен по WSDL
    response = client.service.GetCatalog()

    save_soap_log(history)

    catalog = []

    for cat in response.Categories:
        cat_id = int(cat.Id)
        catalog.append({
            "id": cat_id,
            "name": cat.Name,
            "children": [{
                "name": "Товары",
                "products": []
            }]
        })

        for p in getattr(cat, "Products", []):
            catalog[-1]["children"][0]["products"].append({
                "id": int(p.Id),
                "name": p.Name,
                "vendor": getattr(p, "Vendor", None),
                "image": getattr(p, "ImageUrl", None)
            })

    return catalog

# =========================================================
# DATABASE OPS
# =========================================================
def save_catalog_to_db(catalog):
    conn = get_db()
    cur = conn.cursor()

    for c in catalog:
        cur.execute(
            "INSERT INTO categories (id, name) VALUES (%s, %s) ON CONFLICT DO NOTHING",
            (c["id"], c["name"])
        )

        for p in c["children"][0]["products"]:
            cur.execute(
                """
                INSERT INTO products
                (id, name, vendor, category_id, image_url)
                VALUES (%s, %s, %s, %s, %s)
                ON CONFLICT DO NOTHING
                """,
                (p["id"], p["name"], p["vendor"], c["id"], p["image"])
            )

    conn.commit()
    cur.close()
    conn.close()

def load_catalog_from_db():
    conn = get_db()
    cur = conn.cursor()

    cur.execute("""
        SELECT c.id cid, c.name cname,
               p.id pid, p.name pname, p.vendor, p.image_url
        FROM categories c
        LEFT JOIN products p ON p.category_id = c.id
        ORDER BY c.name
    """)

    rows = cur.fetchall()
    conn.close()

    result = {}
    for r in rows:
        if r["cid"] not in result:
            result[r["cid"]] = {
                "id": r["cid"],
                "name": r["cname"],
                "children": [{"name": "Товары", "products": []}]
            }
        if r["pid"]:
            result[r["cid"]]["children"][0]["products"].append({
                "id": r["pid"],
                "name": r["pname"],
                "vendor": r["vendor"],
                "image": r["image_url"]
            })

    return list(result.values())

# =========================================================
# DASHBOARD
# =========================================================
HTML = """<!doctype html>
<html><head><meta charset="utf-8"><title>Netlab</title></head>
<body>
<h1>Netlab SOAP catalog</h1>
<p>Источник: {{ data_source }}</p>
{% for c in catalog %}
<h2>{{ c.name }}</h2>
<ul>
{% for p in c.children[0].products %}
<li>{{ p.name }} ({{ p.vendor }})</li>
{% endfor %}
</ul>
{% endfor %}
</body></html>
"""

@app.route("/")
def index():
    try:
        catalog = load_netlab_catalog()
        save_catalog_to_db(catalog)
        src = "Netlab SOAP (live)"
    except Exception as e:
        logger.error("SOAP error: %s", e)
        catalog = load_catalog_from_db()
        src = "PostgreSQL cache"

    return render_template_string(HTML, catalog=catalog, data_source=src)

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=10000)
