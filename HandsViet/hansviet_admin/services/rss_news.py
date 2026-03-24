import html
import re
import ssl
import xml.etree.ElementTree as ET
from dataclasses import dataclass
from datetime import datetime
from email.utils import parsedate_to_datetime
from urllib.request import Request, urlopen


@dataclass
class RSSItem:
    title: str
    summary: str
    content: str
    source_url: str
    source_name: str
    image_url: str = ""
    published_at: datetime | None = None


def _fix_text(text: str) -> str:
    raw = html.unescape((text or "").strip())
    # Retry common mojibake conversion.
    for _ in range(2):
        if not any(tok in raw for tok in ("Ã", "Â", "Ä", "á»", "áº", "Æ°", "Æ¡", "â€", "â€“", "â€”", "�")):
            break
        try:
            candidate = raw.encode("latin1", errors="ignore").decode("utf-8", errors="ignore")
        except Exception:
            break
        if candidate and candidate != raw:
            raw = candidate
        else:
            break
    return re.sub(r"\s+", " ", raw).strip()


def _strip_html(text: str) -> str:
    if not text:
        return ""
    no_tags = re.sub(r"<[^>]+>", " ", text)
    return _fix_text(no_tags)


def _to_dt(value: str) -> datetime | None:
    raw = _fix_text(value)
    if not raw:
        return None
    try:
        return parsedate_to_datetime(raw)
    except Exception:
        pass
    for fmt in ("%Y-%m-%dT%H:%M:%SZ", "%Y-%m-%dT%H:%M:%S%z", "%Y-%m-%d %H:%M:%S"):
        try:
            return datetime.strptime(raw, fmt)
        except Exception:
            continue
    return None


def _find_first_text(node: ET.Element, names: list[str]) -> str:
    for name in names:
        elem = node.find(name)
        if elem is not None and elem.text:
            return _fix_text(elem.text)
    return ""


def _extract_image(item: ET.Element, description: str) -> str:
    enclosure = item.find("enclosure")
    if enclosure is not None:
        url = (enclosure.attrib.get("url") or "").strip()
        if url:
            return url

    media_content = item.find("{http://search.yahoo.com/mrss/}content")
    if media_content is not None:
        url = (media_content.attrib.get("url") or "").strip()
        if url:
            return url

    media_thumb = item.find("{http://search.yahoo.com/mrss/}thumbnail")
    if media_thumb is not None:
        url = (media_thumb.attrib.get("url") or "").strip()
        if url:
            return url

    match = re.search(r'<img[^>]+src=["\']([^"\']+)["\']', description or "", flags=re.IGNORECASE)
    return (match.group(1).strip() if match else "")


def fetch_rss_items(feed_url: str, source_name: str = "", max_items: int = 5) -> list[RSSItem]:
    req = Request(feed_url, headers={"User-Agent": "Mozilla/5.0 (HandsViet RSS Bot)"})
    try:
        with urlopen(req, timeout=45) as resp:
            xml_text = resp.read()
    except Exception as ex:
        # Fallback for local machines with SSL interception.
        if "certificate verify failed" not in str(ex).lower():
            raise
        insecure_ctx = ssl._create_unverified_context()
        with urlopen(req, timeout=45, context=insecure_ctx) as resp:
            xml_text = resp.read()

    root = ET.fromstring(xml_text)
    channel = root.find("channel")
    feed_title = _fix_text(source_name)
    if not feed_title and channel is not None:
        feed_title = _find_first_text(channel, ["title"])
    feed_title = feed_title or "RSS"

    nodes = []
    if channel is not None:
        nodes = channel.findall("item")
    if not nodes:
        nodes = root.findall("{http://www.w3.org/2005/Atom}entry")

    out: list[RSSItem] = []
    for node in nodes[: max(1, max_items)]:
        title = _find_first_text(node, ["title", "{http://www.w3.org/2005/Atom}title"])
        link = _find_first_text(node, ["link", "{http://www.w3.org/2005/Atom}link"])
        if not link:
            atom_link = node.find("{http://www.w3.org/2005/Atom}link")
            if atom_link is not None:
                link = (atom_link.attrib.get("href") or "").strip()

        desc_html = _find_first_text(
            node,
            [
                "description",
                "{http://purl.org/rss/1.0/modules/content/}encoded",
                "summary",
                "{http://www.w3.org/2005/Atom}summary",
            ],
        )
        summary = _strip_html(desc_html)[:1400]
        published_raw = _find_first_text(node, ["pubDate", "published", "{http://www.w3.org/2005/Atom}updated"])
        image_url = _extract_image(node, desc_html)

        if not title or not link:
            continue

        content = (
            f"<h2>{title}</h2>"
            f"<p>{summary}</p>"
            "<h3>Điểm chính cần lưu ý</h3>"
            "<ul>"
            "<li>Đây là thông tin tổng hợp nhanh từ nguồn RSS và cần được đối chiếu với bài gốc.</li>"
            "<li>Người đọc nên tham khảo tư vấn chuyên môn trước khi áp dụng cho tình trạng cá nhân.</li>"
            "<li>Ưu tiên nguồn chính thống và cập nhật mới nhất từ cơ quan y tế hoặc bệnh viện uy tín.</li>"
            "</ul>"
            "<h3>Nguồn tham khảo</h3>"
            f"<p>Bài viết được tổng hợp từ: <a href=\"{link}\" target=\"_blank\" rel=\"noopener noreferrer\">{feed_title}</a>.</p>"
        )
        if image_url:
            content = (
                f'<figure><img src="{image_url}" alt="{title}" />'
                f"<figcaption>Ảnh minh họa từ {feed_title}</figcaption></figure>\n\n"
                + content
            )

        out.append(
            RSSItem(
                title=title.strip(),
                summary=summary.strip(),
                content=content.strip(),
                source_url=link.strip(),
                source_name=feed_title,
                image_url=image_url,
                published_at=_to_dt(published_raw),
            )
        )

    return out
