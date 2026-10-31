import django_filters
from django.db.models import Q

from .models import Category, Fabric, Gender, Product


class ProductFilter(django_filters.FilterSet):
    category = django_filters.CharFilter(method="filter_category")
    gender = django_filters.MultipleChoiceFilter(choices=Gender.choices, method="filter_gender")
    fabric = django_filters.CharFilter(method="filter_fabric")
    quality = django_filters.MultipleChoiceFilter(
        choices=Fabric.Quality.choices, field_name="fabric_options__fabric__quality", distinct=True
    )
    min_price = django_filters.NumberFilter(field_name="base_price", lookup_expr="gte")
    max_price = django_filters.NumberFilter(field_name="base_price", lookup_expr="lte")
    max_moq = django_filters.NumberFilter(field_name="min_order_quantity", lookup_expr="lte")
    featured = django_filters.BooleanFilter(field_name="is_featured")
    new = django_filters.BooleanFilter(field_name="is_new")
    tag = django_filters.CharFilter(method="filter_tag")
    ids = django_filters.CharFilter(method="filter_ids")

    class Meta:
        model = Product
        fields = ()

    def filter_category(self, qs, name, value):
        slugs = [s for s in value.split(",") if s]
        cats = Category.objects.filter(slug__in=slugs, is_active=True).values_list("path", flat=True)
        if not cats:
            return qs.none()
        q = Q()
        for path in cats:
            q |= Q(category__path__startswith=path)
        return qs.filter(q)

    def filter_gender(self, qs, name, value):
        return qs.filter(genders__overlap=list(value)) if value else qs

    def filter_fabric(self, qs, name, value):
        return qs.filter(fabric_options__fabric__slug__in=value.split(",")).distinct()

    def filter_tag(self, qs, name, value):
        return qs.filter(tags__contains=[value])

    def filter_ids(self, qs, name, value):
        return qs.filter(uid__in=[v for v in value.split(",") if v][:50])
