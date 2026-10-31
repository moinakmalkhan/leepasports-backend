from rest_framework import serializers

from apps.core.translation import TranslatedSerializerMixin

from .models import FAQ, Announcement, Banner, Page


class BannerSerializer(TranslatedSerializerMixin, serializers.ModelSerializer):
    class Meta:
        model = Banner
        fields = ("id", "title", "subtitle", "eyebrow", "image", "mobile_image", "cta_label", "cta_url", "placement", "theme")
        translated_fields = ("title", "subtitle", "eyebrow", "cta_label")


class AnnouncementSerializer(TranslatedSerializerMixin, serializers.ModelSerializer):
    class Meta:
        model = Announcement
        fields = ("id", "text", "url")
        translated_fields = ("text",)


class PageSerializer(TranslatedSerializerMixin, serializers.ModelSerializer):
    class Meta:
        model = Page
        fields = ("title", "slug", "body", "meta_description", "updated_at")
        translated_fields = ("title", "body", "meta_description")


class FAQSerializer(TranslatedSerializerMixin, serializers.ModelSerializer):
    class Meta:
        model = FAQ
        fields = ("id", "question", "answer", "category")
        translated_fields = ("question", "answer", "category")
