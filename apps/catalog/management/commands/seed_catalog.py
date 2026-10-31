"""
Seed a realistic Leepa Sports wholesale catalog.

    python manage.py seed_catalog            # idempotent – safe to re-run
    python manage.py seed_catalog --demo     # also creates demo company/users/bank account

Fabric prices are indicative Faisalabad / Karachi mill rates (PKR per kg) for
knitted sportswear fabrics; update them from the admin as the market moves —
every product price follows automatically.
"""

from decimal import Decimal

from django.core.management.base import BaseCommand
from django.db import transaction
from django.utils import timezone
from django.utils.text import slugify

from apps.catalog.models import Category, Fabric, Product, ProductFabricOption, ProductSizeOption, Size, SizeGroup
from apps.orders.models import ShippingMethod
from apps.pricing.models import CustomerGroup, ExchangeRate, VolumeTier
from apps.search.models import Synonym

D = Decimal

# name, composition, gsm, quality, rank, PKR/kg, features, best_for, mills, swatch
FABRICS = [
    (
        "Polyester Interlock",
        "100% Polyester",
        180,
        "economy",
        1,
        920,
        ["Sublimation ready", "Colourfast", "Durable"],
        ["Soccer jerseys", "Training tops"],
        "Faisalabad",
        "#94a3b8",
    ),
    (
        "Micro Mesh",
        "100% Polyester",
        150,
        "standard",
        2,
        1050,
        ["Breathable", "Lightweight", "Quick dry"],
        ["Basketball", "Running singlets"],
        "Faisalabad",
        "#60a5fa",
    ),
    (
        "Bird-Eye Mesh",
        "100% Polyester",
        160,
        "standard",
        2,
        1120,
        ["Moisture wicking", "Airflow", "Sublimation ready"],
        ["Soccer", "Volleyball"],
        "Faisalabad / Karachi",
        "#38bdf8",
    ),
    (
        "Dri-Fit Pique",
        "100% Polyester",
        170,
        "standard",
        2,
        1180,
        ["Moisture wicking", "Anti-pilling", "Soft hand"],
        ["Polos", "Cricket shirts"],
        "Faisalabad",
        "#34d399",
    ),
    (
        "Dot-Knit Performance",
        "100% Polyester",
        155,
        "premium",
        3,
        1350,
        ["4-way stretch", "Quick dry", "Lightweight"],
        ["Pro match kits", "Rugby"],
        "Karachi",
        "#a78bfa",
    ),
    (
        "Poly-Spandex Compression",
        "88% Polyester 12% Spandex",
        220,
        "premium",
        3,
        1950,
        ["4-way stretch", "Compression", "Shape retention"],
        ["Base layers", "Leggings"],
        "Lahore / Karachi",
        "#f472b6",
    ),
    (
        "Nylon-Spandex Supplex",
        "80% Nylon 20% Spandex",
        240,
        "elite",
        4,
        2850,
        ["Buttery soft", "Squat proof", "UV protection"],
        ["Premium leggings", "Sports bras"],
        "Karachi",
        "#fb7185",
    ),
    (
        "French Terry",
        "60% Cotton 40% Polyester",
        280,
        "standard",
        2,
        1380,
        ["Soft loopback", "Warm", "Pre-shrunk"],
        ["Hoodies", "Joggers"],
        "Faisalabad",
        "#fbbf24",
    ),
    (
        "Brushed Fleece",
        "65% Polyester 35% Cotton",
        320,
        "standard",
        2,
        1290,
        ["Brushed inside", "Warm", "Durable"],
        ["Hoodies", "Tracksuits"],
        "Faisalabad",
        "#f59e0b",
    ),
    (
        "Cotton Fleece Heavyweight",
        "80% Cotton 20% Polyester",
        380,
        "premium",
        3,
        1750,
        ["Heavyweight", "Premium hand feel", "Pre-shrunk"],
        ["Premium hoodies", "Varsity"],
        "Faisalabad",
        "#f97316",
    ),
    (
        "Combed Cotton Jersey",
        "100% Combed Cotton",
        180,
        "standard",
        2,
        1520,
        ["Breathable", "Soft", "Print friendly"],
        ["T-shirts", "Fan wear"],
        "Faisalabad",
        "#e2e8f0",
    ),
    (
        "Tricot Micro Peach",
        "100% Polyester",
        230,
        "standard",
        2,
        1150,
        ["Peach finish", "Wind resistant", "Durable"],
        ["Tracksuits", "Warm-ups"],
        "Faisalabad",
        "#64748b",
    ),
    (
        "Taslan Woven",
        "100% Nylon Taslan",
        140,
        "premium",
        3,
        1680,
        ["Water repellent", "Crisp", "Lightweight"],
        ["Shorts", "Windbreakers"],
        "Karachi",
        "#0ea5e9",
    ),
    (
        "Sublimation Polyester Lycra",
        "92% Polyester 8% Spandex",
        200,
        "premium",
        3,
        1620,
        ["Full-colour sublimation", "Stretch", "Vivid prints"],
        ["Cycling", "MMA shorts", "Custom kits"],
        "Faisalabad / Lahore",
        "#8b5cf6",
    ),
    (
        "Honeycomb Mesh",
        "100% Polyester",
        190,
        "economy",
        1,
        980,
        ["Textured", "Breathable", "Budget friendly"],
        ["Practice jerseys", "Pinnies"],
        "Faisalabad",
        "#a3e635",
    ),
]

