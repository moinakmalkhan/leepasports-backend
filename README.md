# Leepa Sports — B2B wholesale backend

Django 5.2 · DRF · PostgreSQL 16 · Redis · Celery · Channels (WebSockets)

Wholesale teamwear ordering platform for Leepa Sports (Sialkot). Buyers configure
garments (fabric × size/gender matrix × customisation), see live tiered pricing,
request quotes, check out with PO numbers / net terms, and track orders end to end.

## Features

| Area | What's included |
| --- | --- |
| Accounts | Email + password and Google sign-in (ID-token), JWT (15 min access, 7 day rotating refresh with blacklist), email verification, password reset, Argon2 hashing |
| Companies | Multi-user company accounts, roles (owner / admin / buyer / viewer), invitations, per-member spend limits, approval threshold, addresses, customer groups, net terms + credit limit |
| Catalog | Category tree (materialised path; only categories with products are exposed), products with fabric options, size × gender matrix, size surcharges, MOQ / increments / lead times, customization options, Postgres full-text generated column |
| Fabrics | 15 Pakistani mill fabrics with PKR/kg prices; product prices are derived from fabric × consumption + labour so prices follow mill rates |
| Pricing | Exchange rates, customer-group discounts, volume tiers (global or per product), contract price lists, live `/pricing/quote/` with full breakdown |
| Cart | Company carts, guest carts merged at login, server-side repricing, saved/requisition lists, reorder, quick order by SKU |
| Quotes (RFQ) | Submit cart as a quote, staff respond with negotiated prices, accept → order, auto-expiry |
| Orders | Checkout with address, freight estimate, PO number, bank transfer / net terms, approval workflow, status machine with history, tracking (carrier + number), public tracking by number + email, invoice / pro-forma data, dashboard summary |
| Payments | Pending payments, deposit / balance, proof upload, staff confirmation, bank account instructions |
| Notifications | In-app notifications (cursor paginated), realtime push over WebSocket, HTML emails for every important event, staff alerts |
| Search | Autocomplete with products + categories + fabrics, typo tolerance (trigram), synonyms, ranking with popularity and per-company boosts, trending queries, recommendations (frequently ordered together, personalised, recently viewed) |
| Chat | Company ↔ sales conversations (optionally pinned to an order/quote), WebSocket consumer with JWT auth, typing & read receipts, REST fallback with cursor pagination |
| Admin panel | django-unfold based operations panel: branded sidebar with live badges, KPI dashboard (revenue, orders, queues, charts), reports with CSV export, order workflow actions (confirm → production → QC → ship with tracking → deliver → complete, cancel), payment confirmation, quote publishing, company terms dialog, fabric bulk re-pricing, product duplicate/feature/publish, picking-list export |
| Platform | Consistent error envelope, consistent pagination, throttling, request ids, Redis caching with O(1) namespace invalidation, OpenAPI docs at `/api/docs/` |

## Admin panel

`/admin/` (set `ADMIN_URL` in production). Sign in with the staff demo user. The dashboard shows revenue and order charts, work queues (approvals, payments to confirm, production, late orders), quotes awaiting a reply and recent activity. Every list has saved filters, bulk actions and CSV export; order and quote detail pages carry workflow buttons that notify customers.

## Quick start (Docker, recommended for local development)

Requires Docker Desktop (or Docker Engine + Compose v2) and GNU make.

```bash
cp .env.example .env      # review values; every variable is documented in the file
make up                   # builds the image, starts Postgres, Redis, Mailpit, API, Celery worker + beat
make seed                 # demo catalog, fabrics, company and users (first time only)
```

| URL | What |
| --- | --- |
| http://localhost:8000/api/docs/ | Interactive API docs |
| http://localhost:8000/admin/ | Operations admin |
| http://localhost:8025 | Mailpit — every email the app sends |

Everyday targets (`make help` lists them all):

