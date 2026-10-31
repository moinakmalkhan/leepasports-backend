.PHONY: dev worker beat test lint seed migrate shell
dev: ; python manage.py runserver 0.0.0.0:8000
worker: ; celery -A config worker -l info
beat: ; celery -A config beat -l info
test: ; python -m pytest -q
lint: ; ruff check apps config tests && ruff format --check apps config tests
seed: ; python manage.py seed_catalog --demo
migrate: ; python manage.py migrate
shell: ; python manage.py shell
