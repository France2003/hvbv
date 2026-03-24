import imghdr
import unicodedata
from urllib.request import Request, urlopen

from django.core.files.base import ContentFile
from django.core.management.base import BaseCommand
from django.db.models import Count
from django.utils import timezone

from hansviet_admin.models import NewsArticle
from hansviet_admin.news_category_meta import sync_news_categories
from hansviet_admin.services.news_content import ensure_detailed_content, ensure_summary
from hansviet_admin.services.perplexity_news import translate_news_item, unique_article_slug
from hansviet_admin.services.rss_news import fetch_rss_items


DEFAULT_FEEDS = [
    ("https://vnexpress.net/rss/suc-khoe.rss", "VnExpress"),
    ("https://tuoitre.vn/rss/suc-khoe.rss", "Tuoi Tre"),
    ("https://thanhnien.vn/rss/suc-khoe.rss", "Thanh Nien"),
]

CATEGORY_SLUGS = {
    "story": "cau-chuyen-khach-hang",
    "event": "khuyen-mai-su-kien",
    "media": "tin-truyen-thong",
    "medical": "tin-tuc-y-khoa",
    "consult": "tu-van-phcn",
}

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
    return base.replace("\u0111", "d").replace("\u0110", "d")


def _topic_scores(title: str, summary: str, source_name: str) -> dict[str, int]:
    text = _normalize_text(f"{title} {summary} {source_name}")
    scores = {slug: 0 for slug in KEYWORDS_BY_CATEGORY.keys()}
    for slug, rows in KEYWORDS_BY_CATEGORY.items():
        for phrase, weight in rows:
            if phrase in text:
                scores[slug] += weight
    if "suc khoe" in text or "y te" in text:
        scores[CATEGORY_SLUGS["medical"]] += 1
    return scores


def _topic_category_slug(title: str, summary: str, source_name: str) -> str | None:
    scores = _topic_scores(title, summary, source_name)
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


def _build_bilingual_payload(item, category_name: str) -> dict:
    source_payload = {
        "title": item.title or "",
        "summary": item.summary or "",
        "content": item.content or "",
        "source_url": item.source_url or "",
        "source_name": item.source_name or "",
        "image_url": item.image_url or "",
        "published_at": item.published_at.isoformat() if item.published_at else "",
    }

    try:
        en_payload = translate_news_item(source_payload, target_language="en", category_name=category_name)
    except Exception:
        en_payload = source_payload

    en_title = (en_payload.get("title") or "").strip() or (item.title or "").strip()
    en_summary = ensure_summary(en_title, en_payload.get("summary") or item.summary or "", lang="en")
    en_content = ensure_detailed_content(
        title=en_title,
        summary=en_summary,
        content=en_payload.get("content") or item.content or "",
        source_url=item.source_url,
        source_name=item.source_name,
        category_name=category_name,
        image_url=item.image_url,
        lang="en",
    )

    canonical_en = {
        "title": en_title,
        "summary": en_summary,
        "content": en_content,
        "source_url": item.source_url or "",
        "source_name": item.source_name or "",
        "image_url": item.image_url or "",
        "published_at": item.published_at.isoformat() if item.published_at else "",
    }

    try:
        vi_payload = translate_news_item(canonical_en, target_language="vi", category_name=category_name)
    except Exception:
        vi_payload = {}

    vi_title = (vi_payload.get("title") or "").strip() or en_title
    vi_summary = ensure_summary(vi_title, vi_payload.get("summary") or en_summary, lang="vi")
    vi_content = ensure_detailed_content(
        title=vi_title,
        summary=vi_summary,
        content=vi_payload.get("content") or en_content,
        source_url=item.source_url,
        source_name=item.source_name,
        category_name=category_name,
        image_url=item.image_url,
        lang="vi",
    )

    return {
        "title_en": en_title,
        "summary_en": en_summary,
        "content_en": en_content,
        "title_vi": vi_title,
        "summary_vi": vi_summary,
        "content_vi": vi_content,
    }


