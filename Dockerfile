# syntax=docker/dockerfile:1.7
# Local development image for the Chobbar Shop API.
# Code is bind-mounted by docker-compose, so edits reload without rebuilding;
# rebuild only when requirements change (`make build`).
# No apt packages needed: psycopg[binary] ships libpq, healthchecks use Python.
FROM python:3.13-slim
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1 \
    DJANGO_SETTINGS_MODULE=config.settings.development
WORKDIR /app
COPY requirements.txt requirements-dev.txt ./
RUN pip install -r requirements-dev.txt
COPY docker/entrypoint.sh /usr/local/bin/entrypoint
RUN chmod +x /usr/local/bin/entrypoint
EXPOSE 8000
ENTRYPOINT ["entrypoint"]
CMD ["python", "manage.py", "runserver", "0.0.0.0:8000"]
