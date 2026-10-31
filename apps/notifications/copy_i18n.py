"""Urdu and Arabic copy for in-app order notifications (English lives in handlers.STATUS_COPY)."""

STATUS_COPY_I18N = {
    "ur": {
        "confirmed": ("آرڈر کنفرم", "ہم نے آپ کا آرڈر کنفرم کر دیا ہے اور تیاری شروع ہے۔"),
        "processing": ("پیکنگ جاری", "آپ کا آرڈر ہمارے سیالکوٹ اسٹوڈیو میں پیک ہو رہا ہے۔"),
        "shipped": ("روانہ", "آپ کا پارسل راستے میں ہے۔"),
        "out_for_delivery": ("ڈیلیوری کے لیے نکل چکا", "رائیڈر کے پاس آپ کا پارسل ہے — فون پاس رکھیں۔"),
        "delivered": ("ڈیلیور ہو گیا", "لطف اٹھائیں! فٹنگ کیسی رہی، ریویو میں بتائیں۔"),
        "completed": ("مکمل", "Chobbar سے خریداری کا شکریہ۔"),
        "cancelled": ("منسوخ", "آپ کا آرڈر منسوخ کر دیا گیا۔"),
        "returned": ("واپس", "آپ کی واپسی مکمل ہو گئی۔"),
    },
    "ar": {
        "confirmed": ("تم تأكيد الطلب", "أكدنا طلبك ونقوم بتجهيزه."),
        "processing": ("قيد التغليف", "يتم تغليف طلبك في استوديو سيالكوت."),
        "shipped": ("تم الشحن", "طردك في الطريق إليك."),
        "out_for_delivery": ("خرج للتوصيل", "المندوب يحمل طردك — أبقِ هاتفك قريباً."),
        "delivered": ("تم التوصيل", "استمتع! أخبرنا عن المقاس بمراجعة سريعة."),
        "completed": ("مكتمل", "شكراً لتسوقك من Chobbar."),
        "cancelled": ("أُلغي", "تم إلغاء طلبك."),
        "returned": ("مُرجع", "تمت معالجة الإرجاع."),
    },
}


def status_copy(language: str, status: str, fallback: tuple[str, str]) -> tuple[str, str]:
    return STATUS_COPY_I18N.get(language, {}).get(status, fallback)