SIZE_GROUPS = {
    "Adult": ["XS", "S", "M", "L", "XL", "2XL", "3XL", "4XL", "5XL"],
    "Youth": ["YXS", "YS", "YM", "YL", "YXL"],
    "Numeric": ["28", "30", "32", "34", "36", "38", "40", "42", "44"],
    "One Size": ["OS"],
}
SURCHARGE = {"2XL": D("6"), "3XL": D("10"), "4XL": D("14"), "5XL": D("18")}
ADULT_CHEST = {
    "XS": "86-91",
    "S": "91-96",
    "M": "96-101",
    "L": "101-106",
    "XL": "106-111",
    "2XL": "111-116",
    "3XL": "116-121",
    "4XL": "121-126",
    "5XL": "126-131",
}

# slug, name, icon, children: [(slug, name)]
CATEGORIES = [
    (
        "teamwear",
        "Teamwear",
        "shirt",
        [
            ("soccer-kits", "Soccer / Football"),
            ("basketball-uniforms", "Basketball"),
            ("cricket-kits", "Cricket"),
            ("rugby-kits", "Rugby"),
            ("volleyball-uniforms", "Volleyball"),
            ("hockey-kits", "Field Hockey"),
            ("baseball-softball", "Baseball & Softball"),
        ],
    ),
    (
        "training-performance",
        "Training & Performance",
        "dumbbell",
        [
            ("training-tops", "Training Tops"),
            ("compression-base-layers", "Compression & Base Layers"),
            ("shorts", "Shorts"),
            ("leggings-tights", "Leggings & Tights"),
            ("singlets-tanks", "Singlets & Tanks"),
        ],
    ),
    (
        "tracksuits-outerwear",
        "Tracksuits & Outerwear",
        "wind",
        [
            ("tracksuits", "Tracksuits"),
            ("hoodies-sweatshirts", "Hoodies & Sweatshirts"),
            ("jackets-windbreakers", "Jackets & Windbreakers"),
            ("joggers", "Joggers"),
        ],
    ),
    (
        "combat-sports",
        "Combat Sports",
        "swords",
        [
            ("mma-shorts", "MMA & Grappling Shorts"),
            ("rash-guards", "Rash Guards"),
            ("boxing-apparel", "Boxing Apparel"),
        ],
    ),
    (
        "casual-fanwear",
        "Casual & Fan Wear",
        "star",
        [
            ("polo-shirts", "Polo Shirts"),
            ("t-shirts", "T-Shirts"),
            ("varsity-jackets", "Varsity Jackets"),
        ],
    ),
    (
        "accessories",
        "Accessories",
        "package",
        [
            ("socks", "Socks"),
            ("bags", "Bags"),
            ("caps-beanies", "Caps & Beanies"),
            ("goalkeeper-gloves", "Goalkeeper Gloves"),
        ],
    ),
]

