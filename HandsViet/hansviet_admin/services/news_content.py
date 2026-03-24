import re


def clean_text(text: str) -> str:
    return re.sub(r"\s+", " ", (text or "").strip())


def _word_count(text: str) -> int:
    return len(re.findall(r"\w+", text or "", flags=re.UNICODE))


def _strip_html(text: str) -> str:
    no_tags = re.sub(r"<[^>]+>", " ", text or "")
    return clean_text(no_tags)


def _normalize_lang(lang: str) -> str:
    return "en" if str(lang or "").lower().startswith("en") else "vi"


def ensure_summary(
    title: str,
    summary: str,
    min_len: int = 260,
    min_words: int = 55,
    lang: str = "vi",
) -> str:
    s = clean_text(summary)
    if len(s) >= min_len and _word_count(s) >= min_words:
        return s

    active_lang = _normalize_lang(lang)
    if active_lang == "en":
        fallback = (
            f"{title}. {s} "
            "This article is edited in a practical format for general readers, "
            "highlighting clinical context, warning signs, risk groups, and safe care pathways. "
            "It also clarifies when to seek medical attention, how to coordinate with clinicians, "
            "and how rehabilitation planning can reduce long-term complications."
        )
    else:
        fallback = (
            f"{title}. {s} "
            "Bai viet nay duoc bien tap theo huong thuc hanh cho nguoi doc Viet Nam, "
            "lam ro boi canh benh ly, dau hieu can theo doi, nhom nguy co va cac buoc xu tri phu hop. "
            "Noi dung cung nhan manh thoi diem can di kham, cach phoi hop cung bac si dieu tri, "
            "vai tro cua phuc hoi chuc nang va cac luu y de han che bien chung trong sinh hoat hang ngay."
        )
    return clean_text(fallback)


