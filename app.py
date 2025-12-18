from flask import Flask, render_template_string
import os

app = Flask(__name__)

# ===== НАСТРОЙКИ =====
USE_REAL_NETLAB = False  # позже можно включить SOAP
DATA_SOURCE = "Mock Netlab Catalog (structure compatible)"

# ===== MOCK ДАННЫЕ (повторяют структуру каталога Netlab) =====
def get_mock_catalog():
    return [
        {
            "id": 1,
            "name": "Серверное оборудование",
            "children": [
                {
                    "id": 101,
                    "name": "Серверы",
                    "products": [
                        {
                            "id": 1001,
                            "name": "Dell PowerEdge R750",
                            "vendor": "Dell",
                            "image": "https://i.imgur.com/6XKQzYQ.png"
                        },
                        {
                            "id": 1002,
                            "name": "HPE ProLiant DL380",
                            "vendor": "HPE",
                            "image": "https://i.imgur.com/9QO3YkF.png"
                        }
                    ]
                }
            ]
        },
        {
            "id": 2,
            "name": "Сетевое оборудование",
            "children": [
                {
                    "id": 201,
                    "name": "Коммутаторы",
                    "products": [
                        {
                            "id": 2001,
                            "name": "Cisco Catalyst 9200",
                            "vendor": "Cisco",
                            "image": "https://i.imgur.com/1JQ9ZQO.png"
                        }
                    ]
                }
            ]
        }
    ]


def load_catalog():
    if USE_REAL_NETLAB:
        # здесь позже будет SOAP-клиент
        return []
    return get_mock_catalog()


# ===== HTML ШАБЛОН =====
HTML = """
<!DOCTYPE html>
<html lang="ru">
<head>
    <meta charset="UTF-8">
    <title>Netlab Catalog Dashboard</title>
    <style>
        body { font-family: Arial, sans-serif; background: #f5f5f5; }
        h1 { margin-bottom: 5px; }
        .source { color: #666; margin-bottom: 20px; }
        .category { margin: 20px 0; }
        .subcategory { margin-left: 20px; }
        .products { display: flex; gap: 15px; flex-wrap: wrap; margin-left: 40px; }
        .card {
            background: white;
            border-radius: 6px;
            padding: 10px;
            width: 200px;
            box-shadow: 0 2px 6px rgba(0,0,0,0.1);
        }
        .card img {
            max-width: 100%;
            height: 120px;
            object-fit: contain;
        }
        .vendor { color: #888; font-size: 13px; }
    </style>
</head>
<body>

<h1>Каталог Netlab</h1>
<div class="source">Источник данных: {{ data_source }}</div>

{% for cat in catalog %}
<div class="category">
    <h2>{{ cat.name }}</h2>

    {% for sub in cat.children %}
    <div class="subcategory">
        <h3>{{ sub.name }}</h3>

        <div class="products">
            {% for p in sub.products %}
            <div class="card">
                <img src="{{ p.image }}" alt="">
                <strong>{{ p.name }}</strong>
                <div class="vendor">{{ p.vendor }}</div>
            </div>
            {% endfor %}
        </div>
    </div>
    {% endfor %}
</div>
{% endfor %}

</body>
</html>
"""

# ===== ROUTE =====
@app.route("/")
def index():
    catalog = load_catalog()
    return render_template_string(
        HTML,
        catalog=catalog,
        data_source=DATA_SOURCE
    )


# ===== ENTRY POINT =====
if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5000))
    app.run(host="0.0.0.0", port=port)