| Target | Does |
| --- | --- |
| `make up` / `make down` / `make restart` | start / stop / restart the stack (data is kept) |
| `make server` | infra + worker in the background, API in the foreground with logs (Ctrl+C to stop) |
| `make logs` (`make logs s=worker`) | follow logs |
| `make ps` | container status |
| `make migrate`, `make makemigrations a=app`, `make seed`, `make superuser` | Django management, run inside the api container |
| `make shell`, `make dbshell`, `make psql`, `make redis-cli`, `make exec` | shells |
| `make test`, `make lint`, `make format`, `make check` | quality gates (also run inside the container) |
| `make manage cmd="show_urls"` | any management command |
| `make backup` / `make restore f=backups/x.sql.gz` | database dumps |
| `make clean` | stop and **delete volumes** (database, redis, media) |

The API container runs `runserver` with the code bind-mounted, so edits reload instantly and WebSockets work (Daphne). Migrations run automatically on start; set `SEED_ON_START=1` in `.env` to seed on first boot.

### Without Docker for the app
```bash
make venv && source .venv/bin/activate
make infra                # just Postgres, Redis and Mailpit in Docker
make migrate && make seed
make server-local         # runserver_plus on :8000; `make worker-local` / `make beat-local` in other terminals
```

## Project layout

```
config/            settings (base / development / production / test), urls, asgi, celery
apps/core/         base models, pagination, permissions, throttles, error envelope, cache helpers
apps/accounts/     users, companies, members, invitations, addresses, auth services
apps/catalog/      categories, fabrics, sizes, products, seed command
apps/pricing/      customer groups, exchange rates, volume tiers, price lists, price engine
apps/cart/         carts, cart items, saved lists, quick order
apps/quotes/       RFQ workflow
apps/orders/       checkout, status machine, tracking, invoices, staff ops
apps/payments/     payments, proofs, bank accounts
apps/notifications in-app + email + realtime, event bus & handlers
apps/search/       FTS / trigram / synonyms / recommendations
apps/chat/         conversations, messages, consumers, JWT websocket middleware
templates/email/   transactional email templates
tests/             pytest API tests (run against PostgreSQL)
```

## API

- Base URL `/api/v1/`; interactive docs at `/api/docs/`.
- Auth: `Authorization: Bearer <access>`. Multi-company users pick the acting company with `X-Company-Id`.
- Guests: carts via `X-Cart-Token`; recently viewed / recommendations via `X-Session-Key`.
- WebSockets: `/ws/chat/<conversation-id>/?token=<access>` and `/ws/notifications/?token=<access>`.
- Errors always look like `{"detail": "...", "code": "...", "errors": {...}}`.
- Lists always look like `{"count", "page", "page_size", "total_pages", "next", "previous", "results"}` (feeds use cursor pagination: `{"next", "previous", "results"}`).

## Developer tooling (django-extensions)

| Command | What it does |
| --- | --- |
| `python manage.py shell_plus` | IPython shell with every model, common services and Q/F/Sum pre-imported; `SHELL_PLUS_PRINT_SQL=True` in development prints each query |
| `python manage.py runserver_plus` | Werkzeug dev server with the interactive debugger and `--print-sql` |
| `python manage.py show_urls` | Every API route with its view and name |
| `python manage.py runscript <name>` | Runs `scripts/<name>.py` (`reprice_catalog`, `overdue_invoices`, `sales_snapshot`) |
| `python manage.py graph_models -o docs/models.png` | ER diagram of all apps (needs Graphviz installed) |
| `python manage.py validate_templates` / `sqldiff` / `reset_db` / `generate_secret_key` | Template linting, schema drift, DB reset, key generation |

Models use django-extensions fields: `CreationDateTimeField`/`ModificationDateTimeField` on the shared base, `AutoSlugField` for every slug, `RandomCharField` for invitation tokens.

## Running tests

```bash
python -m pytest -q
```
