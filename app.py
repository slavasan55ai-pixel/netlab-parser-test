import os
import requests
from flask import Flask, render_template_string

app = Flask(__name__)

BASE_URL = "https://api.netlab.ru"
TIMEOUT = 15


def fetch_categories():
    url = f"{BASE_URL}/api/catalog/categories"
    r = requests.get(url, timeout=TIMEOUT)
    r.raise_for_status()
    return r.json()


def fetch_products(category_id):
    url = f"{BASE_URL}/api/catalog/products"
    params = {
        "category_id": category_id,
        "limit": 20
    }
    r = requests.get(url, params=params, timeout=TIMEOUT)
    r.raise_for_status()
    return r.json()


def mock_data():
    return [
        {
            "name": "Ноутбуки",
            "products": [
                {"sku": "NB-HP-450", "name": "HP ProBook 450 G9", "price": 84500},
                {"sku": "NB-LEN-T14", "name": "Lenovo ThinkPad T14", "price": 91200},
            ]
        }
    ]


HTML = """
<!doctype html>
<html>
<head>
<meta charset="utf-8">
<title>Netlab Catalog Dashboard</title>
<style>
body { font-family: Arial; background:#f4f4f4; padding:20px; }
h1 { margin-bottom:10px; }
.note { color:#555; margin-bottom:20px; }
table { background:#fff; border-collapse: collapse; width:100%; }
th, td { border:1px solid #ddd; padding:8px; }
th { background:#eee; }
</style>
</head>
<body>

<h1>Netlab — каталог товаров</h1>
<div class="note">
Режим: {{ mode }}<br>
Источник: {{ source }}
</div>

{% for c in data %}
<h2>{{ c.name }}</h2>
<table>
<tr>
<th>Артикул</th>
<th>Название</th>
<th>Цена</th>
</tr>
{% for p in c.products %}
<tr>
<td>{{ p.sku }}</td>
<td>{{ p.name }}</td>
<td>{{ p.price }}</td>
</tr>
{% endfor %}
</table>
{% endfor %}

</body>
</html>
"""


@app.route("/")
def dashboard():
    try:
        categories = fetch_categories()

        result = []
        for c in categories[:3]:
            products = fetch_products(c["id"])
            result.append({
                "name": c.get("name"),
                "products": [
                    {
                        "sku": p.get("partnumber"),
                        "name": p.get("name"),
                        "price": p.get("price")
                    }
                    for p in products
                ]
            })

        return render_template_string(
            HTML,
            data=result,
            mode="LIVE",
            source="Netlab REST API"
        )

    except Exception as e:
        return render_template_string(
            HTML,
            data=mock_data(),
            mode="DEMO",
            data_source=f"Mock (нет доступа к API: {str(e)})"
        )
