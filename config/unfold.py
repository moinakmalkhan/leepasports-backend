"""django-unfold configuration: Chobbar shop admin."""

from django.templatetags.static import static
from django.urls import reverse_lazy
from django.utils.translation import gettext_lazy as _


def _badge(path: str):
    return f"apps.core.admin_badges.{path}"


UNFOLD = {
    "SITE_TITLE": "Chobbar Admin",
    "SITE_HEADER": "Chobbar",
    "SITE_SUBHEADER": "chobbar.shop",
    "SITE_URL": "/",
    "SITE_ICON": {"light": lambda request: static("brand/logo-mark.svg"), "dark": lambda request: static("brand/logo-mark.svg")},
    "SITE_LOGO": {"light": lambda request: static("brand/logo.svg"), "dark": lambda request: static("brand/logo-dark.svg")},
    "SITE_FAVICONS": [
        {"rel": "icon", "sizes": "32x32", "type": "image/svg+xml", "href": lambda request: static("admin/chobbar-favicon.svg")}
    ],
    "SHOW_HISTORY": True,
    "SHOW_VIEW_ON_SITE": False,
    "SHOW_BACK_BUTTON": True,
    "ENVIRONMENT": "apps.core.admin_badges.environment",
    "DASHBOARD_CALLBACK": "apps.core.admin_dashboard.dashboard_callback",
    "LOGIN": {"image": lambda request: static("admin/login-bg.svg")},
    "STYLES": [lambda request: static("admin/chobbar.css")],
    "COLORS": {
        "base": {
            "50": "oklch(98.5% 0.001 106.423)",
            "100": "oklch(97% 0.001 106.424)",
            "200": "oklch(92.3% 0.003 48.717)",
            "300": "oklch(86.9% 0.005 56.366)",
            "400": "oklch(70.9% 0.01 56.259)",
            "500": "oklch(55.3% 0.013 58.071)",
            "600": "oklch(44.4% 0.011 73.639)",
            "700": "oklch(37.4% 0.01 67.558)",
            "800": "oklch(26.8% 0.007 34.298)",
            "900": "oklch(21.6% 0.006 56.043)",
            "950": "oklch(14.7% 0.004 49.25)",
        },
        "primary": {
            "50": "oklch(96.9% 0.015 12.422)",
            "100": "oklch(94.1% 0.03 12.58)",
            "200": "oklch(89.2% 0.058 10.001)",
            "300": "oklch(81% 0.117 11.638)",
            "400": "oklch(71.2% 0.194 13.428)",
            "500": "oklch(64.5% 0.246 16.439)",
            "600": "oklch(58.6% 0.253 17.585)",
            "700": "oklch(51.4% 0.222 16.935)",
            "800": "oklch(45.5% 0.188 13.697)",
            "900": "oklch(41% 0.159 10.272)",
            "950": "oklch(27.1% 0.105 12.094)",
        },
    },
    "COMMAND": {"search_models": True, "show_history": True},
    "SIDEBAR": {
        "show_search": True,
        "show_all_applications": False,
        "navigation": [
            {
                "title": _("Overview"),
                "items": [
                    {"title": _("Dashboard"), "icon": "dashboard", "link": reverse_lazy("admin:index")},
                    {"title": _("Reports"), "icon": "monitoring", "link": reverse_lazy("admin:reports")},
                ],
            },
            {
                "title": _("Sales"),
                "separator": True,
                "items": [
                    {
                        "title": _("Orders"),
                        "icon": "shopping_bag",
                        "link": reverse_lazy("admin:orders_order_changelist"),
                        "badge": _badge("new_orders"),
                    },
                    {
                        "title": _("Returns & exchanges"),
                        "icon": "assignment_return",
                        "link": reverse_lazy("admin:orders_returnrequest_changelist"),
                        "badge": _badge("open_returns"),
                    },
                    {
                        "title": _("Payments"),
                        "icon": "payments",
                        "link": reverse_lazy("admin:payments_payment_changelist"),
                        "badge": _badge("payments_to_confirm"),
                    },
                    {
                        "title": _("Support chat"),
                        "icon": "forum",
                        "link": reverse_lazy("admin:chat_conversation_changelist"),
                        "badge": _badge("open_conversations"),
                    },
                    {
                        "title": _("Shipping zones"),
                        "icon": "local_shipping",
                        "link": reverse_lazy("admin:orders_shippingzone_changelist"),
                    },
                    {
                        "title": _("Bank accounts"),
                        "icon": "account_balance",
                        "link": reverse_lazy("admin:payments_bankaccount_changelist"),
                    },
                ],
            },
            {
                "title": _("Catalog"),
                "separator": True,
                "items": [
                    {"title": _("Products"), "icon": "apparel", "link": reverse_lazy("admin:catalog_product_changelist")},
                    {
                        "title": _("Inventory"),
                        "icon": "inventory_2",
                        "link": reverse_lazy("admin:catalog_productvariant_changelist"),
                        "badge": _badge("low_stock"),
                    },
                    {"title": _("Categories"), "icon": "category", "link": reverse_lazy("admin:catalog_category_changelist")},
                    {
                        "title": _("Collections"),
                        "icon": "collections_bookmark",
                        "link": reverse_lazy("admin:catalog_collection_changelist"),
                    },
                    {"title": _("Colours"), "icon": "palette", "link": reverse_lazy("admin:catalog_color_changelist")},
                    {"title": _("Size charts"), "icon": "straighten", "link": reverse_lazy("admin:catalog_sizegroup_changelist")},
                    {
                        "title": _("Back-in-stock requests"),
                        "icon": "notifications_active",
                        "link": reverse_lazy("admin:catalog_stockalert_changelist"),
                    },
                ],
            },
            {
                "title": _("Marketing"),
                "separator": True,
                "items": [
                    {
                        "title": _("Coupons"),
                        "icon": "confirmation_number",
                        "link": reverse_lazy("admin:promotions_coupon_changelist"),
                    },
                    {"title": _("Banners"), "icon": "view_carousel", "link": reverse_lazy("admin:content_banner_changelist")},
                    {
                        "title": _("Announcement bar"),
                        "icon": "campaign",
                        "link": reverse_lazy("admin:content_announcement_changelist"),
                    },
                    {"title": _("Pages"), "icon": "article", "link": reverse_lazy("admin:content_page_changelist")},
                    {"title": _("FAQs"), "icon": "help", "link": reverse_lazy("admin:content_faq_changelist")},
                    {
                        "title": _("Newsletter"),
                        "icon": "mail",
                        "link": reverse_lazy("admin:accounts_newslettersubscriber_changelist"),
                    },
                    {
                        "title": _("Search synonyms"),
                        "icon": "spellcheck",
                        "link": reverse_lazy("admin:search_synonym_changelist"),
                    },
                    {
                        "title": _("Search log"),
                        "icon": "search_insights",
                        "link": reverse_lazy("admin:search_searchquery_changelist"),
                    },
                ],
            },
            {
                "title": _("Customers"),
                "separator": True,
                "items": [
                    {"title": _("Customers"), "icon": "person", "link": reverse_lazy("admin:accounts_user_changelist")},
                    {
                        "title": _("Reviews"),
                        "icon": "reviews",
                        "link": reverse_lazy("admin:reviews_review_changelist"),
                        "badge": _badge("pending_reviews"),
                    },
                    {"title": _("Wishlists"), "icon": "favorite", "link": reverse_lazy("admin:cart_wishlist_changelist")},
                    {"title": _("Abandoned bags"), "icon": "shopping_basket", "link": reverse_lazy("admin:cart_cart_changelist")},
                ],
            },
            {
                "title": _("System"),
                "separator": True,
                "collapsible": True,
                "items": [
                    {
                        "title": _("Notifications"),
                        "icon": "notifications",
                        "link": reverse_lazy("admin:notifications_notification_changelist"),
                    },
                    {
                        "title": _("Scheduled tasks"),
                        "icon": "schedule",
                        "link": reverse_lazy("admin:django_celery_beat_periodictask_changelist"),
                        "permission": lambda request: request.user.is_superuser,
                    },
                    {
                        "title": _("Staff groups"),
                        "icon": "admin_panel_settings",
                        "link": reverse_lazy("admin:auth_group_changelist"),
                        "permission": lambda request: request.user.is_superuser,
                    },
                ],
            },
        ],
    },
    "SITE_VIEWS": [("reports/", "reports", "apps.core.admin_views.ReportsView")],
}
