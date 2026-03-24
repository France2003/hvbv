import json
from dataclasses import dataclass
from datetime import datetime
from urllib.error import HTTPError, URLError
from urllib.parse import urljoin
from urllib.request import Request, urlopen

from django.conf import settings
from django.utils.text import slugify

from hansviet_admin.services.news_content import ensure_detailed_content, ensure_summary


@dataclass
class NewsItem:
    title: str
    summary: str
    content: str
    source_url: str
    source_name: str
    image_url: str = ""
    published_at: datetime | None = None


SYSTEM_PROMPT = (
    "You are a medical news editor writing for a healthcare website. "
    "Return only natural English and valid JSON. "
    "Each item needs practical summary and detailed content. "
    "summary: 80-180 words. "
    "content: 900-1600 words using simple HTML (h2, h3, p, ul, li). "
    "Schema: {\"items\":[{\"title\":\"\",\"summary\":\"\",\"content\":\"\",\"source_url\":\"\",\"source_name\":\"\",\"image_url\":\"\",\"published_at\":\"YYYY-MM-DDTHH:MM:SSZ\"}]}"
)


def _normalize_lang(lang: str) -> str:
    return "en" if str(lang or "").lower().startswith("en") else "vi"


def _build_user_prompt(category_name: str, max_items: int) -> str:
    return (
        f"Collect up to {max_items} recent and relevant items for category '{category_name}'. "
        "Use reliable medical sources and keep references clear."
    )


def _parse_json_from_text(raw_text: str) -> dict:
    return json.loads((raw_text or "").strip())


def _looks_vietnamese(text: str) -> bool:
    lowered = f" {(text or '').lower()} "
    markers = [
        " benh ",
        " dieu tri ",
        " phuc hoi ",
        " suc khoe ",
        " bac si ",
        " nguoi benh ",
        " benh nhan ",
        " trieu chung ",
        " chuan doan ",
        " va ",
        " cua ",
    ]
    return sum(1 for marker in markers if marker in lowered) >= 3


def _ensure_item_length(item: dict, lang: str) -> dict:
    active_lang = _normalize_lang(lang)

    title = (item.get("title") or "").strip()
    source_url = (item.get("source_url") or "").strip()
    source_name = (item.get("source_name") or "").strip()
    image_url = (item.get("image_url") or "").strip()

    summary = ensure_summary(
        title=title,
        summary=(item.get("summary") or ""),
        min_len=280,
        min_words=55,
        lang=active_lang,
    )
    content = ensure_detailed_content(
        title=title,
        summary=summary,
        content=(item.get("content") or ""),
        source_url=source_url,
        source_name=source_name,
        image_url=image_url,
        min_len=2200,
        min_words=360,
        lang=active_lang,
    )

    item["title"] = title
    item["summary"] = summary
    item["content"] = content
    item["source_url"] = source_url
    item["source_name"] = source_name
    item["image_url"] = image_url
    return item


def _translate_news_payload(item: dict, target_language: str) -> dict:
    active_lang = _normalize_lang(target_language)
    language_name = "English" if active_lang == "en" else "Vietnamese"

    source_payload = {
        "title": (item.get("title") or "").strip(),
        "summary": (item.get("summary") or "").strip(),
        "content": (item.get("content") or "").strip(),
        "source_url": (item.get("source_url") or "").strip(),
        "source_name": (item.get("source_name") or "").strip(),
        "image_url": (item.get("image_url") or "").strip(),
        "published_at": (item.get("published_at") or "").strip(),
    }

    prompt = (
        f"Rewrite and translate this medical news object into natural {language_name}. "
        "Return JSON only with the same keys. "
        "Keep source_url, source_name, image_url, and published_at unchanged. "
        "summary: 80-180 words. content: 900-1600 words with simple HTML. "
        "Object: "
        + json.dumps(source_payload, ensure_ascii=False)
    )

    response = _post_chat(
        [
            {
                "role": "system",
                "content": "You are a medical editor and translator. Return valid JSON only.",
            },
            {"role": "user", "content": prompt},
        ]
    )
    content = response["choices"][0]["message"]["content"]
    parsed = _parse_json_from_text(content)

    parsed["source_url"] = source_payload["source_url"]
    parsed["source_name"] = source_payload["source_name"]
    parsed["image_url"] = source_payload["image_url"]
    parsed["published_at"] = source_payload["published_at"]
    return _ensure_item_length(parsed, active_lang)


