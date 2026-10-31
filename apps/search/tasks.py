from celery import shared_task


@shared_task
def log_search(query: str, normalized: str, result_count: int, user_id=None, company_id=None):
    from .models import SearchQuery

    SearchQuery.objects.create(
        query=query[:200], normalized=normalized, result_count=result_count, user_id=user_id, company_id=company_id
    )
