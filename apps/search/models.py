from django.db import models


class SearchQuery(models.Model):
    """Every search is logged (async) to power trending queries, zero-result
    reports and 'did you mean' suggestions."""

    query = models.CharField(max_length=200)
    normalized = models.CharField(max_length=200, db_index=True)
    result_count = models.PositiveIntegerField(default=0)
    user = models.ForeignKey("accounts.User", null=True, blank=True, on_delete=models.SET_NULL, related_name="+")
    company = models.ForeignKey("accounts.Company", null=True, blank=True, on_delete=models.SET_NULL, related_name="+")
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        indexes = [models.Index(fields=["-created_at"]), models.Index(fields=["normalized", "-created_at"])]

    def __str__(self):
        return self.query


class Synonym(models.Model):
    """Sportswear jargon expansion: 'jersey' → 'shirt top', 'kit' → 'uniform set'."""

    term = models.CharField(max_length=60, unique=True)
    expansions = models.CharField(max_length=300, help_text="Comma separated")

    def __str__(self):
        return self.term
