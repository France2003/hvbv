from django.core.management.base import BaseCommand

from hansviet_admin.models import NewsArticle
from hansviet_admin.services.news_content import ensure_detailed_content, ensure_summary


class Command(BaseCommand):
    help = "Expand existing short news articles to a richer, more detailed format."

    def add_arguments(self, parser):
        parser.add_argument("--only-published", action="store_true", help="Only enrich published articles.")
        parser.add_argument("--min-len", type=int, default=1800, help="Only enrich content shorter than this length.")
        parser.add_argument("--limit", type=int, default=0, help="Limit number of articles. 0 means all.")

    def handle(self, *args, **options):
        qs = NewsArticle.objects.select_related("category").all().order_by("-id")
        if options["only_published"]:
            qs = qs.filter(is_published=True)
        min_len = int(options["min_len"])
        qs = qs.filter(content__isnull=False)

        updated = 0
        scanned = 0
        limit = int(options["limit"])
        for article in qs:
            scanned += 1
            if limit > 0 and scanned > limit:
                break
            old_content = article.content or ""
            if len(old_content.strip()) >= min_len:
                continue

            image_url = article.thumbnail.url if article.thumbnail else ""
            article.summary = ensure_summary(article.title, article.summary)
            article.content = ensure_detailed_content(
                title=article.title,
                summary=article.summary,
                content=old_content,
                source_url=article.source_url,
                source_name=article.source_name,
                category_name=article.category.name if article.category else "",
                image_url=image_url,
                min_len=min_len,
            )
            article.save(update_fields=["summary", "content"])
            updated += 1

        self.stdout.write(self.style.SUCCESS(f"Enrich done. updated={updated}, scanned={scanned}"))

