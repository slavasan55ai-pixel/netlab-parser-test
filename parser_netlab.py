import requests

BASE_URL = "https://api.netlab.ru"

def get_categories(api_key):
    url = f"{BASE_URL}/v1/categories"
    headers = {"Authorization": f"Bearer {api_key}"}
    resp = requests.get(url, headers=headers)
    resp.raise_for_status()
    return resp.json()

def get_products(api_key, category_id):
    url = f"{BASE_URL}/v1/categories/{category_id}/products"
    headers = {"Authorization": f"Bearer {api_key}"}
    resp = requests.get(url, headers=headers)
    resp.raise_for_status()
    return resp.json()

def one_time_fetch(api_key):
    # 1. Получаем дерево категорий
    categories = get_categories(api_key)

    results = []

    # 2. Для каждой категории берем список товаров
    for cat in categories:
        cat_id = cat.get("id")
        cat_name = cat.get("name")

        products = get_products(api_key, cat_id)

        for p in products:
            results.append({
                "category_id": cat_id,
                "category_name": cat_name,
                "product_id": p.get("id"),
                "name": p.get("name"),
                "sku": p.get("sku"),
                "price": p.get("price"),
            })

    return results