# sku, name, category slug, base fabric, consumption kg, labor USD, size group, genders, moq, lead, featured, tags, colors, fabric options, specs, short desc
PRODUCTS = [
    (
        "LS-SOC-001",
        "Pro Match Soccer Jersey",
        "soccer-kits",
        "Bird-Eye Mesh",
        "0.260",
        "4.60",
        "Adult",
        ["men", "women", "youth"],
        10,
        21,
        True,
        ["jersey", "soccer", "football", "sublimation"],
        ["Royal Blue", "Red", "White", "Black", "Forest Green", "Custom"],
        ["Polyester Interlock", "Micro Mesh", "Bird-Eye Mesh", "Dot-Knit Performance", "Sublimation Polyester Lycra"],
        {"Fit": "Athletic", "Collar": "V-neck rib", "Sleeve": "Raglan", "Decoration": "Sublimation / heat transfer"},
        "Fully sublimated match jersey with raglan sleeves and side mesh panels.",
    ),
    (
        "LS-SOC-002",
        "Match Soccer Shorts",
        "soccer-kits",
        "Polyester Interlock",
        "0.180",
        "3.10",
        "Adult",
        ["men", "women", "youth"],
        10,
        21,
        True,
        ["shorts", "soccer", "football"],
        ["Royal Blue", "Red", "White", "Black", "Navy"],
        ["Polyester Interlock", "Micro Mesh", "Sublimation Polyester Lycra"],
        {"Waist": "Elastic with drawcord", "Inseam": "15 cm adult", "Lining": "Optional brief"},
        "Lightweight match shorts with internal drawcord and sublimated side panels.",
    ),
    (
        "LS-SOC-003",
        "Goalkeeper Long Sleeve Jersey",
        "soccer-kits",
        "Dot-Knit Performance",
        "0.340",
        "6.20",
        "Adult",
        ["men", "women", "youth"],
        10,
        24,
        False,
        ["goalkeeper", "soccer", "long sleeve"],
        ["Neon Yellow", "Orange", "Purple", "Black"],
        ["Polyester Interlock", "Dot-Knit Performance", "Sublimation Polyester Lycra"],
        {"Padding": "Elbow foam optional", "Fit": "Relaxed", "Thumb loops": "Yes"},
        "Padded long-sleeve keeper jersey in high-visibility colourways.",
    ),
    (
        "LS-BBL-001",
        "Reversible Basketball Jersey",
        "basketball-uniforms",
        "Micro Mesh",
        "0.300",
        "5.40",
        "Adult",
        ["men", "women", "youth"],
        10,
        21,
        True,
        ["basketball", "reversible", "jersey"],
        ["Black/White", "Navy/Gold", "Red/White", "Custom"],
        ["Micro Mesh", "Honeycomb Mesh", "Sublimation Polyester Lycra"],
        {"Construction": "Double layer reversible", "Neck": "Classic V", "Decoration": "Sublimation both sides"},
        "Two kits in one — fully sublimated, reversible, tournament ready.",
    ),
    (
        "LS-BBL-002",
        'Basketball Shorts 9"',
        "basketball-uniforms",
        "Micro Mesh",
        "0.280",
        "3.80",
        "Adult",
        ["men", "women", "youth"],
        10,
        21,
        False,
        ["basketball", "shorts"],
        ["Black", "Navy", "Red", "White", "Custom"],
        ["Micro Mesh", "Honeycomb Mesh", "Sublimation Polyester Lycra"],
        {"Inseam": "9 inch", "Pockets": "Optional side pockets", "Waist": "Elastic + drawcord"},
        "Classic 9-inch game shorts with sublimated panels and pockets on request.",
    ),
    (
        "LS-CRK-001",
        "Coloured Cricket Shirt",
        "cricket-kits",
        "Dri-Fit Pique",
        "0.320",
        "5.60",
        "Adult",
        ["men", "women", "youth"],
        12,
        21,
        True,
        ["cricket", "shirt", "polo"],
        ["Green", "Blue", "Yellow", "Maroon", "Custom"],
        ["Dri-Fit Pique", "Polyester Interlock", "Dot-Knit Performance"],
        {"Collar": "Self fabric polo", "Placket": "3 button", "Decoration": "Sublimation + embroidery"},
        "Moisture-wicking pique cricket shirt with sublimated panels and embroidered crest.",
    ),
    (
        "LS-CRK-002",
        "Cricket Trousers",
        "cricket-kits",
        "Tricot Micro Peach",
        "0.420",
        "6.40",
        "Numeric",
        ["men", "women"],
        12,
        24,
        False,
        ["cricket", "trousers", "pants"],
        ["White", "Cream", "Navy", "Green"],
        ["Tricot Micro Peach", "Polyester Interlock"],
        {"Fit": "Straight", "Pockets": "2 side, 1 back", "Waist": "Elastic back, belt loops"},
        "Durable coloured or white cricket trousers with reinforced knees.",
    ),
    (
        "LS-RUG-001",
        "Pro Rugby Jersey",
        "rugby-kits",
        "Dot-Knit Performance",
        "0.380",
        "7.80",
        "Adult",
        ["men", "women"],
        10,
        24,
        False,
        ["rugby", "jersey", "tight fit"],
        ["Black", "Green/Gold", "Red/White", "Custom"],
        ["Dot-Knit Performance", "Poly-Spandex Compression", "Sublimation Polyester Lycra"],
        {"Fit": "Body-fit", "Seams": "Reinforced flatlock", "Collar": "Rib crew with gripper"},
        "Reinforced body-fit rugby jersey with grip panels and sublimated graphics.",
    ),
    (
        "LS-VLB-001",
        "Volleyball Jersey",
        "volleyball-uniforms",
        "Bird-Eye Mesh",
        "0.240",
        "4.40",
        "Adult",
        ["women", "men", "youth"],
        10,
        21,
        False,
        ["volleyball", "jersey"],
        ["Purple", "Teal", "Black", "White", "Custom"],
        ["Bird-Eye Mesh", "Micro Mesh", "Sublimation Polyester Lycra"],
        {"Fit": "Women's athletic", "Sleeve": "Cap / sleeveless"},
        "Sublimated volleyball jersey available in cap-sleeve or sleeveless cuts.",
    ),
    (
        "LS-HOC-001",
        "Field Hockey Shirt",
        "hockey-kits",
        "Bird-Eye Mesh",
        "0.260",
        "4.70",
        "Adult",
        ["men", "women", "youth"],
        10,
        21,
        False,
        ["hockey", "shirt"],
        ["Orange", "Blue", "Green", "Custom"],
        ["Bird-Eye Mesh", "Polyester Interlock"],
        {"Fit": "Regular", "Collar": "Crew"},
        "Breathable sublimated field hockey shirt.",
    ),
    (
        "LS-BSB-001",
        "Full-Button Baseball Jersey",
        "baseball-softball",
        "Polyester Interlock",
        "0.340",
        "6.90",
        "Adult",
        ["men", "women", "youth"],
        12,
        24,
        False,
        ["baseball", "softball", "jersey", "button"],
        ["Pinstripe White", "Navy", "Red", "Custom"],
        ["Polyester Interlock", "Dot-Knit Performance", "Sublimation Polyester Lycra"],
        {"Front": "Full button", "Decoration": "Sublimation / tackle twill"},
        "Classic full-button jersey with sublimated pinstripes and tackle-twill lettering.",
    ),
    (
        "LS-TRN-001",
        "Training Tee",
        "training-tops",
        "Micro Mesh",
        "0.230",
        "3.60",
        "Adult",
        ["men", "women", "youth", "unisex"],
        20,
        18,
        True,
        ["training", "tee", "t-shirt"],
        ["Black", "Grey", "Navy", "Red", "Royal", "Custom"],
        ["Micro Mesh", "Polyester Interlock", "Dri-Fit Pique", "Dot-Knit Performance"],
        {"Fit": "Regular", "Neck": "Crew", "Decoration": "Screen print / heat transfer"},
        "Everyday training tee — lightweight, quick dry, club crest ready.",
    ),
    (
        "LS-TRN-002",
        "Quarter-Zip Training Top",
        "training-tops",
        "Tricot Micro Peach",
        "0.420",
        "7.20",
        "Adult",
        ["men", "women", "youth"],
        12,
        24,
        False,
        ["quarter zip", "training", "midlayer"],
        ["Black", "Navy", "Grey", "Custom"],
        ["Tricot Micro Peach", "Poly-Spandex Compression", "Brushed Fleece"],
        {"Zip": "YKK quarter zip", "Thumb holes": "Optional", "Pockets": "Zip chest pocket optional"},
        "Brushed quarter-zip midlayer for warm-ups and travel.",
    ),
    (
        "LS-CMP-001",
        "Compression Long Sleeve",
        "compression-base-layers",
        "Poly-Spandex Compression",
        "0.300",
        "5.80",
        "Adult",
        ["men", "women", "youth"],
        15,
        21,
        True,
        ["compression", "base layer", "long sleeve"],
        ["Black", "White", "Navy", "Red"],
        ["Poly-Spandex Compression", "Nylon-Spandex Supplex", "Sublimation Polyester Lycra"],
        {"Compression": "Medium", "Seams": "Flatlock", "UV": "UPF 40+"},
        "Flatlock-seamed compression base layer with medium support.",
    ),
    (
        "LS-CMP-002",
        "Compression Tights",
        "compression-base-layers",
        "Poly-Spandex Compression",
        "0.340",
        "6.10",
        "Adult",
        ["men", "women", "youth"],
        15,
        21,
        False,
        ["compression", "tights", "base layer"],
        ["Black", "Navy"],
        ["Poly-Spandex Compression", "Nylon-Spandex Supplex"],
        {"Waist": "Wide elastic", "Gusset": "Yes"},
        "Full-length compression tights with gusset and flatlock seams.",
    ),
    (
        "LS-SHO-001",
        "Woven Training Shorts",
        "shorts",
        "Taslan Woven",
        "0.170",
        "3.90",
        "Adult",
        ["men", "women", "unisex"],
        20,
        21,
        False,
        ["shorts", "woven", "running"],
        ["Black", "Navy", "Charcoal", "Custom"],
        ["Taslan Woven", "Polyester Interlock"],
        {"Liner": "Mesh brief", "Pockets": "Zip back pocket", "Inseam": "7 inch"},
        "Water-repellent woven shorts with mesh liner and zip pocket.",
    ),
    (
        "LS-LEG-001",
        "High-Waist Leggings",
        "leggings-tights",
        "Nylon-Spandex Supplex",
        "0.360",
        "7.40",
        "Adult",
        ["women"],
        15,
        21,
        True,
        ["leggings", "women", "gym", "squat proof"],
        ["Black", "Olive", "Burgundy", "Dusty Rose", "Custom"],
        ["Nylon-Spandex Supplex", "Poly-Spandex Compression", "Sublimation Polyester Lycra"],
        {"Rise": "High", "Pocket": "Side phone pocket", "Length": "Full / 7/8"},
        "Buttery-soft squat-proof leggings with hidden waistband pocket.",
    ),
    (
        "LS-SNG-001",
        "Running Singlet",
        "singlets-tanks",
        "Micro Mesh",
        "0.160",
        "3.20",
        "Adult",
        ["men", "women", "unisex"],
        20,
        18,
        False,
        ["singlet", "tank", "running", "athletics"],
        ["White", "Black", "Neon", "Custom"],
        ["Micro Mesh", "Bird-Eye Mesh", "Sublimation Polyester Lycra"],
        {"Fit": "Racer", "Decoration": "Sublimation"},
        "Feather-light racing singlet, fully sublimated.",
    ),
    (
        "LS-TRK-001",
        "Club Tracksuit (Jacket + Pants)",
        "tracksuits",
        "Tricot Micro Peach",
        "0.900",
        "14.50",
        "Adult",
        ["men", "women", "youth"],
        10,
        28,
        True,
        ["tracksuit", "jacket", "pants", "travel"],
        ["Navy/White", "Black/Red", "Royal/Gold", "Custom"],
        ["Tricot Micro Peach", "Brushed Fleece", "Polyester Interlock"],
        {
            "Jacket": "Full zip, stand collar",
            "Pants": "Tapered, zip hem",
            "Pockets": "Zip pockets",
            "Decoration": "Embroidery + heat transfer",
        },
        "Two-piece club tracksuit with contrast piping and embroidered crest.",
    ),
    (
        "LS-HOD-001",
        "Pullover Hoodie",
        "hoodies-sweatshirts",
        "Brushed Fleece",
        "0.620",
        "8.90",
        "Adult",
        ["men", "women", "youth", "unisex"],
        15,
        24,
        True,
        ["hoodie", "fleece", "pullover"],
        ["Black", "Grey Marl", "Navy", "Maroon", "Custom"],
        ["Brushed Fleece", "French Terry", "Cotton Fleece Heavyweight"],
        {
            "Hood": "Double layer",
            "Pocket": "Kangaroo",
            "Cuffs": "Rib 1x1",
            "Decoration": "Screen print / embroidery / puff print",
        },
        "Heavyweight brushed fleece hoodie — the fan-store staple.",
    ),
    (
        "LS-HOD-002",
        "Full-Zip Hoodie",
        "hoodies-sweatshirts",
        "French Terry",
        "0.650",
        "10.40",
        "Adult",
        ["men", "women", "unisex"],
        15,
        24,
        False,
        ["hoodie", "zip", "french terry"],
        ["Black", "Grey Marl", "Navy", "Custom"],
        ["French Terry", "Brushed Fleece", "Cotton Fleece Heavyweight"],
        {"Zip": "YKK metal", "Pockets": "2 front"},
        "Loopback French terry zip hoodie with metal zipper.",
    ),
    (
        "LS-JKT-001",
        "Lightweight Windbreaker",
        "jackets-windbreakers",
        "Taslan Woven",
        "0.380",
        "9.80",
        "Adult",
        ["men", "women", "unisex"],
        12,
        28,
        False,
        ["windbreaker", "jacket", "rain"],
        ["Black", "Navy", "Neon Yellow", "Custom"],
        ["Taslan Woven"],
        {"Lining": "Mesh", "Hood": "Packable", "Water": "Repellent"},
        "Packable water-repellent windbreaker with mesh lining.",
    ),
    (
        "LS-JOG-001",
        "Tapered Joggers",
        "joggers",
        "French Terry",
        "0.520",
        "7.60",
        "Adult",
        ["men", "women", "unisex"],
        15,
        24,
        False,
        ["joggers", "pants", "french terry"],
        ["Black", "Grey Marl", "Navy", "Custom"],
        ["French Terry", "Brushed Fleece", "Cotton Fleece Heavyweight"],
        {"Fit": "Tapered", "Cuff": "Rib", "Pockets": "2 side, 1 back zip"},
        "Tapered loopback joggers with ribbed cuffs and zip back pocket.",
    ),
    (
        "LS-MMA-001",
        "MMA Fight Shorts",
        "mma-shorts",
        "Sublimation Polyester Lycra",
        "0.260",
        "6.80",
        "Numeric",
        ["men", "women"],
        10,
        21,
        True,
        ["mma", "shorts", "grappling", "bjj"],
        ["Custom"],
        ["Sublimation Polyester Lycra", "Taslan Woven"],
        {"Closure": "Velcro + drawstring", "Split": "Side slits with stretch panel", "Decoration": "Full sublimation"},
        "Fully sublimated fight shorts with stretch crotch panel and velcro closure.",
    ),
    (
        "LS-RSG-001",
        "Long Sleeve Rash Guard",
        "rash-guards",
        "Sublimation Polyester Lycra",
        "0.300",
        "6.20",
        "Adult",
        ["men", "women", "youth"],
        10,
        21,
        False,
        ["rash guard", "bjj", "mma", "surf"],
        ["Custom"],
        ["Sublimation Polyester Lycra", "Poly-Spandex Compression", "Nylon-Spandex Supplex"],
        {"Hem": "Silicone gripper", "Seams": "Flatlock", "Decoration": "Full sublimation"},
        "Flatlock rash guard with silicone hem grip, ranked colours available.",
    ),
    (
        "LS-BOX-001",
        "Boxing Shorts",
        "boxing-apparel",
        "Polyester Interlock",
        "0.250",
        "6.40",
        "Adult",
        ["men", "women", "youth"],
        10,
        21,
        False,
        ["boxing", "shorts", "satin"],
        ["Red", "Blue", "Black", "Gold", "Custom"],
        ["Polyester Interlock", "Sublimation Polyester Lycra"],
        {"Waist": "Wide elastic", "Side slits": "Yes", "Decoration": "Sublimation / embroidery"},
        "Classic wide-waistband boxing shorts with sublimated or embroidered details.",
    ),
    (
        "LS-POL-001",
        "Club Polo Shirt",
        "polo-shirts",
        "Dri-Fit Pique",
        "0.300",
        "5.20",
        "Adult",
        ["men", "women", "unisex"],
        15,
        21,
        True,
        ["polo", "staff", "coach", "club"],
        ["Black", "Navy", "White", "Red", "Bottle Green", "Custom"],
        ["Dri-Fit Pique", "Combed Cotton Jersey"],
        {"Collar": "Rib knit", "Placket": "3 button", "Decoration": "Embroidery"},
        "Moisture-wicking pique polo for coaches, staff and supporters.",
    ),
    (
        "LS-TEE-001",
        "Cotton Fan Tee",
        "t-shirts",
        "Combed Cotton Jersey",
        "0.220",
        "3.30",
        "Adult",
        ["men", "women", "youth", "unisex"],
        25,
        18,
        False,
        ["t-shirt", "cotton", "fan", "merch"],
        ["White", "Black", "Grey Marl", "Navy", "Custom"],
        ["Combed Cotton Jersey", "Polyester Interlock"],
        {"Neck": "Rib crew", "Fit": "Regular", "Decoration": "Screen print / DTF"},
        "Soft combed-cotton tee for merch tables and fan stores.",
    ),
    (
        "LS-VAR-001",
        "Varsity Jacket",
        "varsity-jackets",
        "Cotton Fleece Heavyweight",
        "0.850",
        "22.00",
        "Adult",
        ["men", "women", "unisex"],
        10,
        35,
        False,
        ["varsity", "letterman", "jacket"],
        ["Black/White", "Navy/Grey", "Maroon/Cream", "Custom"],
        ["Cotton Fleece Heavyweight", "Brushed Fleece"],
        {"Sleeves": "PU leather or fleece", "Trim": "Striped rib", "Closure": "Snap buttons", "Decoration": "Chenille patches"},
        "Heavyweight varsity jacket with chenille patches and striped rib trim.",
    ),
    (
        "LS-SCK-001",
        "Team Crew Socks",
        "socks",
        "Combed Cotton Jersey",
        "0.080",
        "1.40",
        "One Size",
        ["unisex", "youth"],
        50,
        18,
        False,
        ["socks", "crew", "team"],
        ["White", "Black", "Custom"],
        ["Combed Cotton Jersey"],
        {"Cushion": "Terry footbed", "Decoration": "Knitted-in logo"},
        "Cushioned crew socks with knitted-in team logo and stripes.",
    ),
    (
        "LS-BAG-001",
        "Team Backpack",
        "bags",
        "Taslan Woven",
        "0.550",
        "11.50",
        "One Size",
        ["unisex"],
        20,
        28,
        False,
        ["bag", "backpack", "kit bag"],
        ["Black", "Navy", "Custom"],
        ["Taslan Woven"],
        {"Capacity": "30 L", "Compartments": "Shoe + laptop", "Decoration": "Embroidery"},
        "30-litre team backpack with ventilated shoe compartment.",
    ),
    (
        "LS-CAP-001",
        "Team Cap",
        "caps-beanies",
        "Combed Cotton Jersey",
        "0.090",
        "2.60",
        "One Size",
        ["unisex"],
        50,
        21,
        False,
        ["cap", "hat", "snapback"],
        ["Black", "Navy", "White", "Custom"],
        ["Combed Cotton Jersey", "Polyester Interlock"],
        {"Panels": "6", "Closure": "Snapback / strap", "Decoration": "3D embroidery"},
        "Six-panel structured cap with 3D embroidered crest.",
    ),
    (
        "LS-GLV-001",
        "Goalkeeper Gloves",
        "goalkeeper-gloves",
        "Taslan Woven",
        "0.120",
        "8.90",
        "Numeric",
        ["unisex", "youth"],
        20,
        28,
        False,
        ["gloves", "goalkeeper", "latex"],
        ["Neon", "Black", "Custom"],
        ["Taslan Woven"],
        {"Palm": "4 mm German latex", "Cut": "Negative / roll finger", "Closure": "Elastic wrist strap"},
        "Negative-cut goalkeeper gloves with 4 mm latex palm.",
    ),
]

