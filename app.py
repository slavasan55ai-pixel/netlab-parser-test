import os
import requests
import psycopg2
import psycopg2.extras
from flask import Flask, render_template_string
from datetime import datetime

# =========================================================
# CONFIG
# =========================================================
NETLAB_AUTH_WSDL = "http://services.netlab.ru/AuthenticationService?wsdl"
NETLAB_REST = "http://services.netlab.ru/rest/catalogsZip"

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
        name TEXT
    );
    """)

    cur.execute("""
    CREATE TABLE IF NOT EXISTS products (
        id BIGINT PRIMARY KEY,
        name TEXT,
        category_id BIGINT,
        image_url TEXT
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
    cur.close()
    conn.close()

init_db()

# =========================================================
# NETLAB AUTH (SOAP)
# =========================================================
def get_token():
    payload = f"""
    <soapenv:Envelope xmlns:soapenv="http://schemas.xmlsoap.org/soap/envelope/"
                      xmlns:ws="http://ws.web.netlab.com/">
       <soapenv:Body>
          <ws:authenticate>
             <arg0>{os.environ['NETLAB_LOGIN']}</arg0>
             <arg1>{os.environ['NETLAB_PASSWORD']}</arg1>
          </ws:authenticate>
       </soapenv:Body>
    </soapenv:Envelope>
    """

    headers = {
        "Content-Type": "text/xml; charset=utf-8"
    }

    r = requests.post(
        "http://services.netlab.ru/AuthenticationService",
        data=payload.encode("utf-8"),
        headers=headers,
        timeout=30
    )

    if "<token>" not in r.text:
        raise Exception("Netlab auth failed")

    token = r.text.split("<token>")[1].split("</token>")[0]
    return token

# =========================================================
# REST HELPERS
# =========================================================
def rest_get(path, token):
    url = f"{NETLAB_REST}/{path}?oauth_token={token}"
    r = requests.get(url, timeout=60)
    r.raise_for_status()
    return r.text

# =========================================================
# LOAD CATALOG (categories + goods)
# =========================================================
def load_catalog(token):
    xml = rest_get("list.xml", token)

    categories = []
    for block in xml.split("<catalog>")[1:]:
        name = block.split("<name>")[1].split("</name>")[0]
        cid = int(block.split("<id>")[1].split("</id>")[0])
        categories.append({"id": cid, "name": name})

    conn = get_db()
    cur = conn.cursor()

    for c in categories:
        cur.execute("""
            INSERT INTO categories (id, name)
            VALUES (%s, %s)
            ON CONFLICT (id) DO NOTHING
        """, (c["id"], c["name"]))

    conn.commit()
    cur.close()
    conn.close()

    return categories

# =========================================================
# LOAD GOODS + IMAGES + PRICES
# =========================================================
def load_goods(category_id, token):
    xml = rest_get(f"goods/{category_id}.xml", token)

    goods = []
    for g in xml.split("<goods>")[1:]:
        gid = int(g.split("<id>")[1].split("</id>")[0])
        name = g.split("<name>")[1].split("</name>")[0]
        goods.append({"id": gid, "name": name})

    conn = get_db()
    cur = conn.cursor()

    for g in goods:
        # IMAGE
        img_xml = rest_get(f"goodsImagesByCategory/{category_id}.xml", token)
        img_url = None
        if "<Url>" in img_xml:
            img_url = img_xml.split("<Url>")[1].split("</Url>")[0]

        cur.execute("""
            INSERT INTO products (id, name, category_id, image_url)
            VALUES (%s, %s, %s, %s)
            ON CONFLICT (id) DO NOTHING
        """, (g["id"], g["name"], category_id, img_url))

        # PRICE
        price_xml = rest_get(f"goodsByUid/{g['id']}.xml", token)
        price = None
        qty = None

        if "<Price>" in price_xml:
            price = float(price_xml.split("<Price>")[1].split("</Price>")[0])
        if "<Quantity>" in price_xml:
            qty = int(price_xml.split("<Quantity>")[1].split("</Quantity>")[0])

        cur.execute("""
            INSERT INTO prices (goods_id, price, quantity, updated_at)
            VALUES (%s, %s, %s, %s)
            ON CONFLICT (goods_id)
            DO UPDATE SET
              price = EXCLUDED.price,
              quantity = EXCLUDED.quantity,
              updated_at = EXCLUDED.updated_at
        """, (g["id"], price, qty, datetime.utcnow()))

    conn.commit()
    cur.close()
    conn.close()

# =========================================================
# DASHBOARD
# =========================================================
HTML = """
<!doctype html>
<html>
<head>
<meta charset="utf-8">
<title>Netlab Dashboard</title>
<style>
body { font-family: Arial; background:#f4f6f8; padding:20px; }
.card { background:#fff; padding:15px; margin-bottom:20px; border-radius:8px; }
.products { display:flex; flex-wrap:wrap; gap:15px; }
.product { width:220px; border:1px solid #ddd; padding:10px; border-radius:6px; }
.product img { width:100%; height:120px; object-fit:contain; }
.price { font-weight:bold; }
</style>
</head>
<body>

<h1>Netlab Catalog</h1>
<p>Источник: {{ data_source }}</p>

{% for row in rows %}
<div class="card">
  {% if row.image_url %}<img src="{{ row.image_url }}">{% endif %}
  <div>{{ row.name }}</div>
  <div class="price">{{ row.price }} ₽</div>
  <div>Остаток: {{ row.quantity }}</div>
</div>
{% endfor %}

</body>
</html>
"""

@app.route("/")
def index():
    try:
        token = get_token()
        categories = load_catalog(token)
        for c in categories[:1]:  # ограничение для теста
            load_goods(c["id"], token)
        source = "Netlab REST (live)"
    except Exception:
        source = "PostgreSQL cache"

    conn = get_db()
    cur = conn.cursor()
    cur.execute("""
        SELECT p.name, p.image_url, pr.price, pr.quantity
        FROM products p
        LEFT JOIN prices pr ON pr.goods_id = p.id
        LIMIT 50
    """)
    rows = cur.fetchall()
    conn.close()

    return render_template_string(
        HTML,
        rows=rows,
        data_source=source
    )

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=10000)
