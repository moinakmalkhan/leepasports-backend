# Chobbar — backend (Django)

Direct-to-consumer activewear store **chobbar.shop** (made in Sialkot, Pakistan). This repo is the API + admin.
Clients: Next.js storefront (`leepasports-frontend`) and the Kotlin Android app (`chobbar-android`), both on `/api/v1/`.

## Stack
Django 5.2 · DRF · SimpleJWT (rotating refresh + blacklist) · PostgreSQL 16 (FTS, trigram, JSONB) · Redis (cache, Celery broker, Channels layer) · Celery + beat · Channels/Daphne (WebSockets) · django-unfold admin · django-extensions.

## Run locally
```bash
cp .env.example .env     # every variable documented there (django-environ reads .env)
make up                  # Docker: Postgres, Redis, Mailpit, API (:8000), Celery worker + beat
make seed                # demo catalog + users (first time)
make server              # alternative: API in the foreground with logs
```
Admin: http://localhost:8000/admin/ (admin@chobbar.shop / Admin!Chobbar2026). API docs: /api/docs/. Emails: http://localhost:8025.
Demo customer: ali@example.com / Customer!2026. Coupons: WELCOME10, CHOBBAR500, FREESHIP.
Without Docker for the app: `make venv`, `make infra`, `make server-local`.

## Commands
- `make test` — API tests against Postgres (runs inside the api container when the stack is up, else in your venv); `make test-fast` reuses the test DB
- `make lint` / `make format` — ruff check + format (line length 130)
- `make logs`, `make ps`, `make shell`, `make psql`, `make exec`, `make manage cmd="..."` — see `make help`
- `python manage.py shell_plus` — IPython with models + services preloaded (prints SQL in dev)
- `python manage.py show_urls`, `runscript <name>` (scripts/), `graph_models`
- `python manage.py makemigrations --check --dry-run` before committing model changes

## Layout
```
config/settings/{base,development,production,test}.py   config/unfold.py (admin sidebar/branding)
apps/core          base models, TranslatableModel + i18n (language detection, LanguageMiddleware), pagination, permissions,
                   throttles, error envelope, language-scoped cache keys, admin dashboard/reports/forms/badges
apps/accounts      User (email + Google, preferred language), Address, NewsletterSubscriber
apps/catalog       Category (materialised path), Collection, Color, SizeGroup/Size, Product, ProductVariant (stock), ProductImage, StockAlert, seed command (+ _translations.py)
apps/promotions    Coupon, CouponRedemption, services.validate_coupon
apps/cart          Cart/CartItem (variant lines), Wishlist; services.compute_totals is the pricing source of truth
apps/orders        ShippingZone, Order, OrderItem, OrderStatusHistory, ReturnRequest/ReturnItem; checkout, lifecycle, returns, tracking
apps/payments      Payment (bank transfer proof, card stub), BankAccount
apps/reviews       Review (verified purchase / moderation), ReviewVote
apps/content       Banner, Announcement, Page, FAQ (one cached /content/storefront/ call)
apps/notifications in-app Notification, event bus (events.emit → handlers.py), emails (templates/email), realtime push
apps/search        FTS + trigram + synonyms, suggest, recommendations, search log
apps/chat          support Conversation/Message, JWT websocket middleware, consumers
tests/             pytest-django suite; conftest seeds the catalog once per session
```

## Conventions (follow these)
- Business logic lives in `services.py` (and `selectors.py`) — views stay thin. Multi-write operations are wrapped in `transaction.atomic` and use `select_for_update` where money/credit/status changes.
- Side effects go through `apps.notifications.events.emit("event.name", **ids)` from `after_commit(...)`; add handlers in `notifications/handlers.py`. Pass ids, not model instances (Celery JSON).
- Prices and stock are never trusted from the client: `cart.services.compute_totals` reprices every read; checkout locks variants (`select_for_update().order_by("pk")`) and decrements stock atomically. Cancels and completed returns restock.
- Translatable models inherit `TranslatableModel` (JSONB `translations`); serializers add `TranslatedSerializerMixin` + `Meta.translated_fields`; use `core.i18n.translate(obj, field)` elsewhere. Cache keys from `make_key` already include the language.
- Public ids are `uid` (UUID); integer pks never leave the API. Lists use `StandardPagination` (`count/page/page_size/total_pages/next/previous/results`), feeds use cursor pagination.
- Errors always return `{"detail", "code", "errors?"}` via `core.exceptions.api_exception_handler`.
- Guests are first-class: carts by `X-Cart-Token`, checkout by email + phone, tracking by order number + email/phone.
- Caching: `core.cache.make_key(namespace, ...)` + `invalidate_namespace()`; catalog signals bump `catalog`/`search` namespaces.
- Models: inherit `UUIDModel`/`TimeStampedModel` from `apps.core.models`; slugs use `AutoSlugField(populate_from="name", overwrite_on_add=False)`.
- Admin: subclass `unfold.admin.ModelAdmin`; workflow buttons are `@action` methods in `actions_detail`/`actions_row`; dialogs use forms in `core/admin_forms.py`; navigation in `config/unfold.py`.
- Tests: add to `tests/`, use the `api`, `auth`, `customer`, `staff`, `product`, `variant` fixtures and `ADDRESS`; throttles are disabled in `settings/test.py`.
- Commit messages: plain, descriptive, no tool attribution lines.
