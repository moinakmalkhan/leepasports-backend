"""
Seed the Chobbar retail catalog: categories, colours, sizes, products with
variants and stock, collections, coupons, shipping zones, banners, pages, FAQs,
bank accounts and a demo customer.

    python manage.py seed_catalog            # idempotent
    python manage.py seed_catalog --demo     # + demo accounts & sample orders
"""

import random
from datetime import timedelta
from decimal import Decimal

from django.core.management.base import BaseCommand
from django.db import transaction
from django.utils import timezone
from django.utils.text import slugify

from apps.catalog.models import Category, Collection, Color, Product, ProductVariant, Size, SizeGroup
from apps.content.models import FAQ, Announcement, Page
from apps.orders.models import ShippingZone
from apps.payments.models import BankAccount
from apps.promotions.models import Coupon
from apps.search.models import Synonym

from . import _translations as tr

D = Decimal

COLORS = [
    ("Black", "#111111"),
    ("White", "#f5f5f5"),
    ("Navy", "#1e2a4a"),
    ("Charcoal", "#3b3b3b"),
    ("Grey Marl", "#9a9a9a"),
    ("Olive", "#5b6b3a"),
    ("Maroon", "#6b1e2b"),
    ("Royal Blue", "#1d4ed8"),
    ("Red", "#dc2626"),
    ("Sand", "#d6c3a5"),
    ("Forest", "#1f4d3a"),
    ("Rust", "#b7410e"),
]

SIZE_GROUPS = {
    "Tops": (
        ["XS", "S", "M", "L", "XL", "XXL"],
        [
            {"size": s, "chest": c, "length": ln}
            for s, c, ln in [
                ("XS", "86-91", "66"),
                ("S", "91-96", "68"),
                ("M", "96-101", "70"),
                ("L", "101-106", "72"),
                ("XL", "106-111", "74"),
                ("XXL", "111-116", "76"),
            ]
        ],
    ),
    "Bottoms": (
        ["28", "30", "32", "34", "36", "38"],
        [
            {"size": s, "waist": w, "inseam": "78"}
            for s, w in [("28", "71"), ("30", "76"), ("32", "81"), ("34", "86"), ("36", "91"), ("38", "96")]
        ],
    ),
    "Women Tops": (
        ["XS", "S", "M", "L", "XL"],
        [
            {"size": s, "bust": b, "length": ln}
            for s, b, ln in [
                ("XS", "80-84", "60"),
                ("S", "84-88", "62"),
                ("M", "88-92", "64"),
                ("L", "92-97", "66"),
                ("XL", "97-102", "68"),
            ]
        ],
    ),
    "Kids": (["6-7Y", "8-9Y", "10-11Y", "12-13Y"], []),
    "One Size": (["OS"], []),
}

CATEGORIES = [
    (
        "men",
        "Men",
        "shirt",
        [
            ("men-tees", "T-Shirts"),
            ("men-polos", "Polos"),
            ("men-hoodies", "Hoodies & Sweatshirts"),
            ("men-joggers", "Joggers & Track Pants"),
            ("men-shorts", "Shorts"),
            ("men-jackets", "Jackets"),
            ("men-tracksuits", "Tracksuits"),
        ],
    ),
    (
        "women",
        "Women",
        "sparkles",
        [
            ("women-tops", "Tops & Tees"),
            ("women-leggings", "Leggings"),
            ("women-hoodies", "Hoodies"),
            ("women-sets", "Co-ord Sets"),
            ("women-sports-bras", "Sports Bras"),
        ],
    ),
    (
        "activewear",
        "Activewear",
        "dumbbell",
        [
            ("training-tees", "Training Tees"),
            ("compression", "Compression"),
            ("running", "Running"),
            ("gym-shorts", "Gym Shorts"),
        ],
    ),
    ("kids", "Kids", "baby", [("kids-tees", "Tees"), ("kids-tracksuits", "Tracksuits")]),
    (
        "accessories",
        "Accessories",
        "package",
        [("caps", "Caps & Beanies"), ("socks", "Socks"), ("bags", "Bags"), ("bottles", "Bottles & Towels")],
    ),
]

