import re
import unicodedata


SERVICE_CATEGORY_METADATA = [
    {
        "slug": "co-xuong-khop",
        "order": 0,
        "vi_name": "PHCN Cơ xương khớp",
        "en_name": "Musculoskeletal Rehabilitation",
        "vi_description": "Điều trị đau cột sống, thoái hóa khớp, viêm gân và các rối loạn cơ xương khớp.",
        "en_description": "Care for spine pain, degenerative joint disease, tendon disorders, and musculoskeletal conditions.",
        "icon_svg": '<svg class="w-9 h-9" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="1.7" d="M7 7a2.5 2.5 0 114 0v1.5a2 2 0 001 1.732l2 1.154A2 2 0 0115 13.118V14a2.5 2.5 0 104 0v-.882a2 2 0 00-1-1.732l-2-1.154A2 2 0 0115 8.5V7a2.5 2.5 0 10-4 0" /></svg>',
    },
    {
        "slug": "chan-thuong-chinh-hinh",
        "order": 1,
        "vi_name": "PHCN Chấn thương chỉnh hình",
        "en_name": "Orthopedic Trauma Rehabilitation",
        "vi_description": "Phục hồi sau gãy xương, đứt dây chằng, chấn thương thể thao và phẫu thuật chỉnh hình.",
        "en_description": "Recovery programs after fractures, ligament injuries, sports trauma, and orthopedic surgery.",
        "icon_svg": '<svg class="w-9 h-9" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="1.7" d="M7 4l10 10M9 20l11-11M5 8l3-3 2 2-3 3-2 4-2-2 4-4zm10 6l4-4 2 2-4 4-4 2-2-2 4-2z" /></svg>',
    },
    {
        "slug": "than-kinh",
        "order": 2,
        "vi_name": "PHCN Tổn thương thần kinh",
        "en_name": "Neurological Rehabilitation",
        "vi_description": "Can thiệp cho đột quỵ, tổn thương tủy sống, Parkinson và các rối loạn thần kinh vận động.",
        "en_description": "Intervention for stroke, spinal cord injury, Parkinson's disease, and neurological motor disorders.",
        "icon_svg": '<svg class="w-9 h-9" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="1.7" d="M12 3a4 4 0 014 4v1a3 3 0 013 3v1a3 3 0 01-2 2.83V17a2 2 0 01-2 2h-1v2m-4-2H9a2 2 0 01-2-2v-2.17A3 3 0 015 12v-1a3 3 0 013-3V7a4 4 0 014-4zm-2 6v1m4-1v1m-4 4a3 3 0 004 0" /></svg>',
    },
    {
        "slug": "sau-tai-bien",
        "order": 3,
        "vi_name": "PHCN Sau tai biến",
        "en_name": "Stroke Rehabilitation",
        "vi_description": "Chương trình phục hồi toàn diện sau tai biến để cải thiện vận động, ngôn ngữ và sinh hoạt hằng ngày.",
        "en_description": "Comprehensive post-stroke programs to improve movement, speech, and daily independence.",
        "icon_svg": '<svg class="w-9 h-9" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="1.7" d="M13 4a8 8 0 108 8m-1-6v5h-5M8 13l2 2 5-5" /></svg>',
    },
    {
        "slug": "sau-phau-thuat",
        "order": 4,
        "vi_name": "PHCN Sau phẫu thuật",
        "en_name": "Postoperative Rehabilitation",
        "vi_description": "Lộ trình phục hồi an toàn sau thay khớp, mổ cột sống, nội soi khớp và các can thiệp ngoại khoa.",
        "en_description": "Safe rehabilitation pathways after joint replacement, spine surgery, arthroscopy, and other operations.",
        "icon_svg": '<svg class="w-9 h-9" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="1.7" d="M14 5l5 5m-6.5-3.5l5 5M5 19l4.5-1.5L18 9 15 6 6.5 14.5 5 19zm11-14l2 2M4 20h7" /></svg>',
    },
    {
        "slug": "tim-mach",
        "order": 5,
        "vi_name": "Phục hồi tim mạch",
        "en_name": "Cardiac Rehabilitation",
        "vi_description": "Hỗ trợ phục hồi thể lực và kiểm soát nguy cơ cho người bệnh sau biến cố tim mạch.",
        "en_description": "Support for physical recovery and risk control after cardiovascular events.",
        "icon_svg": '<svg class="w-9 h-9" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="1.7" d="M4.5 12.5l3-3 3 5 3-8 3 6h3a3 3 0 010 6H7a5 5 0 01-2.5-9.33" /></svg>',
    },
    {
        "slug": "nhi-khoa",
        "order": 6,
        "vi_name": "Phục hồi nhi khoa",
        "en_name": "Pediatric Rehabilitation",
        "vi_description": "Phát triển vận động, giao tiếp và kỹ năng sinh hoạt cho trẻ cần hỗ trợ phục hồi chức năng.",
        "en_description": "Motor, communication, and daily-skills support for children in rehabilitation care.",
        "icon_svg": '<svg class="w-9 h-9" fill="none" stroke="currentColor" viewBox="0 0 24 24"><circle cx="12" cy="8" r="3.5" stroke-width="1.7" /><path stroke-linecap="round" stroke-linejoin="round" stroke-width="1.7" d="M7 20a5 5 0 0110 0M7.5 5.5L6 4m10.5 1.5L18 4" /></svg>',
    },
    {
        "slug": "vat-ly-tri-lieu",
        "order": 7,
        "vi_name": "Vật lý trị liệu",
        "en_name": "Physical Therapy",
        "vi_description": "Các kỹ thuật vận động trị liệu và phương thức vật lý giúp giảm đau, tăng sức mạnh và phục hồi chức năng.",
        "en_description": "Movement-based therapy and physical modalities to reduce pain, build strength, and restore function.",
        "icon_svg": '<svg class="w-9 h-9" fill="none" stroke="currentColor" viewBox="0 0 24 24"><circle cx="13" cy="5" r="2.2" stroke-width="1.7" /><path stroke-linecap="round" stroke-linejoin="round" stroke-width="1.7" d="M11 8l-2 4 3 2 1 5m-1-8l4-1 2 3m-8 0l-4 1m7 0l3 5m-6 0H6" /></svg>',
    },
    {
        "slug": "hoat-dong-tri-lieu",
        "order": 8,
        "vi_name": "Hoạt động trị liệu",
        "en_name": "Occupational Therapy",
        "vi_description": "Tăng khả năng tự lập trong sinh hoạt, lao động và các kỹ năng tinh xảo của bàn tay.",
        "en_description": "Improve independence in daily living, work-related tasks, and fine motor hand skills.",
        "icon_svg": '<svg class="w-9 h-9" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="1.7" d="M8 11V6a1.5 1.5 0 113 0v4m0-5.5a1.5 1.5 0 013 0V10m0-4a1.5 1.5 0 013 0v6a6 6 0 11-12 0v-1a1.5 1.5 0 013 0z" /></svg>',
    },
    {
        "slug": "ngon-ngu-tri-lieu",
        "order": 9,
        "vi_name": "Ngôn ngữ trị liệu",
        "en_name": "Speech Therapy",
        "vi_description": "Hỗ trợ nói, nuốt, phát âm và giao tiếp cho trẻ em và người lớn sau bệnh lý thần kinh.",
        "en_description": "Support for speech, swallowing, pronunciation, and communication in children and adults.",
        "icon_svg": '<svg class="w-9 h-9" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="1.7" d="M7 7h10a3 3 0 013 3v3a3 3 0 01-3 3h-5l-4 3v-3H7a3 3 0 01-3-3v-3a3 3 0 013-3zm3 4h4m-4 3h6" /></svg>',
    },
    {
        "slug": "dinh-duong",
        "order": 10,
        "vi_name": "Tư vấn dinh dưỡng",
        "en_name": "Nutrition Counseling",
        "vi_description": "Tư vấn chế độ ăn hỗ trợ điều trị, phục hồi và kiểm soát cân nặng theo tình trạng bệnh.",
        "en_description": "Diet counseling to support treatment, recovery, and weight management based on each condition.",
        "icon_svg": '<svg class="w-9 h-9" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="1.7" d="M12 20c4-2.2 6-5.3 6-9a5 5 0 00-10 0c0 3.7 2 6.8 4 9zm0 0c-2.6-1.4-6-4.6-6-8.5A4.5 4.5 0 0110.5 7c1 0 1.9.32 2.5.86A4.48 4.48 0 0115.5 7 4.5 4.5 0 0120 11.5" /></svg>',
    },
]

