FROM python:3.13-slim AS base
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1 PIP_NO_CACHE_DIR=1
WORKDIR /app
RUN apt-get update && apt-get install -y --no-install-recommends libpq5 curl && rm -rf /var/lib/apt/lists/*
COPY requirements.txt .
RUN pip install -r requirements.txt
COPY . .
RUN DJANGO_SETTINGS_MODULE=config.settings.production SECRET_KEY=build python manage.py collectstatic --noinput
EXPOSE 8000
# ASGI (HTTP + WebSockets). For HTTP-only scaling you can also run gunicorn config.wsgi.
CMD ["daphne", "-b", "0.0.0.0", "-p", "8000", "config.asgi:application"]
