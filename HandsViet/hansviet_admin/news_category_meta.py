NEWS_CATEGORY_METADATA = [
    {
        "slug": "tin-tuc-y-khoa",
        "vi_name": "Tin tức Y khoa",
        "en_name": "Medical News",
    },
    {
        "slug": "cau-chuyen-khach-hang",
        "vi_name": "Câu chuyện khách hàng",
        "en_name": "Customer Stories",
    },
    {
        "slug": "tin-truyen-thong",
        "vi_name": "Tin truyền thông",
        "en_name": "Media News",
    },
    {
        "slug": "tu-van-phcn",
        "vi_name": "Tư vấn PHCN",
        "en_name": "Rehabilitation Consulting",
    },
    {
        "slug": "khuyen-mai-su-kien",
        "vi_name": "Khuyến mãi sự kiện",
        "en_name": "Promotions & Events",
    },
]

NEWS_CATEGORY_BY_SLUG = {item["slug"]: item for item in NEWS_CATEGORY_METADATA}
NEWS_CATEGORY_LABELS = {
    item["slug"]: {"vi": item["vi_name"], "en": item["en_name"]}
    for item in NEWS_CATEGORY_METADATA
}
DEFAULT_NEWS_CATEGORIES = [(item["en_name"], item["slug"]) for item in NEWS_CATEGORY_METADATA]


def get_news_category_label(slug: str, lang: str = "en") -> str:
    meta = NEWS_CATEGORY_BY_SLUG.get((slug or "").strip())
    if not meta:
        return ""
    return meta["en_name"] if str(lang).lower().startswith("en") else meta["vi_name"]


def sync_news_categories():
    from .models import NewsCategory

    categories = {}
    for item in NEWS_CATEGORY_METADATA:
        category, _ = NewsCategory.objects.get_or_create(
            slug=item["slug"],
            defaults={"name": item["en_name"]},
        )
        if category.name != item["en_name"]:
            category.name = item["en_name"]
            category.save(update_fields=["name"])
        categories[item["slug"]] = category
    return categories
