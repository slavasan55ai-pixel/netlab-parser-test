import os
from flask import Flask, render_template_string
import psycopg2
import psycopg2.extras
from zeep import Client
from zeep.transports import Transport
from requests import Session
from requests.auth import HTTPBasicAuth

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

    transport = Transport(session=session, timeout=30)

    client = Client(
        wsdl=os.environ["NETLAB_WSDL"],
        transport=transport
    )
    return client


def load_netlab_catalog():
    """
    ВАЖНО:
    Названия методов и полей зависят от реального WSDL.
    Здесь — корректный шаблон работы с zeep.
    """

    client = get_netlab_client()

    # ↓↓↓ ПРИМЕР. Реальный метод смотри в WSDL Netlab ↓↓↓
    response = client.service.GetCatalog()

    # Приведение ответа SOAP к нормализованной структуре
    catalog = []

    for cat in response.Categories:
        category = {
            "id": int(cat.Id),
            "name": cat.Name,
            "children": [{
                "name": "Товары",
                "products": []
            }]
        }

        for p in cat.Products:
            category["children"][0]["products"].append({
                "id": int(p.Id),
                "name": p.Name,
                "vendor": p.Vendor,
                "image": getattr(p, "ImageUrl", None)
            })

        catalog.append(category)

    return catalog


# =========================================================
# DATABASE OPERATIONS
# =========================================================

def save_catalog_to_db(catalog):
    conn = get_db()
    cur = conn.cursor()

    for cat in catalog:
        cur.execute(
            """
            INSERT INTO categories (id, name)
            VALUES (%s, %s)
            ON CONFLICT (id) DO NOTHING
            """,
            (cat["id"], cat["name"])
        )

        for block in cat["children"]:
            for p in block["products"]:
                cur.execute(
                    """
                    INSERT INTO products
                    (id, name, vendor, category_id, image_url)
                    VALUES (%s, %s, %s, %s, %s)
                    ON CONFLICT (id) DO NOTHING
                    """,
                    (
                        p["id"],
                        p["name"],
                        p.get("vendor"),
                        cat["id"],
                        p.get("image")
                    )
                )

    conn.commit()
    cur.close()
    conn.close()


def load_catalog_from_db():
    conn = get_db()
    cur = conn.cursor()

    cur.execute("""
        SELECT
            c.id   AS cat_id,
            c.name AS cat_name,
            p.id   AS prod_id,
            p.name AS prod_name,
            p.vendor,
            p.image_url
        FROM categories c
        LEFT JOIN products p ON p.category_id = c.id
        ORDER BY c.name
    """)

    rows = cur.fetchall()
    conn.close()

    catalog = {}

    for r in rows:
        if r["cat_id"] not in catalog:
            catalog[r["cat_id"]] = {
                "id": r["cat_id"],
                "name": r["cat_name"],
                "children": [{
                    "name": "Товары",
                    "products": []
                }]
            }

        if r["prod_id"]:
            catalog[r["cat_id"]]["children"][0]["products"].append({
                "id": r["prod_id"],
                "name": r["prod_name"],
                "vendor": r["vendor"],
                "image": r["image_url"]
            })

    return list(catalog.values())


# =========================================================
# DASHBOARD
# =========================================================

HTML = """
<!doctype html>
<html>
<head>
<meta charset="utf-8">
<title>Netlab SOAP Catalog</title>
<style>
body { font-family: Arial; background: #f4f6f8; padding: 20px; }
.category { background: #fff; margin-bottom: 20px; padding: 15px; border-radius: 8px; }
.products { display: flex; flex-wrap: wrap; gap: 15px; }
.product { width: 220px; border: 1px solid #ddd; padding: 10px; border-radius: 6px; background: #fafafa; }
.product img { width: 100%; height: 120px; object-fit: contain; }
.vendor { font-size: 12px; color: #666; }
</style>
</head>
<body>

<h1>Netlab Catalog (SOAP)</h1>
<p>Источник данных: {{ data_source }}</p>

{% for cat in catalog %}
<div class="category">
  <h2>{{ cat.name }}</h2>
  <div class="products">
  {% for p in cat.children[0].products %}
    <div class="product">
      {% if p.image %}<img src="{{ p.image }}">{% endif %}
      <strong>{{ p.name }}</strong><br>
      <span class="vendor">{{ p.vendor }}</span>
    </div>
  {% endfor %}
  </div>
</div>
{% endfor %}

</body>
</html>
"""


@app.route("/")
def index():
    try:
        catalog = load_netlab_catalog()
        save_catalog_to_db(catalog)
        source = "Netlab SOAP (live)"
    except Exception as e:
        catalog = load_catalog_from_db()
        source = f"PostgreSQL cache (SOAP error)"

    return render_template_string(
        HTML,
        catalog=catalog,
        data_source=source
    )


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=10000)