# sku, name, category, gender, price, compare_at, size group, colours, material, tags, featured, new, specs, short
PRODUCTS = [
    (
        "CH-TEE-001",
        "Essential Heavyweight Tee",
        "men-tees",
        "men",
        1890,
        2490,
        "Tops",
        ["Black", "White", "Olive", "Sand"],
        "240 GSM combed cotton",
        ["tee", "basic", "heavyweight"],
        True,
        True,
        {"Fit": "Relaxed", "Neck": "Rib crew", "Print": "None"},
        "Boxy, heavyweight and built to outlast trends.",
    ),
    (
        "CH-TEE-002",
        "Chobbar Logo Tee",
        "men-tees",
        "men",
        1690,
        None,
        "Tops",
        ["Black", "White", "Maroon", "Navy"],
        "200 GSM combed cotton",
        ["tee", "logo", "graphic"],
        True,
        False,
        {"Fit": "Regular", "Neck": "Rib crew", "Print": "Screen print"},
        "The signature wordmark across the chest. Pre-shrunk.",
    ),
    (
        "CH-TEE-003",
        "Oversized Washed Tee",
        "men-tees",
        "men",
        2290,
        2790,
        "Tops",
        ["Charcoal", "Rust", "Sand"],
        "220 GSM enzyme-washed cotton",
        ["tee", "oversized", "washed"],
        False,
        True,
        {"Fit": "Oversized", "Neck": "Drop shoulder", "Wash": "Enzyme"},
        "Garment-washed for that broken-in feel from day one.",
    ),
    (
        "CH-POL-001",
        "Pique Polo",
        "men-polos",
        "men",
        2490,
        None,
        "Tops",
        ["Navy", "White", "Forest", "Black"],
        "Cotton-blend pique, 210 GSM",
        ["polo", "smart"],
        False,
        False,
        {"Collar": "Rib knit", "Placket": "3 button"},
        "Clean pique polo for weekends and work.",
    ),
    (
        "CH-HOD-001",
        "Fleece Pullover Hoodie",
        "men-hoodies",
        "men",
        3990,
        4990,
        "Tops",
        ["Black", "Grey Marl", "Maroon", "Olive"],
        "320 GSM brushed fleece, 65/35",
        ["hoodie", "fleece", "winter"],
        True,
        False,
        {"Hood": "Double layer", "Pocket": "Kangaroo", "Cuffs": "Rib 1x1"},
        "Thick brushed fleece, roomy hood, built for Lahore winters.",
    ),
    (
        "CH-HOD-002",
        "Zip-Through Hoodie",
        "men-hoodies",
        "men",
        4490,
        None,
        "Tops",
        ["Black", "Charcoal", "Navy"],
        "French terry 300 GSM",
        ["hoodie", "zip"],
        False,
        True,
        {"Zip": "YKK metal", "Pockets": "2 front"},
        "Loopback French terry with a metal zip.",
    ),
    (
        "CH-SWT-001",
        "Crewneck Sweatshirt",
        "men-hoodies",
        "men",
        3290,
        None,
        "Tops",
        ["Grey Marl", "Sand", "Forest", "Black"],
        "French terry 300 GSM",
        ["sweatshirt", "crewneck"],
        False,
        False,
        {"Fit": "Relaxed", "Hem": "Rib"},
        "The everyday crewneck in loopback terry.",
    ),
    (
        "CH-JOG-001",
        "Tapered Joggers",
        "men-joggers",
        "men",
        3490,
        3990,
        "Bottoms",
        ["Black", "Grey Marl", "Navy", "Olive"],
        "French terry 300 GSM",
        ["joggers", "track pants"],
        True,
        False,
        {"Fit": "Tapered", "Cuff": "Rib", "Pockets": "2 side, 1 back zip"},
        "Tapered loopback joggers with a zip back pocket.",
    ),
    (
        "CH-JOG-002",
        "Tech Track Pants",
        "men-joggers",
        "men",
        3990,
        None,
        "Bottoms",
        ["Black", "Charcoal"],
        "Poly-spandex tricot",
        ["track pants", "tech"],
        False,
        True,
        {"Fit": "Slim", "Hem": "Zip ankle"},
        "Four-way stretch track pants with zip ankles.",
    ),
    (
        "CH-SHO-001",
        "Woven Running Shorts",
        "men-shorts",
        "men",
        1990,
        None,
        "Bottoms",
        ["Black", "Navy", "Charcoal"],
        "Taslan nylon with mesh liner",
        ["shorts", "running"],
        False,
        False,
        {"Inseam": "7 inch", "Liner": "Mesh brief", "Pocket": "Zip back"},
        "Light, water-repellent shorts with a mesh liner.",
    ),
    (
        "CH-SHO-002",
        "Terry Sweat Shorts",
        "men-shorts",
        "men",
        2190,
        2690,
        "Bottoms",
        ["Grey Marl", "Black", "Sand"],
        "French terry 300 GSM",
        ["shorts", "lounge"],
        True,
        False,
        {"Inseam": "8 inch", "Pockets": "2 side"},
        "Loopback sweat shorts for lounging and lifting.",
    ),
    (
        "CH-JKT-001",
        "Lightweight Windbreaker",
        "men-jackets",
        "men",
        5490,
        6490,
        "Tops",
        ["Black", "Navy", "Rust"],
        "Taslan nylon, mesh lined",
        ["jacket", "windbreaker"],
        True,
        True,
        {"Hood": "Packable", "Water": "Repellent"},
        "Packable, water-repellent, mesh-lined.",
    ),
    (
        "CH-JKT-002",
        "Varsity Jacket",
        "men-jackets",
        "men",
        8990,
        None,
        "Tops",
        ["Black", "Maroon", "Navy"],
        "Heavy fleece body, PU sleeves",
        ["varsity", "jacket"],
        False,
        True,
        {"Closure": "Snap buttons", "Trim": "Striped rib"},
        "Classic varsity with chenille patches.",
    ),
    (
        "CH-TRK-001",
        "Full Tracksuit Set",
        "men-tracksuits",
        "men",
        6990,
        8490,
        "Tops",
        ["Black", "Navy", "Charcoal"],
        "Tricot micro peach",
        ["tracksuit", "set"],
        True,
        False,
        {"Jacket": "Full zip", "Pants": "Tapered"},
        "Jacket and pants, matched and ready.",
    ),
    (
        "CH-WTP-001",
        "Ribbed Crop Tee",
        "women-tops",
        "women",
        1590,
        None,
        "Women Tops",
        ["Black", "White", "Sand", "Maroon"],
        "Cotton-spandex rib",
        ["crop", "tee", "rib"],
        True,
        True,
        {"Fit": "Fitted", "Length": "Cropped"},
        "Stretchy ribbed crop tee that holds its shape.",
    ),
    (
        "CH-WTP-002",
        "Oversized Boyfriend Tee",
        "women-tops",
        "women",
        1990,
        None,
        "Women Tops",
        ["White", "Grey Marl", "Olive"],
        "200 GSM combed cotton",
        ["tee", "oversized"],
        False,
        False,
        {"Fit": "Oversized"},
        "Borrowed-from-him fit, made for her.",
    ),
    (
        "CH-LEG-001",
        "High-Waist Sculpt Leggings",
        "women-leggings",
        "women",
        2990,
        3490,
        "Women Tops",
        ["Black", "Navy", "Maroon", "Olive"],
        "Nylon-spandex, squat proof",
        ["leggings", "gym", "squat proof"],
        True,
        False,
        {"Rise": "High", "Pocket": "Side phone pocket", "Length": "Full"},
        "Buttery-soft, squat-proof, with a hidden waistband pocket.",
    ),
    (
        "CH-LEG-002",
        "7/8 Flow Leggings",
        "women-leggings",
        "women",
        2790,
        None,
        "Women Tops",
        ["Black", "Sand", "Forest"],
        "Poly-spandex brushed",
        ["leggings", "yoga"],
        False,
        True,
        {"Rise": "High", "Length": "7/8"},
        "Brushed, lightweight and perfect for yoga.",
    ),
    (
        "CH-WHD-001",
        "Cropped Hoodie",
        "women-hoodies",
        "women",
        3490,
        None,
        "Women Tops",
        ["Sand", "Black", "Maroon"],
        "320 GSM brushed fleece",
        ["hoodie", "cropped"],
        True,
        False,
        {"Fit": "Cropped", "Hood": "Double layer"},
        "Boxy cropped hoodie in brushed fleece.",
    ),
    (
        "CH-SET-001",
        "Terry Co-ord Set",
        "women-sets",
        "women",
        5490,
        6490,
        "Women Tops",
        ["Sand", "Black", "Olive"],
        "French terry 300 GSM",
        ["set", "co-ord", "lounge"],
        True,
        True,
        {"Includes": "Crewneck + shorts"},
        "Matching crewneck and shorts in loopback terry.",
    ),
    (
        "CH-BRA-001",
        "Seamless Sports Bra",
        "women-sports-bras",
        "women",
        1890,
        None,
        "Women Tops",
        ["Black", "Sand", "Maroon"],
        "Nylon-spandex seamless knit",
        ["sports bra", "gym"],
        False,
        False,
        {"Support": "Medium", "Pads": "Removable"},
        "Seamless medium-support bra with removable pads.",
    ),
    (
        "CH-TRN-001",
        "Dri-Fit Training Tee",
        "training-tees",
        "unisex",
        1790,
        None,
        "Tops",
        ["Black", "Navy", "Royal Blue", "Red"],
        "Polyester micro-mesh, 150 GSM",
        ["training", "dri-fit", "gym"],
        True,
        False,
        {"Fit": "Athletic", "Fabric": "Quick dry"},
        "Feather-light quick-dry tee for every session.",
    ),
    (
        "CH-CMP-001",
        "Compression Long Sleeve",
        "compression",
        "men",
        2290,
        None,
        "Tops",
        ["Black", "White", "Navy"],
        "Poly-spandex compression 220 GSM",
        ["compression", "base layer"],
        False,
        False,
        {"Compression": "Medium", "Seams": "Flatlock"},
        "Flatlock compression base layer.",
    ),
    (
        "CH-CMP-002",
        "Compression Tights",
        "compression",
        "men",
        2490,
        None,
        "Bottoms",
        ["Black", "Navy"],
        "Poly-spandex compression 220 GSM",
        ["compression", "tights"],
        False,
        False,
        {"Gusset": "Yes"},
        "Full-length compression tights.",
    ),
    (
        "CH-RUN-001",
        "Running Singlet",
        "running",
        "unisex",
        1490,
        None,
        "Tops",
        ["White", "Black", "Royal Blue"],
        "Micro-mesh polyester",
        ["running", "singlet"],
        False,
        True,
        {"Fit": "Racer"},
        "Barely-there racing singlet.",
    ),
    (
        "CH-GYM-001",
        "Mesh Gym Shorts",
        "gym-shorts",
        "men",
        1690,
        1990,
        "Bottoms",
        ["Black", "Grey Marl", "Navy"],
        "Polyester mesh",
        ["shorts", "gym", "mesh"],
        True,
        False,
        {"Inseam": "9 inch", "Pockets": "Side"},
        "Breathable 9-inch mesh shorts.",
    ),
    (
        "CH-KID-001",
        "Kids Graphic Tee",
        "kids-tees",
        "kids",
        1190,
        None,
        "Kids",
        ["White", "Royal Blue", "Red"],
        "180 GSM combed cotton",
        ["kids", "tee"],
        False,
        False,
        {"Print": "Screen print"},
        "Soft cotton tee with a playful print.",
    ),
    (
        "CH-KID-002",
        "Kids Tracksuit",
        "kids-tracksuits",
        "kids",
        3490,
        3990,
        "Kids",
        ["Navy", "Black", "Maroon"],
        "Tricot micro peach",
        ["kids", "tracksuit"],
        True,
        False,
        {"Includes": "Jacket + pants"},
        "Mini tracksuit, maximum energy.",
    ),
    (
        "CH-CAP-001",
        "Structured Cap",
        "caps",
        "unisex",
        1290,
        None,
        "One Size",
        ["Black", "Navy", "Sand", "Olive"],
        "Cotton twill",
        ["cap", "hat"],
        True,
        False,
        {"Panels": "6", "Closure": "Strap"},
        "Six-panel cap with 3D embroidered logo.",
    ),
    (
        "CH-BEA-001",
        "Ribbed Beanie",
        "caps",
        "unisex",
        990,
        None,
        "One Size",
        ["Black", "Grey Marl", "Maroon", "Forest"],
        "Acrylic rib knit",
        ["beanie", "winter"],
        False,
        True,
        {"Fit": "Cuffed"},
        "Cuffed rib beanie for cold mornings.",
    ),
    (
        "CH-SCK-001",
        "Crew Socks (3 pack)",
        "socks",
        "unisex",
        890,
        None,
        "One Size",
        ["White", "Black"],
        "Combed cotton blend",
        ["socks", "pack"],
        False,
        False,
        {"Pack": "3 pairs", "Cushion": "Terry footbed"},
        "Cushioned crew socks, pack of three.",
    ),
    (
        "CH-BAG-001",
        "Gym Duffel",
        "bags",
        "unisex",
        4490,
        None,
        "One Size",
        ["Black", "Navy"],
        "Water-resistant nylon",
        ["bag", "duffel", "gym"],
        True,
        False,
        {"Capacity": "35 L", "Compartments": "Shoe + wet"},
        "35-litre duffel with a separate shoe compartment.",
    ),
    (
        "CH-BAG-002",
        "Everyday Backpack",
        "bags",
        "unisex",
        3990,
        4490,
        "One Size",
        ["Black", "Charcoal", "Olive"],
        "Water-resistant nylon",
        ["bag", "backpack"],
        False,
        False,
        {"Capacity": "22 L", "Laptop": "15 inch sleeve"},
        "22-litre backpack with a padded laptop sleeve.",
    ),
    (
        "CH-BTL-001",
        "Insulated Bottle 750ml",
        "bottles",
        "unisex",
        1890,
        None,
        "One Size",
        ["Black", "White", "Olive"],
        "Double-wall stainless steel",
        ["bottle", "gym"],
        False,
        True,
        {"Capacity": "750 ml", "Cold": "24 h"},
        "Keeps water cold for 24 hours.",
    ),
]