VOLUME_TIERS = [(50, "5"), (100, "10"), (250, "15"), (500, "20"), (1000, "25")]
CUSTOMER_GROUPS = [
    ("Club", "club", "0", True),
    ("Team Store / Retailer", "retailer", "5", False),
    ("Distributor", "distributor", "12", False),
    ("Key Account", "key-account", "18", False),
]
SYNONYMS = [
    ("jersey", "shirt, top, kit"),
    ("kit", "uniform, jersey, set"),
    ("uniform", "kit, jersey"),
    ("pants", "trousers, joggers, bottoms"),
    ("trousers", "pants"),
    ["sweatshirt", "hoodie, fleece"],
    ("hoodie", "sweatshirt, fleece"),
    ("football", "soccer"),
    ("soccer", "football"),
    ("tee", "t-shirt, shirt"),
    ("tights", "leggings, compression"),
    ("leggings", "tights"),
    ("windbreaker", "jacket, rain jacket"),
    ("tracksuit", "warm-up, track suit"),
    ("bjj", "rash guard, grappling, mma"),
    ("gk", "goalkeeper"),
]
SHIPPING = [
    ("Sea freight (consolidated)", "sea", "Most economical for 500+ pieces. 30–45 days port to port.", "120", "0.90", 30, 45, 1),
    ("Air cargo", "air", "Airport to airport, 7–12 days.", "60", "4.20", 7, 12, 2),
    (
        "Express courier (DHL / FedEx)",
        "express",
        "Door to door, 4–7 days. Best for samples and small runs.",
        "35",
        "7.80",
        4,
        7,
        3,
    ),
]


