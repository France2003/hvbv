import unicodedata

from django.core.management.base import BaseCommand
from django.db.models import Count

from hansviet_admin.models import NewsArticle, NewsCategory


CATEGORY_SLUGS = {
    "story": "cau-chuyen-khach-hang",
    "event": "khuyen-mai-su-kien",
    "media": "tin-truyen-thong",
    "medical": "tin-tuc-y-khoa",
    "consult": "tu-van-phcn",
}
CATEGORY_ORDER = [
    CATEGORY_SLUGS["story"],
    CATEGORY_SLUGS["event"],
    CATEGORY_SLUGS["media"],
    CATEGORY_SLUGS["medical"],
    CATEGORY_SLUGS["consult"],
]

KEYWORDS_BY_CATEGORY = {
    CATEGORY_SLUGS["event"]: [
        ("khuyen mai", 4),
        ("uu dai", 4),
        ("mien phi", 3),
        ("giam gia", 3),
        ("su kien", 3),
        ("workshop", 3),
        ("hoi thao", 3),
        ("dang ky", 2),
        ("chuong trinh", 2),
    ],
    CATEGORY_SLUGS["media"]: [
        ("truyen thong", 4),
        ("bao chi", 3),
        ("thong cao", 3),
        ("phong su", 3),
        ("dua tin", 2),
        ("phat song", 2),
        ("truyen hinh", 2),
        ("media", 2),
    ],
    CATEGORY_SLUGS["story"]: [
        ("cau chuyen", 4),
        ("hanh trinh", 3),
        ("khach hang", 3),
        ("benh nhan chia se", 4),
        ("chia se", 2),
        ("vuot qua", 2),
        ("case study", 3),
    ],
    CATEGORY_SLUGS["consult"]: [
        ("phuc hoi chuc nang", 4),
        ("phcn", 4),
        ("vat ly tri lieu", 4),
        ("hoat dong tri lieu", 4),
        ("ngon ngu tri lieu", 4),
        ("rehab", 3),
        ("huong dan", 2),
        ("tu van", 2),
        ("cham soc tai nha", 2),
        ("dau lung", 2),
        ("xuong khop", 2),
        ("dot quy", 2),
        ("sau mo", 2),
    ],
    CATEGORY_SLUGS["medical"]: [
        ("y te", 2),
        ("suc khoe", 2),
        ("benh", 2),
        ("trieu chung", 2),
        ("dieu tri", 2),
        ("nghien cuu", 2),
        ("vaccine", 2),
        ("virus", 2),
        ("kham", 1),
        ("bac si", 1),
        ("xet nghiem", 1),
    ],
}


def _normalize_text(text: str) -> str:
    base = (text or "").lower()
    base = "".join(ch for ch in unicodedata.normalize("NFD", base) if unicodedata.category(ch) != "Mn")
    return base.replace("đ", "d").replace("Đ", "d")


def pick_topic_category_slug(title: str, summary: str, source_name: str) -> str | None:
    text = _normalize_text(f"{title} {summary} {source_name}")
    scores = {slug: 0 for slug in KEYWORDS_BY_CATEGORY.keys()}
    for slug, rows in KEYWORDS_BY_CATEGORY.items():
        for phrase, weight in rows:
            if phrase in text:
                scores[slug] += weight

    best_slug = max(scores.keys(), key=lambda slug: scores.get(slug, 0))
    best_score = scores.get(best_slug, 0)
    if best_score <= 0:
        return None

    priority = [
        CATEGORY_SLUGS["event"],
        CATEGORY_SLUGS["media"],
        CATEGORY_SLUGS["story"],
        CATEGORY_SLUGS["consult"],
        CATEGORY_SLUGS["medical"],
    ]
    top_slugs = {slug for slug, score in scores.items() if score == best_score}
    for slug in priority:
        if slug in top_slugs:
            return slug
    return best_slug


def _least_filled_slug(total_counts: dict[str, int], changed_counts: dict[str, int]) -> str:
    return min(
        CATEGORY_ORDER,
        key=lambda slug: (total_counts.get(slug, 0) + changed_counts.get(slug, 0), changed_counts.get(slug, 0)),
    )


class Command(BaseCommand):
    help = "Reclassify existing news articles by topic; optional rebalance across categories."

    def add_arguments(self, parser):
        parser.add_argument("--limit", type=int, default=0, help="0 means all.")
        parser.add_argument("--only-auto", action="store_true", help="Only auto-generated articles.")
        parser.add_argument("--rebalance", action="store_true", help="Balance uncategorized items across all categories.")

    def handle(self, *args, **options):
        categories = {c.slug: c for c in NewsCategory.objects.all()}
        missing = [slug for slug in CATEGORY_ORDER if slug not in categories]
        if missing:
            self.stdout.write(self.style.ERROR(f"Missing categories: {', '.join(missing)}"))
            return

        qs = NewsArticle.objects.select_related("category").all().order_by("-id")
        if options["only_auto"]:
            qs = qs.filter(is_auto_generated=True)

        total_counts = {slug: 0 for slug in CATEGORY_ORDER}
        for row in (
            NewsArticle.objects.filter(category__slug__in=CATEGORY_ORDER)
            .values("category__slug")
            .annotate(n=Count("id"))
        ):
            total_counts[row["category__slug"]] = int(row["n"])
        changed_counts = {slug: 0 for slug in CATEGORY_ORDER}

        changed = 0
        scanned = 0
        limit = int(options["limit"])

        for article in qs:
            scanned += 1
            if limit > 0 and scanned > limit:
                break

            topic_slug = pick_topic_category_slug(article.title, article.summary, article.source_name)
            if topic_slug:
                target_slug = topic_slug
            elif options["rebalance"]:
                target_slug = _least_filled_slug(total_counts, changed_counts)
            else:
                target_slug = CATEGORY_SLUGS["medical"]

            target_category = categories[target_slug]
            if article.category_id != target_category.id:
                article.category = target_category
                article.save(update_fields=["category"])
                changed += 1
                changed_counts[target_slug] += 1

        self.stdout.write(self.style.SUCCESS(f"Reclassify done. changed={changed}, scanned={scanned}"))