COLLECTIONS = [
    ("new-arrivals", "New Arrivals", "Fresh off the line", True, lambda p: p.is_new),
    ("best-sellers", "Best Sellers", "What everyone's wearing", True, lambda p: p.is_featured),
    ("sale", "Sale", "Up to 25% off, while sizes last", True, lambda p: p.compare_at_price),
    (
        "winter-edit",
        "Winter Edit",
        "Fleece, layers and warm beanies",
        True,
        lambda p: any(t in p.tags for t in ("hoodie", "fleece", "winter", "jacket", "beanie", "sweatshirt", "varsity")),
    ),
    (
        "gym-essentials",
        "Gym Essentials",
        "Train harder in less",
        False,
        lambda p: any(t in p.tags for t in ("gym", "training", "compression", "running", "dri-fit", "sports bra")),
    ),
    ("under-2000", "Under Rs 2,000", "Big looks, small price", False, lambda p: p.price < 2000),
]

COUPONS = [
    ("WELCOME10", "10% off your first order", "percent", "10", None, "1500", True),
    ("CHOBBAR500", "Rs 500 off orders over Rs 4,000", "fixed", "500", None, "4000", False),
    ("FREESHIP", "Free delivery on any order", "free_shipping", "0", None, "0", False),
]

ZONES = [
    ("Lahore & Sialkot", [], ["Lahore", "Sialkot"], False, "150", "3000", "0", 1, 2),
    ("Punjab", ["Punjab", "Islamabad Capital Territory"], [], False, "200", "3000", "0", 2, 4),
    ("Karachi & Sindh", ["Sindh"], ["Karachi", "Hyderabad"], False, "250", "3500", "50", 3, 5),
    ("Rest of Pakistan", [], [], True, "300", "4000", "50", 4, 7),
]

