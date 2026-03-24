from django.conf import settings
from django.test import Client

settings.ALLOWED_HOSTS = ["*"]

paths = [
    "/",
    "/about/",
    "/experts/",
    "/facilities/",
    "/faq/",
    "/partners/",
    "/visit-guide/",
    "/rehab/",
    "/rehab/co-xuong-khop/",
    "/rehab/chan-thuong-chinh-hinh/",
    "/rehab/than-kinh/",
    "/rehab/sau-tai-bien/",
    "/rehab/sau-phau-thuat/",
    "/exercise-library/",
    "/physical-therapy/",
    "/occupational-therapy/",
    "/speech-therapy/",
    "/services/",
    "/contact/",
    "/news/",
    "/news/category/tin-tuc-y-khoa/",
]

bad_tokens = ["Ã", "Ä", "Â", "Æ", "á»", "áº", "â€", "�"]

for lang in ("vi", "en"):
    c = Client()
    c.cookies["django_language"] = lang
    print(f"\n=== {lang.upper()} ===")
    for path in paths:
        r = c.get(path)
        html = r.content.decode("utf-8", errors="replace")
        bad = any(token in html for token in bad_tokens)
        print(path, r.status_code, "bad_tokens=", bad)
