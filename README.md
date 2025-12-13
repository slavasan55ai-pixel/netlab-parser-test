# netlab-parser-test

Минимальный тестовый проект:
- Разовая выгрузка категорий и товаров из API netlab.ru
- Вывод в виде простого HTML-дашборда
- Запуск на Render (бесплатный тариф)

## Установка на Render

1. Создайте свой репозиторий на GitHub и загрузите в него файлы проекта.

2. На Render:
   - New → Web Service
   - Выбрать этот репозиторий
   - Environment = Python
   - Instance type = FREE

3. Build Command:
   pip install -r requirements.txt

4. Start Command:
   gunicorn app:app --bind 0.0.0.0:$PORT

5. В разделе Environment добавьте переменную:
   NETLAB_API_KEY = ваш_api_ключ_от_netlab

6. После деплоя откройте URL сервиса:
   вы увидите таблицу категорий и товаров.
