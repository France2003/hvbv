import time

from django.core.management import call_command
from django.core.management.base import BaseCommand
from django.utils import timezone


class Command(BaseCommand):
    help = "Run RSS sync in a loop, default every 60 seconds."

    def add_arguments(self, parser):
        parser.add_argument("--interval", type=int, default=60, help="Seconds between sync runs.")
        parser.add_argument("--max-items", type=int, default=2, help="Max items per RSS feed each run.")
        parser.add_argument("--publish", action="store_true", help="Publish immediately.")
        parser.add_argument("--balanced", action="store_true", help="Spread unclear topics across categories.")
        parser.add_argument("--fallback-category", type=str, default="tin-tuc-y-khoa", help="Fallback category slug.")
        parser.add_argument("--iterations", type=int, default=0, help="0=forever; >0=number of loops.")

    def handle(self, *args, **options):
        interval = max(10, int(options["interval"]))
        iterations = int(options["iterations"])
        count = 0
        self.stdout.write(
            self.style.SUCCESS(
                f"RSS auto sync started at {timezone.now()}, interval={interval}s, iterations={iterations or 'infinite'}"
            )
        )
        while True:
            count += 1
            self.stdout.write(self.style.WARNING(f"[{count}] RSS sync started at {timezone.now()}"))
            call_command(
                "sync_rss_news",
                max_items=options["max_items"],
                publish=bool(options.get("publish")),
                balanced=bool(options.get("balanced")),
                fallback_category=(options.get("fallback_category") or "tin-tuc-y-khoa"),
            )
            self.stdout.write(self.style.SUCCESS(f"[{count}] RSS sync finished at {timezone.now()}"))
            if iterations > 0 and count >= iterations:
                break
            time.sleep(interval)
        self.stdout.write(self.style.SUCCESS("RSS auto sync stopped."))
