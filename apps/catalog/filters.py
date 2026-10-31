import django_filters
from django.db.models import Q

from .models import Category, Gender, Product


class ProductFilter(django_filters.FilterSet):
    category = django_filters.CharFilter(method="filter_category")
    collection = django_filters.CharFilter(field_name="collections__slug")
    gender = django_filters.MultipleChoiceFilter(choices=Gender.choices)
    size = django_filters.CharFilter(method="filter_size")
    color = django_filters.CharFilter(method="filter_color")
    min_price = django_filters.NumberFilter(field_name="price", lookup_expr="gte")
    max_price = django_filters.NumberFilter(field_name="price", lookup_expr="lte")
    in_stock = django_filters.BooleanFilter(method="filter_in_stock")
    on_sale = django_filters.BooleanFilter(method="filter_on_sale")
    featured = django_filters.BooleanFilter(field_name="is_featured")
    new = django_filters.BooleanFilter(field_name="is_new")
    min_rating = django_filters.NumberFilter(field_name="rating_avg", lookup_expr="gte")
    tag = django_filters.CharFilter(method="filter_tag")
    brand = django_filters.CharFilter(field_name="brand", lookup_expr="iexact")
    ids = django_filters.CharFilter(method="filter_ids")
    slugs = django_filters.CharFilter(method="filter_slugs")

    class Meta:
        model = Product
        fields = ()

    def filter_category(self, qs, name, value):
        slugs = [s for s in value.split(",") if s]
        paths = Category.objects.filter(slug__in=slugs, is_active=True).values_list("path", flat=True)
        if not paths:
            return qs.none()
        q = Q()
        for path in paths:
            q |= Q(category__path__startswith=path)
        return qs.filter(q)

    def filter_size(self, qs, name, value):
        labels = [v.upper() for v in value.split(",") if v]
        return qs.filter(variants__size__label__in=labels, variants__is_active=True, variants__stock__gt=0).distinct()

    def filter_color(self, qs, name, value):
        return qs.filter(variants__color__slug__in=value.split(","), variants__is_active=True).distinct()

    def filter_in_stock(self, qs, name, value):
        return qs.filter(total_stock__gt=0) if value else qs.filter(total_stock__lte=0)

    def filter_on_sale(self, qs, name, value):
        return qs.filter(compare_at_price__gt=models_f("price")) if value else qs

    def filter_tag(self, qs, name, value):
        return qs.filter(tags__contains=[value])

    def filter_ids(self, qs, name, value):
        return qs.filter(uid__in=[v for v in value.split(",") if v][:50])

    def filter_slugs(self, qs, name, value):
        return qs.filter(slug__in=[v for v in value.split(",") if v][:100])


def models_f(name):
    from django.db.models import F

    return F(name)
