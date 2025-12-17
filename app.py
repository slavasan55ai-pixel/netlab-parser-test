from flask import Flask, render_template_string
import os

# ---------------------------
# Optional SOAP (Netlab)
# ---------------------------
USE_REAL_NETLAB = False  # переключатель: False = mock, True = SOAP

try:
    from zeep import Client
    from zeep.transports import Transport
    from requests import Session
except Exception:
    Client = None

NETLAB_WSDL = "https://api.4dealer.ru/Netlab?wsdl"

# ---------------------------
# Flask
# ---------------------------
app = Flask(__name__)

# ---------------------------
# MOCK DATA (близко к Netlab)
# ---------------------------

MOCK_CATEGORIES = [
    {"Id": 1, "Name": "Серверное оборудование", "ParentId": None},
    {"Id": 2, "Name": "Rack-серверы", "ParentId": 1},
    {"Id": 3, "Name": "Blade-серверы", "ParentId": 1},
    {"Id": 4, "Name": "Сетевое оборудование", "ParentId": None},
    {"Id": 5, "Name": "Коммутаторы", "ParentId": 4},
]

MOCK_PRODUCTS = [
    {
        "id": 101,
        "category_id": 2,
        "name": "Dell PowerEdge R750",
        "vendor": "Dell",
        "price": 485000,
        "image": "https://i.imgur.com/6QKQZ7C.png",
    },
    {
        "id": 102,
        "category_id": 2,
        "name": "HPE ProLiant DL380 Gen10",
        "vendor": "HPE",
        "price": 462000,
        "image": "https://i.imgur.com/fy8zJYH.png",
    },
    {
        "id": 201,
        "category_id": 5,
        "name": "Cisco Catalyst 9200",
        "vendor": "Cisco",
        "price": 198000,
        "image": "https://i.imgur.com/8KpZKZJ.png",
    },
]

# ---------------------------
# SOAP CLIENT
# ---------------------------

def get_netlab_client():
    session = Session()
    session.auth = (
        os.getenv("NETLAB_LOGIN"),
        os.getenv("NETLAB_PASSWORD"),
    )
    transport = Transport(session=session, timeout=20)
    return Client(wsdl=NETLAB_WSDL, transport=transport)

def fetch_categories_from_netlab():
    client = get_netlab_client()
    return client.service.GetCatalogTree()

# ---------------------------
# HELPERS
# ---------------------------

def build_category_tree(flat_categories):
    nodes = {}
    tree = []

    for c in flat_categories:
        nodes[c["Id"]] = {
            "id": c["Id"],
            "name": c["Name"],
            "parent_id": c.get("ParentId"),
            "children": []
        }

    for node in nodes.values():
        pid = node["parent_id"]
        if pid and pid in nodes:
            nodes[pid]["children"].append(node)
        else:
            tree.append(node)

    return tree

# ---------------------------
# DASHBOARD TEMPLATE
# ---------------------------

HTML = """
<!doctype html>
<html lang="ru">
<head>
<meta charset="utf-8">
<title>Netlab Demo Dashboard</title>
<style>
body { font-family: Arial; background:#f4f6f8; margin:40px; }
h1 { margin-bottom:5px; }
.meta { color:#666; margin-bottom:30px; }
.container { display:flex; gap:40px; }
.categories { width:300px; background:#fff; padding:20px; border-radius:10px; }
.products { flex:1; display:grid; grid-template-columns:repeat(auto-fill,minmax(260px,1fr)); gap:20px; }
.card { background:#fff; padding:15px; border-radius:10px; box-shadow:0 2px 8px rgba(0,0,0,.08); }
.card img { width:100%; height:160px; object-fit:contain; background:#fafafa; border-radius:6px; }
.name { font-weight:bold; margin:10px 0 5px; }
.vendor { color:#555; font-size:14px; }
.price { margin-top:8px; font-size:16px; color:#0a7; }
ul { list-style:none; padding-left:15px; }
li { margin:4px 0; }
</style>
</head>
<body>

<h1>Каталог Netlab</h1>
<div class="meta">Источник данных: {{ data_source }}</div>

<div class="container">

<div class="categories">
<b>Категории</b>
<ul>
{% for c in categories %}
<li>
{{ c.name }}
{% if c.children %}
<ul>
{% for ch in c.children %}
<li>{{ ch.name }}</li>
{% endfor %}
</ul>
{% endif %}
</li>
{% endfor %}
</ul>
</div>

<div class="products">
{% for p in products %}
<div class="card">
<img src="{{ p.image }}">
<div class="name">{{ p.name }}</div>
<div class="vendor">{{ p.vendor }}</div>
<div class="price">{{ "{:,.0f}".format(p.price).replace(",", " ") }} ₽</div>
</div>
{% endfor %}
</div>

</div>
</body>
</html>
"""

# ---------------------------
# ROUTES
# ---------------------------

@app.route("/")
def index():
    if USE_REAL_NETLAB and Client:
        try:
            flat = fetch_categories_from_netlab()
            categories = build_category_tree(flat)
            source = "Netlab SOAP API"
        except Exception as e:
            categories = build_category_tree(MOCK_CATEGORIES)
            source = f"Mock (ошибка API)"
    else:
        categories = build_category_tree(MOCK_CATEGORIES)
        data_source = "Mock (демо-каталог)"

    return render_template_string(
        HTML,
        categories=categories,
        products=MOCK_PRODUCTS,
        data_source=data_source
    )

# ---------------------------
# RUN
# ---------------------------

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=10000)
