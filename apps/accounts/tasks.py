from celery import shared_task


@shared_task
def flush_expired_tokens():
    """Purge expired refresh tokens from the blacklist tables (daily)."""
    from django.core.management import call_command

    call_command("flushexpiredtokens")