class Command(BaseCommand):
    help = "Sync news from RSS feeds, store EN canonical content, and generate VI translation."

    def add_arguments(self, parser):
        parser.add_argument("--max-items", type=int, default=3, help="Max items per feed.")
        parser.add_argument("--publish", action="store_true", help="Publish immediately.")
        parser.add_argument("--feed", action="append", dest="feeds", help="Custom RSS feed URL.")
        parser.add_argument(
            "--balanced",
            action="store_true",
            help="When topic is unclear, spread items across categories instead of using fallback category.",
        )
        parser.add_argument(
            "--fallback-category",
            type=str,
            default=CATEGORY_SLUGS["medical"],
            help="Fallback category slug when classifier cannot infer topic.",
        )

    def handle(self, *args, **options):
        max_items = max(1, int(options["max_items"]))
        auto_publish = bool(options.get("publish"))
        balanced = bool(options.get("balanced"))
        created_count = 0
        skipped_count = 0

        custom_feeds = options.get("feeds") or []
        feed_rows = list(DEFAULT_FEEDS)
        if custom_feeds:
            feed_rows = [(u.strip(), "RSS Custom") for u in custom_feeds if u.strip()]

        categories_by_slug = sync_news_categories()
        if CATEGORY_SLUGS["medical"] not in categories_by_slug:
            self.stdout.write(self.style.ERROR("Missing required category 'tin-tuc-y-khoa'."))
            return

        fallback_slug = (options.get("fallback_category") or "").strip() or CATEGORY_SLUGS["medical"]
        if fallback_slug not in categories_by_slug:
            self.stdout.write(
                self.style.WARNING(
                    f"Fallback category '{fallback_slug}' not found. Use '{CATEGORY_SLUGS['medical']}' instead."
                )
            )
            fallback_slug = CATEGORY_SLUGS["medical"]

        bucket_order = [
            CATEGORY_SLUGS["consult"],
            CATEGORY_SLUGS["medical"],
            CATEGORY_SLUGS["media"],
            CATEGORY_SLUGS["story"],
            CATEGORY_SLUGS["event"],
        ]
        created_buckets = {slug: 0 for slug in bucket_order}
        existing_counts = {slug: 0 for slug in bucket_order}
        for row in (
            NewsArticle.objects.filter(category__slug__in=bucket_order)
            .values("category__slug")
            .annotate(n=Count("id"))
        ):
            existing_counts[row["category__slug"]] = int(row["n"])

        def _least_filled_slug() -> str:
            return min(bucket_order, key=lambda slug: existing_counts.get(slug, 0) + created_buckets.get(slug, 0))

        def _download_image_file(url: str, title: str) -> ContentFile | None:
            if not url:
                return None
            try:
                req = Request(url, headers={"User-Agent": "Mozilla/5.0 (HandsViet RSS Bot)"})
                with urlopen(req, timeout=45) as resp:
                    data = resp.read()
                if not data:
                    return None
                kind = imghdr.what(None, h=data) or "jpg"
                if kind == "jpeg":
                    kind = "jpg"
                safe_title = "".join(ch if ch.isalnum() else "-" for ch in (title or "rss-news")).strip("-").lower()
                safe_title = safe_title[:50] or "rss-news"
                name = f"{safe_title}-{timezone.now().strftime('%Y%m%d%H%M%S')}.{kind}"
                cf = ContentFile(data)
                cf.name = name
                return cf
            except Exception:
                return None

        for feed_url, source_name in feed_rows:
            self.stdout.write(f"Syncing RSS: {feed_url}")
            try:
                items = fetch_rss_items(feed_url, source_name=source_name, max_items=max_items)
            except Exception as ex:
                self.stdout.write(self.style.ERROR(f"RSS error '{feed_url}': {ex}"))
                continue

            for item in items:
                if item.source_url and NewsArticle.objects.filter(source_url=item.source_url).exists():
                    skipped_count += 1
                    continue

                topic_slug = _topic_category_slug(item.title, item.summary, item.source_name)
                if topic_slug:
                    chosen_slug = topic_slug
                elif balanced:
                    chosen_slug = _least_filled_slug()
                else:
                    chosen_slug = fallback_slug

                target_category = categories_by_slug.get(chosen_slug) or categories_by_slug[fallback_slug]
                bilingual = _build_bilingual_payload(item, target_category.name)

                en_title = (bilingual["title_en"] or "").strip()
                vi_title = (bilingual["title_vi"] or "").strip()
                if not en_title and not vi_title:
                    skipped_count += 1
                    continue

                if en_title and NewsArticle.objects.filter(title_en__iexact=en_title).exists():
                    skipped_count += 1
                    continue
                if vi_title and NewsArticle.objects.filter(title__iexact=vi_title).exists():
                    skipped_count += 1
                    continue

                slug_seed = en_title or vi_title
                slug_value = unique_article_slug(slug_seed, exists_fn=lambda s: NewsArticle.objects.filter(slug=s).exists())

                article = NewsArticle.objects.create(
                    category=target_category,
                    title=vi_title or en_title,
                    title_en=en_title,
                    slug=slug_value,
                    summary=bilingual["summary_vi"],
                    summary_en=bilingual["summary_en"],
                    content=bilingual["content_vi"],
                    content_en=bilingual["content_en"],
                    is_published=auto_publish,
                    source_url=item.source_url,
                    source_name=item.source_name,
                    ai_source="rss",
                    is_auto_generated=True,
                    needs_review=not auto_publish,
                )
                if item.published_at:
                    published_at = item.published_at
                    if timezone.is_naive(published_at):
                        published_at = timezone.make_aware(published_at, timezone.get_current_timezone())
                    article.published_at = published_at
                    article.save(update_fields=["published_at"])

                if item.image_url:
                    image_file = _download_image_file(item.image_url, en_title or vi_title)
                    if image_file:
                        article.thumbnail.save(image_file.name, image_file, save=True)

                created_buckets[chosen_slug] = created_buckets.get(chosen_slug, 0) + 1
                created_count += 1

        self.stdout.write(
            self.style.SUCCESS(
                f"Done RSS sync. created={created_count}, skipped={skipped_count}, "
                f"mode={'publish' if auto_publish else 'draft'}, balanced={balanced}, at={timezone.now()}"
            )
        )
