from flask import Flask, render_template_string
import os
from parser_netlab import one_time_fetch

app = Flask(__name__)

HTML = """
<!DOCTYPE html>
<html>
<head>
    <meta charset="utf-8">
    <title>Netlab Test Dashboard</title>
    <style>
        body { font-family: Arial; padding: 20px; }
        table { border-collapse: collapse; width: 100%; }
        th, td { border: 1px solid #ccc; padding: 6px; font-size: 14px; }
        th { background: #eee; }
    </style>
</head>
<body>
<h2>Netlab Test Dashboard</h2>

<p>Данные загружены: {{ rows|length }} шт.</p>

<table>
    <tr>
        <th>Категория</th>
        <th>Товар</th>
        <th>SKU</th>
        <th>Цена</th>
    </tr>
    {% for r in rows %}
    <tr>
        <td>{{ r.category_name }}</td>
        <td>{{ r.name }}</td>
        <td>{{ r.sku }}</td>
        <td>{{ r.price }}</td>
    </tr>
    {% endfor %}
</table>

</body>
</html>
"""

@app.route("/")
def index():
    api_key = os.getenv("NETLAB_API_KEY")
    if not api_key:
        return "NETLAB_API_KEY not set", 500

    rows = one_time_fetch(api_key)
    return render_template_string(HTML, rows=rows)

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=10000)

