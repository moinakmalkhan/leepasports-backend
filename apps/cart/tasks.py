from celery import shared_task


@shared_task
def purge_abandoned_guest_carts():
    from .services import purge_guest_carts

    purge_guest_carts()
