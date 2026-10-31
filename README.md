# Chobbar — shop API

Django 5.2 · DRF · PostgreSQL 16 · Redis · Celery · Channels (WebSockets)

Backend for **chobbar.shop**, a direct-to-consumer activewear and streetwear store made in Sialkot.
It serves the Next.js storefront, the Android app and the operations admin.

## Features

| Area | What's included |
| --- | --- |
| Accounts | Email + password and Google sign-in, JWT (15 min access, 7 day rotating refresh with blacklist), email verification, password reset, saved addresses with one default, newsletter, profile with preferred language, account deletion (anonymised) |
| Catalog | Category tree (materialised path; empty categories hidden), collections with schedules, colours and size charts, products with colour × size **variants**, per-variant SKU/stock/price override, sale (compare-at) pricing, image per colour, facets (sizes, colours, price range), back-in-stock alerts, full-text search column |
| Bag & wishlist | Guest bags by token merged on sign-in, server-side pricing and stock checks on every read, quantity limits, coupons, wishlist |
| Promotions | Coupons: percentage (with cap), fixed amount, free shipping; minimum spend, first-order-only, per-user limits, category/product restrictions, schedules, redemption log |
| Checkout & orders | Guest or account checkout, Pakistan shipping zones (city → province → default) with free-delivery thresholds and COD fee, cash on delivery, bank transfer / JazzCash / EasyPaisa with receipt upload, card stub; atomic stock decrement with row locks; order lifecycle (pending → confirmed → packing → shipped → out for delivery → delivered → completed, cancel/return), tracking, public tracking by order number + email or phone, reorder |
| Returns | Refund or exchange requests within 14 days, per-item quantities, photo upload, staff resolution with automatic restock and refund recording |
| Reviews | Verified-purchase reviews go live instantly, others are moderated; fit feedback, photos, helpful votes, staff replies, rating histogram, denormalised product rating |
| Content | Hero/promo banners, announcement bar, static pages (shipping, returns, size guide…), FAQs — one cached storefront call |
| Languages | English, Urdu, Arabic. Language from explicit choice → visitor country (CDN header) → `Accept-Language`. Translated catalog and content via a JSONB `translations` column; caches are language-scoped; `/api/v1/locale/` tells clients what to render (incl. RTL) |
| Notifications | In-app feed (cursor paginated), realtime WebSocket push, HTML emails for every order/return/payment event, back-in-stock emails, staff alerts |
| Search | Postgres FTS + trigram typo tolerance + synonyms, autocomplete with products/categories/collections, personalised ranking, trending queries, recommendations, recently viewed |
| Support chat | Customer ↔ staff conversations (optionally about an order) over WebSockets with REST fallback |
| Admin | django-unfold panel: KPI dashboard (revenue, AOV, queues, charts, top cities), reports with CSV export, order workflow buttons (confirm, pack, ship with courier + tracking, deliver, cancel with restock), payment verification, returns resolution, review moderation, inventory with stock adjustments and low-stock badge, sale pricing tool, coupon performance, banners, abandoned bags |

## Quick start (Docker)

```bash
cp .env.example .env      # every variable is documented in the file
make up                   # Postgres, Redis, Mailpit, API, Celery worker + beat
make seed                 # demo catalog (34 products, 529 variants), content, coupons, accounts
```

| URL | What |
| --- | --- |
| http://localhost:8000/api/docs/ | Interactive API docs |
| http://localhost:8000/admin/ | Admin — admin@chobbar.shop / Admin!Chobbar2026 |
| http://localhost:8025 | Mailpit — every email the app sends |

Demo customer: ali@example.com / Customer!2026. Coupons: `WELCOME10`, `CHOBBAR500`, `FREESHIP`.

`make help` lists every target (`server`, `logs`, `migrate`, `shell`, `test`, `lint`, `backup`, …). Without Docker for the app: `make venv`, `make infra`, `make server-local`.

## Languages & location

The CDN in front of chobbar.shop (Cloudflare recommended) adds the visitor's country header (`CF-IPCountry`).
Pakistan → Urdu, Arab League countries → Arabic, everyone else → English, unless the visitor picked a language
(`?lang=`, `X-Language` header or `chobbar_lang` cookie). Translate products, categories, collections, colours,
banners, pages and FAQs in the admin's "Translations" section (JSON per language; missing keys fall back to English).

## API conventions

- Base URL `/api/v1/`. Auth: `Authorization: Bearer <access>`. Guests send `X-Cart-Token` (bag) and `X-Session-Key` (recently viewed).
- Language: `Accept-Language` or `X-Language: ur|ar|en`; responses carry `Content-Language`.
- Errors: `{"detail", "code", "errors?"}`. Lists: `{"count", "page", "page_size", "total_pages", "next", "previous", "results"}`; feeds use cursors.
- WebSockets: `/ws/notifications/?token=<access>`, `/ws/chat/<conversation-id>/?token=<access>`.

## Tests

```bash
make test
```
