import os
import psycopg2
import psycopg2.extras
from flask import Flask, render_template_string

app = Flask(__name__)

# ----------------------------
# DATABASE
# ----------------------------

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


# вызываем инициализацию при старте
init_db()

# ----------------------------
# MOCK DATA (временно)
# ----------------------------

def get_mock_catalog():
    return [
        {
            "id": 1,
            "name": "Серверное оборудование",
            "children": [
                {
                    "name": "Серверы",
                    "products": [
                        {
                            "id": 101,
                            "name": "Dell PowerEdge R750",
                            "vendor": "Dell",
                            "image": "https://i.imgur.com/4YQZ6sK.png"
                        },
                        {
                            "id": 102,
                            "name": "HPE ProLiant DL380",
                            "vendor": "HPE",
                            "image": "https://i.imgur.com/W5Z8yYf.png"
                        }
                    ]
                }
            ]
        }
    ]


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

        for block in cat.get("children", []):
            for p in block.get("products", []):
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


# ----------------------------
# ROUTES
# ----------------------------

HTML = """
<!doctype html>
<html>
<head>
<meta charset="utf-8">
<title>Netlab Catalog</title>
<style>
body { font-family: Arial; background: #f6f7f8; padding: 20px; }
h1 { margin-bottom: 10px; }
.category { background: #fff; padding: 15px; margin-bottom: 20px; border-radius: 8px; }
.products { display: flex; gap: 15px; flex-wrap: wrap; }
.product { width: 200px; border: 1px solid #ddd; padding: 10px; border-radius: 6px; background: #fafafa; }
.product img { width: 100%; height: 120px; object-fit: contain; }
.vendor { font-size: 12px; color: #666; }
</style>
</head>
<body>

<h1>Каталог Netlab (тест)</h1>
<p>Источник данных: {{ data_source }}</p>

{% for cat in catalog %}
<div class="category">
  <h2>{{ cat.name }}</h2>
  {% for block in cat.children %}
    <div class="products">
      {% for p in block.products %}
        <div class="product">
          {% if p.image %}
            <img src="{{ p.image }}">
          {% endif %}
          <strong>{{ p.name }}</strong><br>
          <span class="vendor">{{ p.vendor }}</span>
        </div>
      {% endfor %}
    </div>
  {% endfor %}
</div>
{% endfor %}

</body>
</html>
"""


@app.route("/")
def index():
    # первый запуск — наполняем БД mock-данными
    if not load_catalog_from_db():
        save_catalog_to_db(get_mock_catalog())

    catalog = load_catalog_from_db()

    return render_template_string(
        HTML,
        catalog=catalog,
        data_source="Mock → PostgreSQL (Render)"
    )


# ----------------------------
# ENTRY POINT
# ----------------------------

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=10000)
