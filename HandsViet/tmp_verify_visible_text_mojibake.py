import html
import re
from django.conf import settings
from django.test import Client

settings.ALLOWED_HOSTS = ["*"]

paths = [
    "/",
    "/experts/",
    "/rehab/co-xuong-khop/",
    "/rehab/chan-thuong-chinh-hinh/",
    "/rehab/than-kinh/",
    "/rehab/sau-tai-bien/",
    "/rehab/sau-phau-thuat/",
    "/physical-therapy/",
    "/speech-therapy/",
]

bad_tokens = ["Ã", "Ä", "Â", "Æ", "á»", "áº", "â€", "�"]


def visible_text(html_text):
    html_text = re.sub(r"<script\b[^>]*>[\s\S]*?</script>", " ", html_text, flags=re.I)
    html_text = re.sub(r"<style\b[^>]*>[\s\S]*?</style>", " ", html_text, flags=re.I)
    html_text = re.sub(r"<[^>]+>", "\n", html_text)
    html_text = html.unescape(html_text)
    lines = [re.sub(r"\s+", " ", line).strip() for line in html_text.splitlines()]
    return [line for line in lines if line]


for lang in ("vi", "en"):
    c = Client()
    c.cookies["django_language"] = lang
    print(f"\n=== {lang.upper()} ===")
    for path in paths:
        r = c.get(path)
        chunks = visible_text(r.content.decode("utf-8", errors="replace"))
        bad_lines = [line for line in chunks if any(token in line for token in bad_tokens)]
        print(path, r.status_code, "bad_lines=", len(bad_lines))
        if bad_lines:
            print("  sample:", bad_lines[0].encode("unicode_escape").decode("ascii"))
