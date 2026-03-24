import time

from django.core.management import call_command
from django.core.management.base import BaseCommand
from django.utils import timezone


class Command(BaseCommand):
    help = "Run news sync in a loop (realtime-like), default every 60 seconds."

    def add_arguments(self, parser):
        parser.add_argument("--interval", type=int, default=60, help="Seconds between sync runs.")
        parser.add_argument("--max-items", type=int, default=3, help="Max items per category each run.")
        parser.add_argument(
            "--category",
            action="append",
            dest="categories",
            help="Category slug to sync. Can pass multiple times.",
        )
        parser.add_argument("--publish", action="store_true", help="Publish immediately.")
        parser.add_argument("--model", type=str, default="", help="Override model, e.g. gpt-4o-mini.")
        parser.add_argument("--iterations", type=int, default=0, help="0 = run forever; >0 = number of loops.")

    def handle(self, *args, **options):
        interval = max(10, int(options["interval"]))
        iterations = int(options["iterations"])
        count = 0

        self.stdout.write(
            self.style.SUCCESS(
                f"Auto sync started at {timezone.now()}, interval={interval}s, iterations={iterations or 'infinite'}"
            )
        )

        while True:
            count += 1
            self.stdout.write(self.style.WARNING(f"[{count}] Sync started at {timezone.now()}"))

            kwargs = {
                "max_items": options["max_items"],
                "publish": bool(options.get("publish")),
            }
            if options.get("categories"):
                kwargs["categories"] = options["categories"]
            if (options.get("model") or "").strip():
                kwargs["model"] = options["model"].strip()

            call_command("sync_medical_news", **kwargs)
            self.stdout.write(self.style.SUCCESS(f"[{count}] Sync finished at {timezone.now()}"))

            if iterations > 0 and count >= iterations:
                break
            time.sleep(interval)

        self.stdout.write(self.style.SUCCESS("Auto sync stopped."))