SERVICE_CATEGORY_BY_SLUG = {item["slug"]: item for item in SERVICE_CATEGORY_METADATA}
SERVICE_CATEGORY_LABELS = {
    item["slug"]: {"vi": item["vi_name"], "en": item["en_name"]}
    for item in SERVICE_CATEGORY_METADATA
}
DEFAULT_SERVICE_CATEGORIES = [(item["en_name"], item["slug"]) for item in SERVICE_CATEGORY_METADATA]

SERVICE_CATEGORY_KEYWORDS = {
    "co-xuong-khop": ("co-xuong-khop", "musculoskeletal", "bone", "joint", "spine", "orthopedic", "xuong", "khop"),
    "chan-thuong-chinh-hinh": ("chan-thuong", "chinh-hinh", "orthopedic-trauma", "fracture", "ligament", "sports", "injury"),
    "than-kinh": ("than-kinh", "neurolog", "nerve", "spinal", "parkinson"),
    "sau-tai-bien": ("sau-tai-bien", "tai-bien", "dot-quy", "stroke"),
    "sau-phau-thuat": ("sau-phau-thuat", "hau-phau", "post-op", "postoperative", "surgery"),
    "tim-mach": ("tim-mach", "cardiac", "cardio", "heart"),
    "nhi-khoa": ("nhi-khoa", "pediatric", "child", "tre-em"),
    "vat-ly-tri-lieu": ("vat-ly-tri-lieu", "physical-therapy", "physiotherapy"),
    "hoat-dong-tri-lieu": ("hoat-dong-tri-lieu", "occupational-therapy"),
    "ngon-ngu-tri-lieu": ("ngon-ngu-tri-lieu", "speech-therapy", "language-therapy", "swallow"),
    "dinh-duong": ("dinh-duong", "nutrition", "diet"),
}


