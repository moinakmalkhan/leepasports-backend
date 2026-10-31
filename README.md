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
| Platform | Consistent error envelope, consistent pagination, throttling, request ids, Redis caching with O(1) namespace invalidation, OpenAPI docs at `/api/docs/` |

## Quick start

```bash
python -m venv .venv && . .venv/bin/activate
pip install -r requirements-dev.txt
cp .env.example .env            # set SECRET_KEY / JWT_SIGNING_KEY
createdb leepasports            # needs PostgreSQL 16 + redis running
python manage.py migrate
python manage.py seed_catalog --demo
python manage.py runserver
```

Or with Docker: `docker compose up --build` (API on :8000, Postgres, Redis, Celery worker + beat).

Demo logins after `seed_catalog --demo`:

| Role | Email | Password |
| --- | --- | --- |
| Staff / admin | admin@leepasports.com | Admin!Leepa2026 |
| Company owner | buyer@riversidefc.com | Buyer!Leepa2026 |
| Company buyer (limit 2,000) | coach@riversidefc.com | Coach!Leepa2026 |

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

## Running tests

```bash
python -m pytest -q
```
