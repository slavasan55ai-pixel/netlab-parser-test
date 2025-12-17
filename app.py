from flask import Flask, render_template_string
from zeep import Client
import hashlib
import os

# -------------------------
# НАСТРОЙКИ
# -------------------------
WSDL_URL = "http://4dealer.ru/soap/?WSDL"
LOGIN = os.getenv("NETLAB_LOGIN", "SlavaSan")
SOAP_KEY = os.getenv("NETLAB_KEY", "8577405782dcdefcd63d117d690ef485")

PRICE_ID = 1  # Megacomline (фактически определяется через getPricesList)

# -------------------------
# ВСПОМОГАТЕЛЬНЫЕ ФУНКЦИИ
# -------------------------
def make_hash(function_name: str) -> str:
    return hashlib.md5(
        (LOGIN + function_name + hashlib.md5(SOAP_KEY.encode()).hexdigest()).encode()
    ).hexdigest()


client = Client(WSDL_URL)
app = Flask(__name__)

# -------------------------
# ГЛАВНАЯ СТРАНИЦА
# -------------------------
@app.route("/")
def index():
    # 1. Получаем товары
    params = {
        "limit": 50,
        "offset": 1,
        "only_with_prices": "Y",
        "avail": "all"
    }

    items = client.service.getPriceItems(
        LOGIN,
        make_hash("getPriceItems"),
        PRICE_ID,
        params
    )

    products = items["Result"] if items and "Result" in items else []

    # 2. Получаем изображения
    ids = [int(p["id"]) for p in products]
    images_map = {}

    if ids:
        infos = client.service.getPriceItemInfoByIdArray(
            LOGIN,
            make_hash("getPriceItemInfoByIdArray"),
            ids,
            "Y"
        )

        for info in infos.get("Result", []):
            if info.get("image"):
                images_map[int(info["id"])] = info["image"][0]

    # 3. HTML-шаблон
    html = """
    <!doctype html>
    <html lang="ru">
    <head>
        <meta charset="utf-8">
        <title>Каталог Megacomline</title>
        <link href="https://cdn.jsdelivr.net/npm/bootstrap@5.3.2/dist/css/bootstrap.min.css" rel="stylesheet">
    </head>
    <body class="bg-light">
    <div class="container py-4">
        <h1 class="mb-4">Каталог продукции Megacomline</h1>

        <div class="row row-cols-1 row-cols-md-3 g-4">
        {% for p in products %}
            <div class="col">
                <div class="card h-100">
                    {% if images.get(p.id) %}
                        <img src="{{ images[p.id] }}" class="card-img-top" style="object-fit:contain;height:200px;">
                    {% endif %}
                    <div class="card-body">
                        <h6 class="card-title">{{ p.name }}</h6>
                        <p class="card-text">
                            Бренд: {{ p.brand }}<br>
                            Артикул: {{ p.part_no }}<br>
                            В наличии: {{ p.free }}
                        </p>
                        {% if p.my_prices %}
                        <strong>{{ p.my_prices.price_rub }} ₽</strong>
                        {% endif %}
                    </div>
                </div>
            </div>
        {% endfor %}
        </div>
    </div>
    </body>
    </html>
    """

    return render_template_string(html, products=products, images=images_map)


# -------------------------
# ТОЧКА ВХОДА
# -------------------------
if __name__ == "__main__":
    app.run(host="0.0.0.0", port=10000)
