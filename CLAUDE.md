# Leepa Sports — backend (Django)

B2B wholesale teamwear platform for Leepa Sports (Sialkot, Pakistan). This repo is the API + admin.
Frontend lives in `leepasports-frontend` (Next.js) and talks to `/api/v1/`.

## Stack
Django 5.2 · DRF · SimpleJWT (rotating refresh + blacklist) · PostgreSQL 16 (FTS, trigram, JSONB) · Redis (cache, Celery broker, Channels layer) · Celery + beat · Channels/Daphne (WebSockets) · django-unfold admin · django-extensions.

## Run locally
```bash
python -m venv .venv && . .venv/bin/activate
pip install -r requirements-dev.txt
cp .env.example .env            # Postgres + Redis must be running; set SECRET_KEY/JWT_SIGNING_KEY
createdb leepasports && python manage.py migrate
python manage.py seed_catalog --demo      # fabrics, categories, products, demo users
python manage.py runserver_plus 0.0.0.0:8000   # or: daphne config.asgi:application (needed for WebSockets)
celery -A config worker -l info           # optional in dev: CELERY_TASK_ALWAYS_EAGER=True runs tasks inline
```
Admin: http://localhost:8000/admin/ (admin@leepasports.com / Admin!Leepa2026). API docs: /api/docs/.
Demo buyer: buyer@riversidefc.com / Buyer!Leepa2026 (company owner), coach@riversidefc.com / Coach!Leepa2026 (buyer with a 2,000 spend limit).

## Commands
- `make test` / `python -m pytest -q` — API tests against Postgres (35 tests; use `--create-db` after model changes)
- `make lint` — ruff check + format (line length 130)
- `python manage.py shell_plus` — IPython with models + services preloaded (prints SQL in dev)
- `python manage.py show_urls`, `runscript <name>` (scripts/), `graph_models`
- `python manage.py makemigrations --check --dry-run` before committing model changes

## Layout
```
config/settings/{base,development,production,test}.py   config/unfold.py (admin sidebar/branding)
apps/core          base models (UUIDModel/TimeStampedModel), pagination, permissions, throttles, error envelope,
                   cache namespaces, admin dashboard/reports/forms/utils
apps/accounts      User (email login + Google), Company, CompanyMember (owner/admin/buyer/viewer), invitations, addresses
apps/catalog       Category (materialised path), Fabric (PKR/kg mill price), Size/SizeGroup, Product (+fabric/size options), seed command
apps/pricing       CustomerGroup, ExchangeRate, VolumeTier, PriceListItem, services.compute_price (the price engine)
apps/cart          Cart/CartItem (size×gender breakdown JSON), SavedList, quick order by SKU
apps/quotes        RFQ: submit → staff respond → accept (creates Order)
apps/orders        checkout, status machine + history, approvals, net terms/credit, public tracking, invoice data, staff transitions
apps/payments      Payment (deposit/full/balance), proof upload, staff confirm, BankAccount
apps/notifications in-app Notification, event bus (events.emit → handlers.py), emails (templates/email), realtime push
apps/search        FTS + trigram + synonyms, suggest, recommendations, search log
apps/chat          Conversation/Message, JWT websocket middleware, consumers (/ws/chat/<uid>/, /ws/notifications/)
tests/             pytest-django suite; conftest seeds the catalog once per session
```

## Conventions (follow these)
- Business logic lives in `services.py` (and `selectors.py`) — views stay thin. Multi-write operations are wrapped in `transaction.atomic` and use `select_for_update` where money/credit/status changes.
- Side effects go through `apps.notifications.events.emit("event.name", **ids)` from `after_commit(...)`; add handlers in `notifications/handlers.py`. Pass ids, not model instances (Celery JSON).
- Prices are never trusted from the client: `pricing.selectors.resolve_configuration` validates product/fabric/sizes/MOQ, `pricing.services.compute_price` returns the breakdown. Fabric price (PKR) × consumption ÷ FX + labour, then group/volume discounts or contract price.
- Public ids are `uid` (UUID); integer pks never leave the API. Lists use `StandardPagination` (`count/page/page_size/total_pages/next/previous/results`), feeds use cursor pagination.
- Errors always return `{"detail", "code", "errors?"}` via `core.exceptions.api_exception_handler`.
- Company context: `CompanyContextMixin` sets `request.company`/`request.membership` from `X-Company-Id` or the default membership; role checks via `CompanyRolePermission.required_roles`.
- Caching: `core.cache.make_key(namespace, ...)` + `invalidate_namespace()`; catalog signals bump `catalog`/`search` namespaces.
- Models: inherit `UUIDModel`/`TimeStampedModel` from `apps.core.models`; slugs use `AutoSlugField(populate_from="name", overwrite_on_add=False)`.
- Admin: subclass `unfold.admin.ModelAdmin`; workflow buttons are `@action` methods in `actions_detail`/`actions_row`; dialogs use forms in `core/admin_forms.py`; navigation in `config/unfold.py`.
- Tests: add to `tests/`, use the `auth`, `buyer`, `staff`, `product`, `cart_with_item` fixtures; throttles are disabled in `settings/test.py`.
- Commit messages: plain, descriptive, no tool attribution lines.