SYNONYMS = [
    ("hoodie", "sweatshirt, pullover"),
    ("sweatshirt", "hoodie, crewneck"),
    ("joggers", "track pants, trousers, sweatpants"),
    ("track pants", "joggers"),
    ("tee", "t-shirt, shirt"),
    ("tshirt", "tee, t-shirt"),
    ("tights", "leggings"),
    ("leggings", "tights"),
    ("cap", "hat"),
    ("jacket", "windbreaker, varsity"),
    ("set", "co-ord, tracksuit"),
    ("bag", "backpack, duffel"),
]

PAGES = {
    "Shipping & Delivery": "## Delivery across Pakistan\n\nWe ship from Sialkot with TCS, Leopards and PostEx.\n\n| Zone | Charge | Time |\n|---|---|---|\n| Lahore & Sialkot | Rs 150 (free over Rs 3,000) | 1–2 days |\n| Rest of Punjab & Islamabad | Rs 200 (free over Rs 3,000) | 2–4 days |\n| Karachi & Sindh | Rs 250 (free over Rs 3,500) | 3–5 days |\n| Rest of Pakistan | Rs 300 (free over Rs 4,000) | 4–7 days |\n\nOrders placed before 2 pm ship the same day. You'll get a tracking link by email the moment your parcel leaves.",
    "Returns & Exchanges": "## 14-day easy returns\n\nNot the right size? Request an exchange or return from your order page within 14 days of delivery. Items must be unworn with tags attached.\n\n- **Exchanges** are free — we collect and redeliver.\n- **Refunds** go back by bank transfer, JazzCash/EasyPaisa or store credit within 5 business days of receiving the item.\n- Socks, bottles and sale items marked final are not returnable for hygiene reasons.",
    "Size Guide": "## Find your fit\n\nAll measurements are garment measurements in cm. Between sizes? Our tees and hoodies run relaxed — size down for a closer fit.\n\nEvery product page has a size chart tab with chest, length and waist for that exact style.",
    "About Chobbar": "## Made in Sialkot. Worn everywhere.\n\nChobbar started in a Sialkot factory that has stitched teamwear for clubs around the world since 2008. We took the same fabrics, the same stitching and put our own name on it — activewear and streetwear for the lads (and everyone else) at honest prices.\n\nNo middlemen, no markups. Just good clothes.",
    "Privacy Policy": "We collect what we need to deliver your order: name, phone, address and email. We never sell your data. Payment receipts you upload are visible only to our finance team. Email us at support@chobbar.shop to export or delete your data.",
    "Terms of Service": "Prices are in PKR and include GST where applicable. Cash-on-delivery orders are confirmed by phone or WhatsApp before dispatch; unconfirmed orders may be cancelled after 48 hours. Bank-transfer orders ship after payment is verified. See Returns & Exchanges for our return policy.",
}