class Command(BaseCommand):
    help = "Seed categories, fabrics, sizes, products, pricing tiers and shipping methods."

    def add_arguments(self, parser):
        parser.add_argument("--demo", action="store_true", help="Also create demo company, users and bank account")

    @transaction.atomic
    def handle(self, *args, **options):
        self.stdout.write("Seeding exchange rates, customer groups, volume tiers…")
        ExchangeRate.objects.update_or_create(currency="USD", defaults={"pkr_per_unit": D("280.00"), "source": "seed"})
        ExchangeRate.objects.update_or_create(currency="EUR", defaults={"pkr_per_unit": D("305.00"), "source": "seed"})
        ExchangeRate.objects.update_or_create(currency="GBP", defaults={"pkr_per_unit": D("355.00"), "source": "seed"})
        ExchangeRate.objects.update_or_create(currency="PKR", defaults={"pkr_per_unit": D("1"), "source": "seed"})
        for name, slug, pct, default in CUSTOMER_GROUPS:
            CustomerGroup.objects.update_or_create(
                slug=slug, defaults={"name": name, "discount_percent": D(pct), "is_default": default}
            )
        for qty, pct in VOLUME_TIERS:
            VolumeTier.objects.update_or_create(product=None, min_quantity=qty, defaults={"discount_percent": D(pct)})
        for term, exp in SYNONYMS:
            Synonym.objects.update_or_create(term=term, defaults={"expansions": exp})
        for name, code, desc, base, per_kg, mn, mx, order in SHIPPING:
            ShippingMethod.objects.update_or_create(
                code=code,
                defaults={
                    "name": name,
                    "description": desc,
                    "base_price": D(base),
                    "price_per_kg": D(per_kg),
                    "min_days": mn,
                    "max_days": mx,
                    "sort_order": order,
                },
            )

        self.stdout.write("Seeding fabrics…")
        fabrics = {}
        for name, comp, gsm, quality, rank, price, features, best_for, mills, swatch in FABRICS:
            fabric, _ = Fabric.objects.update_or_create(
                slug=slugify(name),
                defaults={
                    "name": name,
                    "composition": comp,
                    "gsm": gsm,
                    "quality": quality,
                    "quality_rank": rank,
                    "price_pkr": D(price),
                    "features": features,
                    "best_for": best_for,
                    "typical_mills": mills,
                    "swatch_color": swatch,
                    "price_updated_at": timezone.localdate(),
                    "description": f"{comp} knit at {gsm} GSM sourced from {mills} mills. Indicative mill rate PKR {price}/kg.",
                },
            )
            fabrics[name] = fabric

        self.stdout.write("Seeding sizes…")
        groups = {}
        for i, (gname, labels) in enumerate(SIZE_GROUPS.items()):
            group, _ = SizeGroup.objects.update_or_create(slug=slugify(gname), defaults={"name": gname, "sort_order": i})
            groups[gname] = group
            for j, label in enumerate(labels):
                Size.objects.update_or_create(
                    group=group,
                    label=label,
                    defaults={
                        "sort_order": j,
                        "surcharge_percent": SURCHARGE.get(label, D("0")),
                        "chest_cm": ADULT_CHEST.get(label, ""),
                    },
                )

        self.stdout.write("Seeding categories…")
        cats = {}
        for i, (slug, name, icon, children) in enumerate(CATEGORIES):
            parent, _ = Category.objects.update_or_create(slug=slug, defaults={"name": name, "icon": icon, "sort_order": i})
            cats[slug] = parent
            for j, (cslug, cname) in enumerate(children):
                child, _ = Category.objects.update_or_create(
                    slug=cslug, defaults={"name": cname, "parent": parent, "sort_order": j}
                )
                cats[cslug] = child
        # Intentionally empty category to prove the storefront hides it.
        Category.objects.update_or_create(
            slug="esports-apparel", defaults={"name": "Esports Apparel", "icon": "gamepad-2", "sort_order": 99}
        )

        self.stdout.write("Seeding products…")
        for (
            sku,
            name,
            cat,
            base,
            cons,
            labor,
            grp,
            genders,
            moq,
            lead,
            featured,
            tags,
            colors,
            fabric_opts,
            specs,
            short,
        ) in PRODUCTS:
            product, created = Product.objects.update_or_create(
                sku=sku,
                defaults={
                    "name": name,
                    "slug": slugify(name),
                    "category": cats[cat],
                    "base_fabric": fabrics[base],
                    "fabric_consumption_kg": D(cons),
                    "labor_price": D(labor),
                    "size_group": groups[grp],
                    "genders": genders,
                    "min_order_quantity": moq,
                    "lead_time_days": lead,
                    "is_featured": featured,
                    "is_new": sku.endswith("1") and featured,
                    "tags": tags,
                    "colors": colors,
                    "specifications": specs,
                    "short_description": short,
                    "description": (
                        f"{short} Made to order in Sialkot with {base.lower()} as the standard fabric; choose any listed fabric to move "
                        f"up or down in quality and price. Minimum order {moq} pieces, mixed sizes and genders allowed. "
                        f"Typical lead time {lead} days after artwork approval."
                    ),
                    "customization_options": {
                        "logo_placements": ["Left chest", "Right chest", "Back", "Sleeve", "Shorts leg"],
                        "print_methods": ["Sublimation", "Screen print", "Embroidery", "Heat transfer"],
                        "name_number": cat
                        in (
                            "soccer-kits",
                            "basketball-uniforms",
                            "cricket-kits",
                            "rugby-kits",
                            "volleyball-uniforms",
                            "hockey-kits",
                            "baseball-softball",
                        ),
                        "sponsor_logos": True,
                    },
                },
            )
            for fname in fabric_opts:
                ProductFabricOption.objects.update_or_create(
                    product=product, fabric=fabrics[fname], defaults={"is_default": fname == base}
                )
            sizes = list(groups[grp].sizes.all())
            for gender in genders:
                allowed = sizes
                if gender == "youth":
                    allowed = list(groups["Youth"].sizes.all()) if grp == "Adult" else sizes
                if gender in ("women",) and grp == "Adult":
                    allowed = [s for s in sizes if s.label not in ("4XL", "5XL")]
                for size in allowed:
                    ProductSizeOption.objects.update_or_create(product=product, gender=gender, size=size)
            product.save()  # recompute base_price via signal

        if options["demo"]:
            self._demo()
        self.stdout.write(
            self.style.SUCCESS(
                f"Done: {Fabric.objects.count()} fabrics, {Category.objects.count()} categories, {Product.objects.count()} products."
            )
        )

    def _demo(self):
        from apps.accounts.models import Address, Company, CompanyMember, User
        from apps.accounts.services import create_company
        from apps.payments.models import BankAccount

        self.stdout.write("Seeding demo accounts…")
        admin, _ = User.objects.get_or_create(
            email="admin@leepasports.com",
            defaults={
                "first_name": "Leepa",
                "last_name": "Admin",
                "is_staff": True,
                "is_superuser": True,
                "is_email_verified": True,
            },
        )
        if not admin.has_usable_password():
            admin.set_password("Admin!Leepa2026")
            admin.save()
        buyer, created = User.objects.get_or_create(
            email="buyer@riversidefc.com",
            defaults={"first_name": "Sam", "last_name": "Taylor", "is_email_verified": True, "job_title": "Kit Manager"},
        )
        if created:
            buyer.set_password("Buyer!Leepa2026")
            buyer.save()
            company = create_company(
                user=buyer,
                name="Riverside FC",
                business_type=Company.BusinessType.CLUB,
                country="GB",
                email="kit@riversidefc.com",
            )
            company.customer_group = CustomerGroup.objects.get(slug="club")
            company.approval_threshold = D("5000")
            company.save()
            Address.objects.create(
                company=company,
                kind=Address.Kind.SHIPPING,
                label="Clubhouse",
                contact_name="Sam Taylor",
                contact_phone="+44 20 7946 0000",
                line1="12 Riverside Way",
                city="Manchester",
                postal_code="M1 1AA",
                country="GB",
                is_default=True,
            )
            viewer, _ = User.objects.get_or_create(
                email="coach@riversidefc.com", defaults={"first_name": "Jordan", "last_name": "Lee", "is_email_verified": True}
            )
            viewer.set_password("Coach!Leepa2026")
            viewer.save()
            CompanyMember.objects.create(company=company, user=viewer, role=CompanyMember.Role.BUYER, order_limit=D("2000"))
        BankAccount.objects.get_or_create(
            label="Leepa Sports USD account",
            defaults={
                "bank_name": "Habib Bank Limited",
                "account_name": "Leepa Sports",
                "account_number": "0000-1234567-01",
                "iban": "PK00HABB0000001234567001",
                "swift": "HABBPKKA",
                "currency": "USD",
                "branch_address": "Sialkot Cantt Branch, Pakistan",
            },
        )
