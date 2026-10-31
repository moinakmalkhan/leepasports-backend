from django.contrib import admin
from django.db.models import Count
from unfold.admin import ModelAdmin
from unfold.contrib.filters.admin import RangeDateFilter, RangeNumericFilter
from unfold.decorators import display

from .models import SearchQuery, Synonym


@admin.register(SearchQuery)
class SearchQueryAdmin(ModelAdmin):
    list_display = ("query", "result_count", "zero_results", "user", "created_at")
    list_filter = (("result_count", RangeNumericFilter), ("created_at", RangeDateFilter))
    search_fields = ("query",)
    date_hierarchy = "created_at"
    list_select_related = ("user",)

    def has_add_permission(self, request):
        return False

    @display(description="No results", boolean=True)
    def zero_results(self, obj):
        return obj.result_count == 0

    def changelist_view(self, request, extra_context=None):
        extra_context = extra_context or {}
        top_zero = SearchQuery.objects.filter(result_count=0).values("normalized").annotate(n=Count("id")).order_by("-n")[:10]
        extra_context["zero_result_queries"] = list(top_zero)
        return super().changelist_view(request, extra_context=extra_context)


@admin.register(Synonym)
class SynonymAdmin(ModelAdmin):
    list_display = ("term", "expansions")
    search_fields = ("term", "expansions")
    list_editable = ("expansions",)

    def save_model(self, request, obj, form, change):
        super().save_model(request, obj, form, change)
        from django.core.cache import cache

        cache.delete("search:synonyms")
