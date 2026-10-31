from django.contrib import admin

from .models import SearchQuery, Synonym


@admin.register(SearchQuery)
class SearchQueryAdmin(admin.ModelAdmin):
    list_display = ("query", "result_count", "user", "created_at")
    list_filter = ("result_count",)
    search_fields = ("query",)
    date_hierarchy = "created_at"


@admin.register(Synonym)
class SynonymAdmin(admin.ModelAdmin):
    list_display = ("term", "expansions")
    search_fields = ("term",)
