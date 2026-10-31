# Chobbar Shop API — developer commands
#
#   make up        → build images and start the whole stack (Postgres, Redis, Mailpit, API, Celery worker + beat)
#   make server    → start infra, then run the API in the foreground (logs here, Ctrl+C to stop)
#   make down      → stop everything           make clean → stop and delete volumes (database!)
#   make logs      → follow logs               make ps    → container status
#   make migrate / seed / shell / test / lint … run inside the api container when it is up,
#   otherwise in your local virtualenv — so the same target works both ways.
#   Configuration lives in `.env` (see .env.example for every variable).
#
# Local (no Docker) alternative: `make venv`, `make infra` (just db/redis/mailpit in Docker), `make server-local`.

SHELL := /bin/bash
.DEFAULT_GOAL := help

COMPOSE      ?= docker compose
PY           ?= python
MANAGE        = $(PY) manage.py
VENV          = .venv/bin/activate

# Run a command inside the api container if it's running, else locally.
API_RUNNING = $(shell $(COMPOSE) ps --status running --services 2>/dev/null | grep -qx api && echo 1)
ifeq ($(API_RUNNING),1)
  RUN  = $(COMPOSE) exec api
  RUNT = $(COMPOSE) exec -T api
else
  RUN  =
  RUNT =
endif

.PHONY: help
help: ## Show this help
	@awk 'BEGIN {FS = ":.*##"; printf "\nUsage: make \033[36m<target>\033[0m\n\n"} /^[a-zA-Z0-9_-]+:.*?##/ { printf "  \033[36m%-16s\033[0m %s\n", $$1, $$2 } /^##@/ { printf "\n\033[1m%s\033[0m\n", substr($$0, 5) }' $(MAKEFILE_LIST)
	@echo

##@ Docker stack
.PHONY: build up server infra down stop restart clean logs ps
build: ## Build the dev image
	$(COMPOSE) build api
up: .env ## Start everything in the background (db, redis, mailpit, api, worker, beat)
	$(COMPOSE) up -d --build
	@echo; echo "  API      http://localhost:8000/api/docs/"; echo "  Admin    http://localhost:8000/admin/"; echo "  Mailpit  http://localhost:8025"; echo
	@echo "  First time? run: make seed   (demo catalog + accounts)"; echo
server: .env ## Build, start infra + worker in background, run the API in the foreground
	$(COMPOSE) build api
	$(COMPOSE) up -d db redis mailpit
	$(COMPOSE) up api worker beat
infra: .env ## Only Postgres, Redis and Mailpit (for running Django from your venv)
	$(COMPOSE) up -d db redis mailpit
.env: ## Create .env from the example on first run
	@test -f .env || (cp .env.example .env && echo "Created .env from .env.example — review it.")
down: ## Stop and remove containers (keeps data)
	$(COMPOSE) down --remove-orphans
stop: ## Stop containers without removing them
	$(COMPOSE) stop
restart: ## Restart the app containers
	$(COMPOSE) restart api worker beat
clean: ## Stop everything and DELETE volumes (database, redis, media)
	$(COMPOSE) down -v --remove-orphans
logs: ## Follow logs (make logs s=api for one service)
	$(COMPOSE) logs -f --tail=200 $(s)
ps: ## Container status
	$(COMPOSE) ps

##@ Django (inside the container when up, otherwise local venv)
.PHONY: migrate makemigrations seed superuser shell dbshell manage urls graph low-stock collectstatic
migrate: ## Apply migrations
	$(RUNT) $(MANAGE) migrate
makemigrations: ## Create migrations (make makemigrations a=accounts)
	$(RUNT) $(MANAGE) makemigrations $(a)
seed: ## Seed catalog, fabrics, demo company and users
	$(RUNT) $(MANAGE) seed_catalog --demo
superuser: ## Create a staff superuser
	$(RUN) $(MANAGE) createsuperuser
shell: ## IPython shell_plus with models and services loaded
	$(RUN) $(MANAGE) shell_plus
dbshell: ## Django dbshell (psql)
	$(RUN) $(MANAGE) dbshell
manage: ## Any management command: make manage cmd="show_urls"
	$(RUN) $(MANAGE) $(cmd)
urls: ## List all URL routes
	$(RUNT) $(MANAGE) show_urls
graph: ## ER diagram → docs/models.png (needs graphviz)
	$(RUNT) $(MANAGE) graph_models -o docs/models.png
low-stock: ## Print low-stock variants
	$(RUNT) $(MANAGE) runscript low_stock_report
collectstatic: ## Collect static files
	$(RUNT) $(MANAGE) collectstatic --noinput

##@ Quality
.PHONY: test test-fast lint format check
test: ## Run the test suite (fresh test database)
	$(RUNT) $(PY) -m pytest -q --create-db
test-fast: ## Run tests reusing the test database
	$(RUNT) $(PY) -m pytest -q
lint: ## Ruff lint + format check
	$(RUNT) ruff check apps config tests scripts && $(RUNT) ruff format --check apps config tests scripts
format: ## Auto-fix lint and format
	$(RUNT) ruff check --fix apps config tests scripts && $(RUNT) ruff format apps config tests scripts
check: lint test ## Lint then test

##@ Local virtualenv (no Docker for the app)
.PHONY: venv server-local worker-local beat-local
venv: ## Create .venv and install dev requirements
	$(PY) -m venv .venv && . $(VENV) && pip install -U pip && pip install -r requirements-dev.txt
	@test -f .env || cp .env.example .env
	@echo "Activate with: source .venv/bin/activate"
server-local: ## runserver_plus on :8000 from your venv (run `make infra` first)
	$(MANAGE) runserver_plus 0.0.0.0:8000
worker-local: ## Celery worker from your venv
	celery -A config worker -l info
beat-local: ## Celery beat from your venv
	celery -A config beat -l info

##@ Containers & data
.PHONY: exec psql redis-cli backup restore
exec: ## Bash inside the api container
	$(COMPOSE) exec api bash
psql: ## psql on the dev database
	$(COMPOSE) exec db psql -U postgres -d chobbar
redis-cli: ## redis-cli on the dev redis
	$(COMPOSE) exec redis redis-cli
backup: ## Dump the database to backups/<timestamp>.sql.gz
	@mkdir -p backups && $(COMPOSE) exec -T db pg_dump -U postgres chobbar | gzip > backups/$$(date +%Y%m%d-%H%M%S).sql.gz && ls -1t backups | head -1
restore: ## Restore: make restore f=backups/xxx.sql.gz
	@test -n "$(f)" || (echo "usage: make restore f=backups/file.sql.gz" && exit 1)
	gunzip -c $(f) | $(COMPOSE) exec -T db psql -U postgres -d chobbar