def get_service_category_meta(slug: str) -> dict | None:
    return SERVICE_CATEGORY_BY_SLUG.get(slug)


def get_service_category_label(slug: str, lang: str = "en") -> str:
    meta = get_service_category_meta(slug)
    if not meta:
        return slug or ""
    return meta["en_name"] if str(lang).lower().startswith("en") else meta["vi_name"]


def get_service_category_description(slug: str, lang: str = "en") -> str:
    meta = get_service_category_meta(slug)
    if not meta:
        return ""
    return meta["en_description"] if str(lang).lower().startswith("en") else meta["vi_description"]


def _normalize_text(value: str) -> str:
    text = unicodedata.normalize("NFKD", (value or "").strip().lower())
    text = "".join(ch for ch in text if not unicodedata.combining(ch))
    text = text.replace("đ", "d")
    text = re.sub(r"[^a-z0-9]+", "-", text)
    return text.strip("-")


def sync_service_categories():
    from .models import ServiceCategory

    categories = {}
    for item in SERVICE_CATEGORY_METADATA:
        category, _ = ServiceCategory.objects.get_or_create(
            slug=item["slug"],
            defaults={
                "name": item["en_name"],
                "description": item["en_description"],
                "icon_svg": item["icon_svg"],
                "order": item["order"],
            },
        )
        changed = []
        for field, value in (
            ("name", item["en_name"]),
            ("description", item["en_description"]),
            ("icon_svg", item["icon_svg"]),
            ("order", item["order"]),
        ):
            if getattr(category, field) != value:
                setattr(category, field, value)
                changed.append(field)
        if changed:
            category.save(update_fields=changed)
        categories[item["slug"]] = category
    return categories


def guess_service_category_slug(service) -> str | None:
    source = " ".join(
        filter(
            None,
            [
                getattr(service, "slug", ""),
                getattr(service, "title", ""),
                getattr(service, "summary", ""),
            ],
        )
    )
    normalized = _normalize_text(source)
    if not normalized:
        return None

    for slug, keywords in SERVICE_CATEGORY_KEYWORDS.items():
        if any(keyword in normalized for keyword in keywords):
            return slug
    return None


def auto_assign_service_categories():
    from .models import Service

    categories_by_slug = sync_service_categories()
    updated = 0
    for service in Service.objects.select_related("category").all():
        target_slug = guess_service_category_slug(service)
        if not target_slug:
            continue
        target = categories_by_slug.get(target_slug)
        if target and service.category_id != target.id:
            service.category = target
            service.save(update_fields=["category"])
            updated += 1
    return updated