def ensure_detailed_content(
    title: str,
    summary: str,
    content: str,
    source_url: str = "",
    source_name: str = "",
    category_name: str = "",
    image_url: str = "",
    min_len: int = 2500,
    min_words: int = 420,
    lang: str = "vi",
) -> str:
    active_lang = _normalize_lang(lang)

    base = (content or "").strip()
    if image_url and "<img" not in base.lower():
        caption = (
            "Illustration image from a referenced source"
            if active_lang == "en"
            else "Anh minh hoa tu nguon tham khao"
        )
        base = (
            f'<figure><img src="{image_url}" alt="{title}" />'
            f"<figcaption>{caption}</figcaption></figure>\n\n"
            + base
        )

    normalized_base = _strip_html(base)
    if len(normalized_base) >= min_len and _word_count(normalized_base) >= min_words:
        return base

    category_label = category_name or ("Medical News" if active_lang == "en" else "Tin tuc Y khoa")
    source_label = source_name or ("Reference source" if active_lang == "en" else "Nguon tham khao")
    source_link = (
        f'<a href="{source_url}" target="_blank" rel="noopener noreferrer">{source_label}</a>'
        if source_url
        else source_label
    )
    summary_text = ensure_summary(title, summary, lang=active_lang)

    if active_lang == "en":
        appendix_sections = [
            "<h2>Overview</h2>"
            f"<p>{summary_text}</p>"
            f"<p>This article belongs to <strong>{category_label}</strong> and prioritizes clarity, "
            "clinical safety, and practical guidance that readers can apply in daily care decisions.</p>",
            "<h2>Key signs and risk groups</h2>"
            "<ul>"
            "<li>Track persistent, recurrent, or worsening symptoms over time.</li>"
            "<li>Consider age, comorbidities, mobility level, sleep quality, and nutrition status.</li>"
            "<li>Review work and lifestyle factors that may aggravate symptoms.</li>"
            "</ul>",
            "<h2>Initial management direction</h2>"
            "<p>Avoid prolonged self-medication without professional guidance. "
            "If symptoms affect daily activities, seek clinical evaluation early to confirm causes and set an appropriate treatment plan.</p>"
            "<p>During recovery, maintain suitable physical activity, monitor treatment response, and attend follow-up visits to adjust the plan as needed.</p>",
            "<h2>Practical recommendations</h2>"
            "<ul>"
            "<li>Keep a simple symptom timeline to support clinical consultations.</li>"
            "<li>Prioritize healthy routines: adequate sleep, balanced nutrition, and stress control.</li>"
            "<li>Follow rehabilitation and home-safety instructions consistently.</li>"
            "<li>Ask clinicians to clarify any unclear treatment steps.</li>"
            "</ul>",
            "<h2>Clinical note</h2>"
            "<p>This content is for educational reference and does not replace direct diagnosis. "
            "All treatment decisions should be based on in-person assessment by qualified clinicians.</p>",
            f"<h2>References</h2><p>{source_link}</p>",
        ]
        extra_block = (
            "<h2>Extended analysis</h2>"
            f"<p>{summary_text}</p>"
            "<p>From a prevention perspective, readers should maintain regular health monitoring, "
            "recognize warning signs early, and discuss changes in medication or activity intensity with clinicians. "
            "Combining medical treatment with structured rehabilitation often improves long-term outcomes.</p>"
        )
    else:
        appendix_sections = [
            "<h2>Tong quan van de</h2>"
            f"<p>{summary_text}</p>"
            f"<p>Noi dung thuoc chuyen muc <strong>{category_label}</strong>, uu tien tinh chinh xac, "
            "de hieu va co the ap dung trong cham soc suc khoe hang ngay.</p>",
            "<h2>Dau hieu nhan biet va nhom nguy co</h2>"
            "<ul>"
            "<li>Theo doi dau hieu xuat hien keo dai, tai phat hoac tang dan muc do.</li>"
            "<li>Luu y benh nen, tuoi tac, muc do van dong, giac ngu va dinh duong.</li>"
            "<li>Danh gia yeu to nghe nghiep va thoi quen sinh hoat co the lam trieu chung nang hon.</li>"
            "</ul>",
            "<h2>Dinh huong xu tri ban dau</h2>"
            "<p>Khong tu y dung thuoc keo dai khi chua co chi dinh chuyen mon. "
            "Neu trieu chung anh huong sinh hoat, can kham som de duoc danh gia nguyen nhan va lap ke hoach dieu tri phu hop.</p>"
            "<p>Trong giai doan phuc hoi, nen duy tri van dong phu hop, theo doi dap ung dieu tri, "
            "va tai kham dinh ky de dieu chinh phac do khi can.</p>",
            "<h2>Khuyen nghi thuc hanh cho nguoi benh va gia dinh</h2>"
            "<ul>"
            "<li>Ghi lai trieu chung theo moc thoi gian de cung cap cho bac si.</li>"
            "<li>Uu tien loi song lanh manh: ngu du, an can bang, tranh cang thang keo dai.</li>"
            "<li>Tuan thu lich tap phuc hoi chuc nang va huong dan an toan tai nha.</li>"
            "<li>Chu dong hoi lai nhan vien y te khi chua ro ke hoach dieu tri.</li>"
            "</ul>",
            "<h2>Luu y chuyen mon</h2>"
            "<p>Thong tin trong bai co gia tri tham khao va khong thay the chan doan truc tiep. "
            "Moi quyet dinh dieu tri can dua tren tham kham thuc te va chi dinh cua bac si.</p>",
            f"<h2>Nguon tham khao</h2><p>{source_link}</p>",
        ]
        extra_block = (
            "<h2>Phan tich mo rong</h2>"
            f"<p>{summary_text}</p>"
            "<p>O goc do phong ngua, nguoi doc nen duy tri theo doi suc khoe dinh ky, "
            "nhan dien som dau hieu bat thuong va trao doi voi bac si truoc khi thay doi thuoc hoac cuong do van dong. "
            "Viec phoi hop giua dieu tri y khoa va phuc hoi chuc nang thuong giup cai thien ket qua dai han.</p>"
        )

    assembled = (base + "\n\n" + "\n\n".join(appendix_sections)).strip() if base else "\n\n".join(appendix_sections)

    for _ in range(6):
        normalized = _strip_html(assembled)
        if len(normalized) >= min_len and _word_count(normalized) >= min_words:
            break
        assembled = f"{assembled}\n\n{extra_block}".strip()

    return assembled