def translate_news_item(item: dict | NewsItem, target_language: str, category_name: str = "") -> dict:
    payload = {
        "title": item.title if isinstance(item, NewsItem) else (item.get("title") or ""),
        "summary": item.summary if isinstance(item, NewsItem) else (item.get("summary") or ""),
        "content": item.content if isinstance(item, NewsItem) else (item.get("content") or ""),
        "source_url": item.source_url if isinstance(item, NewsItem) else (item.get("source_url") or ""),
        "source_name": item.source_name if isinstance(item, NewsItem) else (item.get("source_name") or ""),
        "image_url": item.image_url if isinstance(item, NewsItem) else (item.get("image_url") or ""),
        "published_at": (
            item.published_at.isoformat() if isinstance(item, NewsItem) and item.published_at else item.get("published_at") or ""
        ),
    }
    _ = category_name  # kept for backward-compatible signature
    return _translate_news_payload(payload, target_language=target_language)


def _post_chat(messages: list[dict]) -> dict:
    if not settings.PPLX_API_KEY:
        raise RuntimeError("Missing PPLX_API_KEY in environment/settings.")

    payload = {
        "model": settings.PPLX_MODEL,
        "temperature": 0.2,
        "messages": messages,
    }
    base = settings.PPLX_BASE_URL.rstrip("/") + "/"
    candidate_paths = [
        "v1/chat/completions",
        "chat/completions",
        "api/v1/chat/completions",
        "openai/v1/chat/completions",
    ]
    last_error = None
    for path in candidate_paths:
        endpoint = urljoin(base, path)
        req = Request(
            endpoint,
            data=json.dumps(payload).encode("utf-8"),
            headers={
                "Content-Type": "application/json",
                "Authorization": f"Bearer {settings.PPLX_API_KEY}",
            },
            method="POST",
        )
        try:
            with urlopen(req, timeout=settings.PPLX_TIMEOUT) as resp:
                raw = resp.read().decode("utf-8")
                return json.loads(raw)
        except HTTPError as ex:
            last_error = RuntimeError(f"{endpoint} HTTPError {ex.code}: {ex.reason}")
        except URLError as ex:
            last_error = RuntimeError(f"{endpoint} URLError: {ex.reason}")
        except json.JSONDecodeError as ex:
            last_error = RuntimeError(f"{endpoint} returned invalid JSON: {ex}")

    if last_error:
        raise last_error
    raise RuntimeError("Unable to reach API endpoint.")


def fetch_category_news(category_name: str, max_items: int = 5) -> list[NewsItem]:
    response = _post_chat(
        [
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user", "content": _build_user_prompt(category_name, max_items)},
        ]
    )
    content = response["choices"][0]["message"]["content"]
    parsed = _parse_json_from_text(content)

    items: list[NewsItem] = []
    for row in parsed.get("items", []):
        row = _ensure_item_length(row, lang="en")
        joined = " ".join(
            [
                str(row.get("title", "")),
                str(row.get("summary", "")),
                str(row.get("content", "")),
            ]
        )
        if _looks_vietnamese(joined):
            try:
                row = _translate_news_payload(row, target_language="en")
            except Exception:
                pass

        title = (row.get("title") or "").strip()
        if not title:
            continue

        published_at = None
        published_at_raw = (row.get("published_at") or "").strip()
        if published_at_raw:
            try:
                published_at = datetime.fromisoformat(published_at_raw.replace("Z", "+00:00"))
            except ValueError:
                published_at = None

        items.append(
            NewsItem(
                title=title,
                summary=(row.get("summary") or "").strip(),
                content=(row.get("content") or "").strip(),
                source_url=(row.get("source_url") or "").strip(),
                source_name=(row.get("source_name") or "").strip(),
                image_url=(row.get("image_url") or "").strip(),
                published_at=published_at,
            )
        )
    return items


def unique_article_slug(title: str, exists_fn) -> str:
    base = slugify(title) or "medical-news"
    slug = base
    i = 2
    while exists_fn(slug):
        slug = f"{base}-{i}"
        i += 1
    return slug