FAQS = [
    (
        "Orders",
        "How do I track my order?",
        "Use the tracking link in your confirmation email or go to Track Order and enter your order number with the email or phone you used.",
    ),
    (
        "Orders",
        "Can I change or cancel my order?",
        "You can cancel from your order page while the status is Pending or Confirmed. After that, message us and we'll do our best.",
    ),
    (
        "Shipping",
        "How long does delivery take?",
        "1–2 days in Lahore and Sialkot, 2–4 days across Punjab, 3–7 days elsewhere in Pakistan.",
    ),
    (
        "Shipping",
        "Is delivery free?",
        "Yes, above Rs 3,000 in Punjab and Rs 3,500–4,000 elsewhere. The exact threshold shows at checkout.",
    ),
    (
        "Payments",
        "Which payment methods do you accept?",
        "Cash on delivery, bank transfer, JazzCash and EasyPaisa. Card payments are coming soon.",
    ),
    (
        "Payments",
        "Is there a COD fee?",
        "A small Rs 50 handling fee applies outside Punjab. It shows before you place the order.",
    ),
    (
        "Returns",
        "What is your return policy?",
        "14 days from delivery for unworn items with tags. Exchanges are free; refunds are processed within 5 business days of receipt.",
    ),
    (
        "Sizing",
        "How do your sizes run?",
        "Tees and hoodies run relaxed; activewear is true to size. Check the size chart on each product page.",
    ),
]


