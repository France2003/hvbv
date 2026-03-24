import html

from django.core.management.base import BaseCommand

from hansviet_admin.models import NewsArticle, NewsCategory

CATEGORY_NAME_BY_SLUG = {
    "tin-tuc-y-khoa": "Tin tức Y khoa",
    "cau-chuyen-khach-hang": "Câu chuyện khách hàng",
    "tin-truyen-thong": "Tin truyền thông",
    "tu-van-phcn": "Tư vấn PHCN",
    "khuyen-mai-su-kien": "Khuyến mãi sự kiện",
}


def repair_text(value: str) -> str:
    text = html.unescape((value or "").strip())
    for _ in range(2):
        if not any(tok in text for tok in ("Ã", "Ä", "Â", "á»", "áº", "Æ°", "Æ¡", "â€", "â€“", "â€”", "�", "&amp;", "&#")):
            break
        try:
            candidate = text.encode("latin1", errors="ignore").decode("utf-8", errors="ignore")
        except Exception:
            break
        if candidate and candidate != text:
            text = candidate
        else:
            break
    return text


class Command(BaseCommand):
    help = "Fix mojibake and HTML entities in NewsCategory.name and NewsArticle title/summary/content/source_name."

    def add_arguments(self, parser):
        parser.add_argument("--limit", type=int, default=0, help="0 means all.")

    def handle(self, *args, **options):
        qs = NewsArticle.objects.all().order_by("-id")
        limit = int(options["limit"])
        updated = 0
        scanned = 0

        categories_updated = 0
        for category in NewsCategory.objects.all():
            old_name = category.name or ""
            new_name = CATEGORY_NAME_BY_SLUG.get(category.slug) or repair_text(old_name)
            if new_name and new_name != old_name:
                category.name = new_name
                category.save(update_fields=["name"])
                categories_updated += 1

        for article in qs:
            scanned += 1
            if limit > 0 and scanned > limit:
                break

            old_title = article.title or ""
            old_summary = article.summary or ""
            old_content = article.content or ""
            old_source = article.source_name or ""

            new_title = repair_text(old_title)
            new_summary = repair_text(old_summary)
            new_content = repair_text(old_content)
            new_source = repair_text(old_source)

            if (new_title, new_summary, new_content, new_source) != (old_title, old_summary, old_content, old_source):
                article.title = new_title
                article.summary = new_summary
                article.content = new_content
                article.source_name = new_source
                article.save(update_fields=["title", "summary", "content", "source_name"])
                updated += 1

        self.stdout.write(self.style.SUCCESS(f"Fix done. categories_updated={categories_updated}, articles_updated={updated}, articles_scanned={scanned}"))

