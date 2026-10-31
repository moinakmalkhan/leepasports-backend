"""django-unfold configuration: Leepa Sports operations panel."""

from django.templatetags.static import static
from django.urls import reverse_lazy
from django.utils.translation import gettext_lazy as _


def _badge(path: str):
    return f"apps.core.admin_badges.{path}"


UNFOLD = {
    "SITE_TITLE": "Leepa Sports Operations",
    "SITE_HEADER": "Leepa Sports",
    "SITE_SUBHEADER": "Wholesale operations",
    "SITE_URL": "/",
    "SITE_SYMBOL": "sports_soccer",
    "SITE_FAVICONS": [
        {"rel": "icon", "sizes": "32x32", "type": "image/svg+xml", "href": lambda request: static("admin/leepa-favicon.svg")}
    ],
    "SHOW_HISTORY": True,
    "SHOW_VIEW_ON_SITE": False,
    "SHOW_BACK_BUTTON": True,
    "ENVIRONMENT": "apps.core.admin_badges.environment",
    "DASHBOARD_CALLBACK": "apps.core.admin_dashboard.dashboard_callback",
    "LOGIN": {"image": lambda request: static("admin/login-bg.svg")},
    "STYLES": [lambda request: static("admin/leepa.css")],
    "COLORS": {
        "base": {
            "50": "oklch(98.4% 0.003 247.858)",
            "100": "oklch(96.8% 0.007 247.896)",
            "200": "oklch(92.9% 0.013 255.508)",
            "300": "oklch(86.9% 0.022 252.894)",
            "400": "oklch(70.4% 0.04 256.788)",
            "500": "oklch(55.4% 0.046 257.417)",
            "600": "oklch(44.6% 0.043 257.281)",
            "700": "oklch(37.2% 0.044 257.287)",
            "800": "oklch(27.9% 0.041 260.031)",
            "900": "oklch(20.8% 0.042 265.755)",
            "950": "oklch(12.9% 0.042 264.695)",
        },
        "primary": {
            "50": "oklch(98% 0.016 73.684)",
            "100": "oklch(95.4% 0.038 75.164)",
            "200": "oklch(90.1% 0.076 70.697)",
            "300": "oklch(83.7% 0.128 66.29)",
            "400": "oklch(75% 0.183 55.934)",
            "500": "oklch(70.5% 0.213 47.604)",
            "600": "oklch(64.6% 0.222 41.116)",
            "700": "oklch(55.3% 0.195 38.402)",
            "800": "oklch(47% 0.157 37.304)",
            "900": "oklch(40.8% 0.123 38.172)",
            "950": "oklch(26.6% 0.079 36.259)",
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
                        "badge": _badge("open_orders"),
                    },
                    {
                        "title": _("Quotes (RFQ)"),
                        "icon": "request_quote",
                        "link": reverse_lazy("admin:quotes_quote_changelist"),
                        "badge": _badge("pending_quotes"),
                    },
                    {
                        "title": _("Payments"),
                        "icon": "payments",
                        "link": reverse_lazy("admin:payments_payment_changelist"),
                        "badge": _badge("payments_to_confirm"),
                    },
                    {
                        "title": _("Conversations"),
                        "icon": "forum",
                        "link": reverse_lazy("admin:chat_conversation_changelist"),
                        "badge": _badge("open_conversations"),
                    },
                    {
                        "title": _("Shipping methods"),
                        "icon": "local_shipping",
                        "link": reverse_lazy("admin:orders_shippingmethod_changelist"),
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
                    {"title": _("Categories"), "icon": "category", "link": reverse_lazy("admin:catalog_category_changelist")},
                    {
                        "title": _("Fabrics & mill prices"),
                        "icon": "texture",
                        "link": reverse_lazy("admin:catalog_fabric_changelist"),
                    },
                    {"title": _("Size charts"), "icon": "straighten", "link": reverse_lazy("admin:catalog_sizegroup_changelist")},
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
                "title": _("Pricing"),
                "separator": True,
                "items": [
                    {
                        "title": _("Customer groups"),
                        "icon": "groups",
                        "link": reverse_lazy("admin:pricing_customergroup_changelist"),
                    },
                    {"title": _("Volume tiers"), "icon": "stairs", "link": reverse_lazy("admin:pricing_volumetier_changelist")},
                    {
                        "title": _("Contract price lists"),
                        "icon": "receipt_long",
                        "link": reverse_lazy("admin:pricing_pricelistitem_changelist"),
                    },
                    {
                        "title": _("Exchange rates"),
                        "icon": "currency_exchange",
                        "link": reverse_lazy("admin:pricing_exchangerate_changelist"),
                    },
                ],
            },
            {
                "title": _("Customers"),
                "separator": True,
                "items": [
                    {
                        "title": _("Companies"),
                        "icon": "domain",
                        "link": reverse_lazy("admin:accounts_company_changelist"),
                        "badge": _badge("unverified_companies"),
                    },
                    {"title": _("Users"), "icon": "person", "link": reverse_lazy("admin:accounts_user_changelist")},
                    {
                        "title": _("Invitations"),
                        "icon": "mail",
                        "link": reverse_lazy("admin:accounts_companyinvitation_changelist"),
                    },
                    {"title": _("Saved lists"), "icon": "bookmarks", "link": reverse_lazy("admin:cart_savedlist_changelist")},
                    {"title": _("Carts"), "icon": "shopping_cart", "link": reverse_lazy("admin:cart_cart_changelist")},
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
    # (url, name, dotted path to view)
    "SITE_VIEWS": [("reports/", "reports", "apps.core.admin_views.ReportsView")],
}
