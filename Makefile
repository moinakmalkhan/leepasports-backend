.PHONY: dev worker beat test lint seed migrate shell urls graph reprice
dev: ; python manage.py runserver_plus 0.0.0.0:8000
worker: ; celery -A config worker -l info
beat: ; celery -A config beat -l info
test: ; python -m pytest -q
lint: ; ruff check apps config tests scripts && ruff format --check apps config tests scripts
seed: ; python manage.py seed_catalog --demo
migrate: ; python manage.py migrate
shell: ; python manage.py shell_plus
urls: ; python manage.py show_urls
graph: ; python manage.py graph_models -o docs/models.png
reprice: ; python manage.py runscript reprice_catalog
