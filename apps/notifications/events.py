"""Tiny in-process event bus.

Domain services call `emit("order.placed", order_id=...)`; handlers (see
`handlers.py`) decide who gets an email, an in-app notification and a realtime
push. Keeping this indirection means the order service never imports the mail
system, and new side-effects are one handler away.

Handlers run in a Celery task so the HTTP request never waits on SMTP.
"""

import logging
from collections import defaultdict
from collections.abc import Callable

logger = logging.getLogger("apps.notifications")

_registry: dict[str, list[Callable]] = defaultdict(list)


def on(event: str):
    def decorator(fn):
        _registry[event].append(fn)
        return fn

    return decorator


def emit(event: str, **payload):
    from .tasks import dispatch_event

    dispatch_event.delay(event, payload)


def dispatch(event: str, payload: dict):
    for handler in _registry.get(event, ()):
        try:
            handler(**payload)
        except Exception:  # pragma: no cover - never let one handler kill the rest
            logger.exception("Notification handler %s failed for %s", handler.__name__, event)