class Command(BaseCommand):
    help = "Seed the Chobbar catalog and storefront content."

    def add_arguments(self, parser):
        parser.add_argument("--demo", action="store_true")

    @transaction.atomic
    def handle(self, *args, **options):
        random.seed(42)
        self.stdout.write("Colours, sizes, categories…")
        colors = {}
        for i, (name, hx) in enumerate(COLORS):
            colors[name], _ = Color.objects.update_or_create(
                slug=slugify(name), defaults={"name": name, "hex": hx, "sort_order": i}
            )
        groups = {}
        for i, (gname, (labels, guide)) in enumerate(SIZE_GROUPS.items()):
            group, _ = SizeGroup.objects.update_or_create(
                slug=slugify(gname), defaults={"name": gname, "sort_order": i, "guide": guide}
            )
            groups[gname] = group
            for j, label in enumerate(labels):
                Size.objects.update_or_create(group=group, label=label, defaults={"sort_order": j})
        cats = {}
        for i, (slug, name, icon, children) in enumerate(CATEGORIES):
            parent, _ = Category.objects.update_or_create(slug=slug, defaults={"name": name, "icon": icon, "sort_order": i})
            cats[slug] = parent
            for j, (cslug, cname) in enumerate(children):
                cats[cslug], _ = Category.objects.update_or_create(
                    slug=cslug, defaults={"name": cname, "parent": parent, "sort_order": j}
                )
        Category.objects.update_or_create(
            slug="gift-cards", defaults={"name": "Gift Cards", "icon": "gift", "sort_order": 99}
        )  # intentionally empty → hidden

        self.stdout.write("Products & variants…")
        now = timezone.now()
        for idx, (sku, name, cat, gender, price, compare, grp, pcolors, material, tags, featured, new, specs, short) in enumerate(
            PRODUCTS
        ):
            product, _ = Product.objects.update_or_create(
                sku=sku,
                defaults={
                    "name": name,
                    "category": cats[cat],
                    "gender": gender,
                    "price": D(price),
                    "compare_at_price": D(compare) if compare else None,
                    "cost_price": D(price) * D("0.55"),
                    "size_group": groups[grp],
                    "material": material,
                    "tags": tags,
                    "is_featured": featured,
                    "is_new": new,
                    "specifications": specs,
                    "short_description": short,
                    "description": f"{short} Made in our own Sialkot facility from {material.lower()}. {('Machine wash cold, inside out. Do not tumble dry.')}",
                    "care_instructions": "Machine wash cold with similar colours. Do not bleach. Tumble dry low or hang dry. Iron inside out.",
                    "published_at": now - timedelta(days=(len(PRODUCTS) - idx) * 3),
                    "weight_grams": 650
                    if "tracksuit" in tags or "set" in tags
                    else 450
                    if "hoodie" in tags or "jacket" in tags
                    else 250,
                },
            )
            sizes = list(groups[grp].sizes.all())
            for cname in pcolors:
                color = colors[cname]
                for size in sizes:
                    vsku = f"{sku}-{slugify(cname).upper().replace('-', '')[:4]}-{size.label.replace('-', '')}"
                    # Deterministic pseudo-random stock with a few sold-out and low-stock cells.
                    stock = random.choice([0, 2, 4, 8, 12, 15, 20, 25, 30])
                    ProductVariant.objects.update_or_create(
                        product=product, color=color, size=size, defaults={"sku": vsku, "stock": stock, "is_active": True}
                    )

        self.stdout.write("Collections…")
        products = list(Product.objects.all())
        for i, (slug, name, tagline, featured, rule) in enumerate(COLLECTIONS):
            coll, _ = Collection.objects.update_or_create(
                slug=slug, defaults={"name": name, "tagline": tagline, "is_featured": featured, "sort_order": i}
            )
            coll.products.set([p for p in products if rule(p)])

        self.stdout.write("Promotions, shipping, content…")
        for code, desc, kind, value, max_disc, min_sub, first in COUPONS:
            Coupon.objects.update_or_create(
                code=code,
                defaults={
                    "description": desc,
                    "kind": kind,
                    "value": D(value),
                    "max_discount": D(max_disc) if max_disc else None,
                    "min_subtotal": D(min_sub),
                    "first_order_only": first,
                    "max_uses_per_user": 1 if first else 5,
                },
            )
        for i, (name, provs, cities, default, rate, free, cod, mn, mx) in enumerate(ZONES):
            ShippingZone.objects.update_or_create(
                name=name,
                defaults={
                    "provinces": provs,
                    "cities": cities,
                    "is_default": default,
                    "rate": D(rate),
                    "free_over": D(free),
                    "cod_fee": D(cod),
                    "min_days": mn,
                    "max_days": mx,
                    "sort_order": i,
                },
            )
        for term, exp in SYNONYMS:
            Synonym.objects.update_or_create(term=term, defaults={"expansions": exp})
        for title, body in PAGES.items():
            Page.objects.update_or_create(slug=slugify(title), defaults={"title": title, "body": body})
        for i, (cat, q, a) in enumerate(FAQS):
            FAQ.objects.update_or_create(question=q, defaults={"answer": a, "category": cat, "sort_order": i})
        Announcement.objects.update_or_create(
            text="Free delivery over Rs 3,000 · Cash on delivery available · 14-day easy returns",
            defaults={"url": "/pages/shipping-delivery", "sort_order": 0},
        )
        BankAccount.objects.update_or_create(
            label="Meezan Bank",
            defaults={
                "bank_name": "Meezan Bank Limited",
                "account_name": "Chobbar",
                "account_number": "0000-0101234567",
                "iban": "PK00MEZN0000000101234567",
                "instructions": "Send the receipt screenshot after transferring.",
                "sort_order": 0,
            },
        )
        BankAccount.objects.update_or_create(
            label="JazzCash",
            defaults={
                "bank_name": "JazzCash",
                "account_name": "Chobbar",
                "account_number": "0300 0000000",
                "instructions": "Use 'Send money' to this number and upload the receipt.",
                "sort_order": 1,
            },
        )

        self._translations()
        if options["demo"]:
            self._demo()
        self.stdout.write(
            self.style.SUCCESS(
                f"Done: {Product.objects.count()} products, {ProductVariant.objects.count()} variants, {Category.objects.count()} categories, {Collection.objects.count()} collections."
            )
        )

    def _translations(self):
        self.stdout.write("Urdu & Arabic translations…")

        def pair(ur, ar, field="name"):
            return {"ur": {field: ur}, "ar": {field: ar}}

        for slug, (ur, ar) in tr.CATEGORIES.items():
            Category.objects.filter(slug=slug).update(translations=pair(ur, ar))
        for slug, (ur, ar) in tr.COLORS.items():
            Color.objects.filter(slug=slug).update(translations=pair(ur, ar))
        for slug, ((ur_n, ur_t), (ar_n, ar_t)) in tr.COLLECTIONS.items():
            Collection.objects.filter(slug=slug).update(
                translations={"ur": {"name": ur_n, "tagline": ur_t}, "ar": {"name": ar_n, "tagline": ar_t}}
            )
        for sku, (ur, ar) in tr.PRODUCTS.items():
            Product.objects.filter(sku=sku).update(
                translations={
                    "ur": {"name": ur, "short_description": tr.SHORT["ur"]},
                    "ar": {"name": ar, "short_description": tr.SHORT["ar"]},
                }
            )
        Announcement.objects.filter(sort_order=0).update(
            translations={"ur": {"text": tr.ANNOUNCEMENT["ur"]}, "ar": {"text": tr.ANNOUNCEMENT["ar"]}}
        )
        for slug, (ur, ar) in tr.PAGES.items():
            Page.objects.filter(slug=slug).update(translations=pair(ur, ar, "title"))
        for faq in FAQ.objects.all():
            ur, ar = tr.FAQ_CATEGORY.get(faq.category, (faq.category, faq.category))
            faq.translations = {"ur": {"category": ur}, "ar": {"category": ar}}
            faq.save(update_fields=["translations"])

    def _demo(self):
        from apps.accounts.models import Address, User

        self.stdout.write("Demo accounts…")
        admin, _ = User.objects.get_or_create(
            email="admin@chobbar.shop",
            defaults={
                "first_name": "Chobbar",
                "last_name": "Admin",
                "is_staff": True,
                "is_superuser": True,
                "is_email_verified": True,
            },
        )
        if not admin.has_usable_password():
            admin.set_password("Admin!Chobbar2026")
            admin.save()
        customer, created = User.objects.get_or_create(
            email="ali@example.com",
            defaults={"first_name": "Ali", "last_name": "Raza", "phone": "03001234567", "is_email_verified": True},
        )
        if created:
            customer.set_password("Customer!2026")
            customer.save()
            Address.objects.create(
                user=customer,
                full_name="Ali Raza",
                phone="03001234567",
                line1="House 12, Street 4, DHA Phase 5",
                city="Lahore",
                province="Punjab",
                postal_code="54000",
                is_default=True,
            )
