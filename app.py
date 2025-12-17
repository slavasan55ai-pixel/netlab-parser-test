from flask import Flask, render_template_string

app = Flask(__name__)

# ---------------------------
# MOCK DATA (структура близка к Netlab)
# ---------------------------

CATEGORIES = [
    {"id": 1, "name": "Серверное оборудование"},
    {"id": 2, "name": "Сетевое оборудование"},
    {"id": 3, "name": "Хранение данных"},
]

PRODUCTS = [
    {
        "id": 101,
        "category_id": 1,
        "name": "Сервер Dell PowerEdge R750",
        "vendor": "Dell",
        "price": 485000,
        "image": "https://i.imgur.com/6QKQZ7C.png",
    },
    {
        "id": 102,
        "category_id": 1,
        "name": "HPE ProLiant DL380 Gen10",
        "vendor": "HPE",
        "price": 462000,
        "image": "https://i.imgur.com/fy8zJYH.png",
    },
    {
        "id": 201,
        "category_id": 2,
        "name": "Cisco Catalyst 9200",
        "vendor": "Cisco",
        "price": 198000,
        "image": "https://i.imgur.com/8KpZKZJ.png",
    },
    {
        "id": 301,
        "category_id": 3,
        "name": "Synology RS3621xs+",
        "vendor": "Synology",
        "price": 312000,
        "image": "https://i.imgur.com/JZy1E9F.png",
    },
]

# ---------------------------
# DASHBOARD
# ---------------------------

HTML = """
<!doctype html>
<html lang="ru">
<head>
    <meta charset="utf-8">
    <title>Netlab Test Dashboard</title>
    <style>
        body { font-family: Arial; background: #f4f6f8; margin: 40px; }
        h1 { margin-bottom: 10px; }
        .meta { color: #666; margin-bottom: 30px; }
        .grid { display: grid; grid-template-columns: repeat(auto-fill, minmax(260px, 1fr)); gap: 20px; }
        .card {
            background: #fff;
            border-radius: 10px;
            padding: 15px;
            box-shadow: 0 2px 8px rgba(0,0,0,.08);
        }
        .card img {
            width: 100%;
            height: 160px;
            object-fit: contain;
            background: #fafafa;
            border-radius: 6px;
        }
        .name { font-weight: bold; margin: 10px 0 5px; }
        .vendor { color: #555; font-size: 14px; }
        .price { margin-top: 8px; font-size: 16px; color: #0a7; }
    </style>
</head>
<body>

<h1>Каталог Netlab (тест)</h1>
<div class="meta">
Источник данных: mock-каталог (API Netlab подключается после выдачи логина)
</div>

<div class="grid">
{% for p in products %}
    <div class="card">
        <img src="{{ p.image }}">
        <div class="name">{{ p.name }}</div>
        <div class="vendor">{{ p.vendor }}</div>
        <div class="price">{{ "{:,.0f}".format(p.price).replace(",", " ") }} ₽</div>
    </div>
{% endfor %}
</div>

</body>
</html>
"""

@app.route("/")
def index():
    return render_template_string(HTML, products=PRODUCTS)

# ---------------------------

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=10000)
