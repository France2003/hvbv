import imghdr
import re
from urllib.request import Request, urlopen

from django.conf import settings
from django.core.files.base import ContentFile
from django.core.management.base import BaseCommand
from django.utils import timezone

from hansviet_admin.models import NewsArticle, NewsCategory
from hansviet_admin.news_category_meta import sync_news_categories
from hansviet_admin.services.news_content import ensure_detailed_content, ensure_summary
from hansviet_admin.services.perplexity_news import (
    fetch_category_news,
    translate_news_item,
    unique_article_slug,
)


DEFAULT_CATEGORY_SLUGS = [
    "tin-tuc-y-khoa",
    "tu-van-phcn",
    "tin-truyen-thong",
    "khuyen-mai-su-kien",
    "cau-chuyen-khach-hang",
]


def _extract_og_image(source_url: str) -> str:
    if not source_url:
        return ""
    try:
        req = Request(source_url, headers={"User-Agent": "Mozilla/5.0 (HandsViet News Bot)"})
        with urlopen(req, timeout=settings.PPLX_TIMEOUT) as resp:
            html = resp.read().decode("utf-8", errors="ignore")
        match = re.search(
            r'<meta[^>]+property=["\']og:image["\'][^>]+content=["\']([^"\']+)["\']',
            html,
            flags=re.IGNORECASE,
        )
        return (match.group(1).strip() if match else "")
    except Exception:
        return ""


def _download_image_file(url: str, title: str) -> ContentFile | None:
    if not url:
        return None
    try:
        req = Request(url, headers={"User-Agent": "Mozilla/5.0 (HandsViet News Bot)"})
        with urlopen(req, timeout=settings.PPLX_TIMEOUT) as resp:
            data = resp.read()
        if not data:
            return None
        kind = imghdr.what(None, h=data) or "jpg"
        if kind == "jpeg":
            kind = "jpg"
        safe_title = "".join(ch if ch.isalnum() else "-" for ch in (title or "news-image")).strip("-").lower()
        safe_title = safe_title[:50] or "news-image"
        name = f"{safe_title}-{timezone.now().strftime('%Y%m%d%H%M%S')}.{kind}"
        cf = ContentFile(data)
        cf.name = name
        return cf
    except Exception:
        return None


def _build_bilingual_payload(item, category_name: str) -> dict:
    en_title = (item.title or "").strip()
    en_summary = ensure_summary(en_title, item.summary or "", lang="en")
    en_content = ensure_detailed_content(
        title=en_title,
        summary=en_summary,
        content=item.content or "",
        source_url=item.source_url,
        source_name=item.source_name,
        category_name=category_name,
        image_url=item.image_url,
        lang="en",
    )

    en_payload = {
        "title": en_title,
        "summary": en_summary,
        "content": en_content,
        "source_url": item.source_url or "",
        "source_name": item.source_name or "",
        "image_url": item.image_url or "",
        "published_at": item.published_at.isoformat() if item.published_at else "",
    }

    try:
        vi_payload = translate_news_item(en_payload, target_language="vi", category_name=category_name)
    except Exception:
        vi_payload = {
            "title": "",
            "summary": "",
            "content": "",
            "source_url": item.source_url or "",
            "source_name": item.source_name or "",
            "image_url": item.image_url or "",
            "published_at": item.published_at.isoformat() if item.published_at else "",
        }

    vi_title_raw = (vi_payload.get("title") or "").strip() or en_title
    vi_summary_raw = (vi_payload.get("summary") or "").strip()
    vi_content_raw = (vi_payload.get("content") or "").strip()

    vi_summary = ensure_summary(vi_title_raw, vi_summary_raw or en_summary, lang="vi")
    vi_content = ensure_detailed_content(
        title=vi_title_raw,
        summary=vi_summary,
        content=vi_content_raw or en_content,
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
        "title_vi": vi_title_raw,
        "summary_vi": vi_summary,
        "content_vi": vi_content,
    }


class Command(BaseCommand):
    help = "Sync medical news from Perplexity-compatible API and save EN canonical + VI translation."

    def add_arguments(self, parser):
        parser.add_argument("--category", action="append", dest="categories", help="Category slug to sync.")
        parser.add_argument("--max-items", type=int, default=3, help="Max items per category.")
        parser.add_argument("--publish", action="store_true", help="Publish immediately.")
        parser.add_argument("--model", type=str, default="", help="Override model for this run.")

    def handle(self, *args, **options):
        sync_news_categories()

        category_slugs = options.get("categories") or DEFAULT_CATEGORY_SLUGS
        max_items = max(1, options["max_items"])
        auto_publish = bool(options.get("publish")) or settings.PPLX_AUTO_PUBLISH

        model_override = (options.get("model") or "").strip()
        if model_override:
            settings.PPLX_MODEL = model_override

        created_count = 0
        skipped_count = 0

        for slug in category_slugs:
            category = NewsCategory.objects.filter(slug=slug).first()
            if not category:
                self.stdout.write(self.style.WARNING(f"Skip '{slug}': category not found."))
                continue

            self.stdout.write(f"Syncing category: {slug}")
            try:
                items = fetch_category_news(category.name, max_items=max_items)
            except Exception as ex:
                self.stdout.write(self.style.ERROR(f"Error fetching '{slug}': {ex}"))
                continue

            for item in items:
                if item.source_url and NewsArticle.objects.filter(source_url=item.source_url).exists():
                    skipped_count += 1
                    continue

                bilingual = _build_bilingual_payload(item, category.name)
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

                image_url = (item.image_url or "").strip()
                if not image_url and item.source_url:
                    image_url = _extract_og_image(item.source_url)

                article = NewsArticle.objects.create(
                    category=category,
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
                    ai_source="perplexity-compatible",
                    is_auto_generated=True,
                    needs_review=not auto_publish,
                )

                if item.published_at:
                    published_at = item.published_at
                    if timezone.is_naive(published_at):
                        published_at = timezone.make_aware(published_at, timezone.get_current_timezone())
                    article.published_at = published_at
                    article.save(update_fields=["published_at"])

                if image_url:
                    image_file = _download_image_file(image_url, en_title or vi_title)
                    if image_file:
                        article.thumbnail.save(image_file.name, image_file, save=True)
                created_count += 1

        self.stdout.write(
            self.style.SUCCESS(
                f"Done. created={created_count}, skipped={skipped_count}, "
                f"mode={'publish' if auto_publish else 'draft'}, at={timezone.now()}"
            )
        )
