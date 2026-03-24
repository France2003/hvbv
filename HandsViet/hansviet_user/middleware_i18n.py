import html
import json
import re
import unicodedata
from functools import lru_cache
from pathlib import Path

from django.conf import settings
from django.utils import translation
from django.utils.deprecation import MiddlewareMixin


class GlobalContentTranslationMiddleware(MiddlewareMixin):
    """
    Runtime i18n bridge for legacy templates.

    Rules:
    - Never touch URLs (`href/src/action`) so routing is unchanged.
    - Keep VI pages as source-of-truth; only apply runtime translation for EN.
    - Repair mojibake (UTF-8 decoded as cp1252/latin1) on all HTML responses.
    """

    DEFAULT_LANGUAGE = "en"
    SUPPORTED = {"en", "vi"}
    GENERATED_MAP_FILE = Path(settings.BASE_DIR) / "hansviet_user" / "i18n_generated_map.json"

    # Deterministic fallback map for core UI text.
    MANUAL_REPLACEMENTS = (
        ("Trang chủ", "Home"),
        ("Giới thiệu", "Introduce"),
        ("Về chúng tôi", "About us"),
        ("Lĩnh vực điều trị", "Treatment field"),
        ("Phương pháp trị liệu", "Treatment methods"),
        ("Tin tức", "News"),
        ("Dịch vụ", "Service"),
        ("Liên hệ", "Contact"),
        ("Đăng nhập", "Log in"),
        ("Đăng ký", "Register"),
        ("Đăng xuất", "Log out"),
        ("Thông tin người dùng", "User profile"),
        ("Quản lý chăm sóc", "Care management"),
        ("Đặt lịch khám", "Book appointment"),
        ("Xem thêm", "See more"),
        ("Xem dịch vụ", "Explore services"),
        ("Bài tập & Tờ khai", "Exercises & declarations"),
        ("Vật lý trị liệu", "Physical therapy"),
        ("Hoạt động trị liệu", "Therapeutic activities"),
        ("Ngôn ngữ trị liệu", "Speech therapy"),
        ("Tin tức Y khoa", "Medical News"),
        ("Câu chuyện khách hàng", "Customer stories"),
        ("Tin truyền thông", "Media news"),
        ("Tư vấn PHCN", "Rehabilitation consulting"),
        ("Khuyến mãi sự kiện", "Event promotion"),
        ("Mở menu", "Open menu"),
        ("Đóng menu", "Close menu"),
    )

    # Targeted cleanup phrases to avoid EN pages showing mixed VI/EN fragments.
    EN_FORCE_REPLACEMENTS = (
        ("Bệnh viện", "Hospital"),
        ("thăm khám", "medical examination"),
        ("đặt lịch khám", "book an appointment"),
        ("đặt lịch", "book an appointment"),
        ("gửi yêu cầu", "send request"),
        ("gửi tin nhắn", "send message"),
        ("họ và tên", "full name"),
        ("số điện thoại", "phone number"),
        ("lời nhắn", "message"),
        ("địa chỉ", "address"),
        ("giờ làm việc", "working hours"),
        ("liên hệ tư vấn", "consultation contact"),
        ("liên hệ với chúng tôi", "contact us"),
        ("tin nhắn khác", "another message"),
        ("đã nhận được tin nhắn", "message received"),
        ("câu hỏi thường gặp", "Frequently asked questions"),
        ("chi phí", "cost"),
        ("chính sách", "policy"),
        ("hỗ trợ khách hàng", "customer support"),
        ("quy trình", "process"),
        ("điều trị", "treatment"),
        ("đối tác chiến lược", "strategic partners"),
        ("đối tác", "partners"),
        ("sự kiện", "events"),
        ("bản tin", "newsletter"),
        ("mới cập nhật", "newly updated"),
        ("đã xuất bản", "published"),
        ("đọc tiếp", "read more"),
        ("trước", "previous"),
        ("thứ 2 - thứ 6", "Mon - Fri"),
        ("thứ 7 - CN", "Sat - Sun"),
        ("khẩn cấp", "Emergency"),
        ("nơi chia sẻ kiến thức", "A place to share knowledge"),
        ("câu chuyện truyền cảm hứng", "inspirational stories"),
        ("phục hồi chức năng", "rehabilitation"),
        ("lĩnh vực", "field"),
        ("thế mạnh", "strengths"),
        ("chứng chỉ", "certification"),
        ("kinh nghiệm", "experience"),
    )

    # Cleanup for no-diacritic Vietnamese fragments leaking from generated map values.
    EN_FORCE_ASCII_REPLACEMENTS = (
        ("physical therapy la gi", "What is Physical Therapy"),
        ("occupational therapy la gi", "What is Occupational Therapy"),
        ("speech therapy la gi", "What is Speech Therapy"),
        ("la gi", "what is it"),
        ("nhom benh thuong gap", "Common conditions"),
        ("can tap bao lau", "How long should I exercise"),
        ("sau mo bao lau thi tap", "How soon after surgery can I exercise"),
        ("dot quy lau nam co tap duoc khong", "Can long-term stroke patients still exercise"),
        ("gia dinh can lam gi", "What should family members do"),
        ("bao lau thay tien bo", "How long until progress is visible"),
        ("co tap tai nha duoc khong", "Can I exercise at home"),
        (
            "van co the cai thien neu tap dung muc tieu va duy tri deu dan",
            "Improvement is still possible with goal-based, consistent practice",
        ),
        (
            "co, nhung can duoc huong dan bai ban va theo doi dinh ky",
            "Yes, but you need structured guidance and periodic monitoring",
        ),
        ("yeu/liet nua nguoi", "Hemiparesis/Hemiplegia"),
        ("tap adl", "ADL training"),
        ("bai tap proprioception", "Proprioception exercises"),
        ("hoi chung ong co tay", "Carpal tunnel syndrome"),
        ("degeneration of the spine co/lung", "Degeneration of the cervical/lumbar spine"),
        (
            "dong hanh sau gay xuong, dut day chang, sports injury.",
            "Support after fractures, ligament tears, and sports injuries.",
        ),
        ("tap rom co kiem soat", "Controlled range-of-motion (ROM) training"),
        ("kham hau phau va sang loc nguy co", "Postoperative assessment and risk screening"),
        (
            "phoi hop gia dinh de duy tri tap luyen tai nha",
            "Coordinate with family to maintain home exercises",
        ),
    )
    ASCII_WORD_RE = re.compile(r"[a-z]+")
    ASCII_VI_WORDS = {
        "la",
        "mot",
        "nhung",
        "cua",
        "va",
        "trong",
        "cho",
        "ve",
        "voi",
        "tu",
        "khi",
        "de",
        "the",
        "nay",
        "do",
        "sau",
        "truoc",
        "tai",
        "nguoi",
        "benh",
        "nhan",
        "chuyen",
        "nganh",
        "y",
        "khoa",
        "su",
        "dung",
        "dong",
        "vai",
        "tro",
        "chu",
        "trinh",
        "toan",
        "dien",
        "mang",
        "lai",
        "thay",
        "doi",
        "tich",
        "cuc",
        "ca",
        "cau",
        "truc",
        "lan",
        "chuc",
        "nang",
        "giai",
        "phap",
        "can",
        "thiep",
        "phuong",
        "phap",
        "ky",
        "thuat",
        "vien",
        "huong",
        "dan",
        "doi",
        "ngu",
        "phuc",
        "hoi",
        "tri",
        "lieu",
        "hoat",
        "dong",
        "vat",
        "ly",
        "ngon",
        "ngu",
        "giam",
        "dau",
        "tang",
        "cuong",
        "kha",
        "nang",
        "tap",
        "luyen",
        "ket",
        "qua",
        "muc",
        "tieu",
        "tien",
        "trien",
        "cham",
        "soc",
        "suc",
        "khoe",
        "cam",
        "ket",
        "hieu",
        "qua",
        "phoi",
        "hop",
        "gia",
        "dinh",
        "bai",
        "ban",
        "dinh",
        "ky",
        "nhom",
        "benh",
        "thuong",
        "gap",
        "tap",
        "bao",
        "lau",
        "sau",
        "mo",
        "thi",
        "dot",
        "quy",
        "duoc",
        "khong",
        "gia",
        "dinh",
        "lam",
        "gi",
        "tai",
        "nha",
        "van",
        "the",
        "cai",
        "thien",
        "neu",
        "dung",
        "muc",
        "tieu",
        "duy",
        "tri",
        "deu",
        "dan",
        "yeu",
        "liet",
        "nua",
        "nguoi",
        "phoi",
        "hop",
        "huong",
        "dan",
        "bai",
        "ban",
        "phac",
        "do",
        "tien",
        "bo",
        "nhan",
    }
    ASCII_EN_WORDS = {
        "a",
        "an",
        "and",
        "are",
        "as",
        "at",
        "be",
        "by",
        "for",
        "from",
        "if",
        "in",
        "into",
        "is",
        "it",
        "of",
        "on",
        "or",
        "that",
        "the",
        "their",
        "them",
        "these",
        "they",
        "this",
        "to",
        "was",
        "we",
        "with",
        "you",
        "your",
    }

    SCRIPT_STYLE_RE = re.compile(
        r"(<script\b[^>]*>.*?</script>|<style\b[^>]*>.*?</style>)",
        re.IGNORECASE | re.DOTALL,
    )
    TEXT_NODE_RE = re.compile(r">(.*?)<", re.DOTALL)
    ATTR_DQ_RE = re.compile(r'(\b(?:title|placeholder|aria-label|alt|content)\s*=\s*")([^"]*?)(")', re.IGNORECASE)
    ATTR_SQ_RE = re.compile(r"(\b(?:title|placeholder|aria-label|alt|content)\s*=\s*')([^']*?)(')", re.IGNORECASE)
    WS_RE = re.compile(r"\s+")
    PUNCT_TRIM_CHARS = "\"'.,;:!?()[]{}…“”‘’"

    # Common mojibake markers when UTF-8 text was decoded as cp1252/latin1.
    # Include cp1252 punctuation + C1 controls because mixed-decode sequences often contain them.
    CP1252_PUNCT_RE = re.compile(
        r"[\u20AC\u201A\u0192\u201E\u2026\u2020\u2021\u02C6\u2030\u0160\u2039\u0152\u017D"
        r"\u2018\u2019\u201C\u201D\u2022\u2013\u2014\u02DC\u2122\u0161\u203A\u0153\u017E\u0178]"
    )
    CTRL_CHAR_RE = re.compile(r"[\u0080-\u009F]")
    MOJIBAKE_HINT_RE = re.compile(
        r"(?:[\u00C2-\u00C6\u00D0\u00D1\u00E2\u00E3]|"
        r"\u00E1[\u00BB\u00BA]|"
        r"\uFFFD|[\u0080-\u009F]|"
        r"[\u20AC\u201A\u0192\u201E\u2026\u2020\u2021\u02C6\u2030\u0160\u2039\u0152\u017D"
        r"\u2018\u2019\u201C\u201D\u2022\u2013\u2014\u02DC\u2122\u0161\u203A\u0153\u017E\u0178])"
    )
    VI_CHAR_RE = re.compile(
        r"[ăâđêôơưĂÂĐÊÔƠƯ"
        r"áàảãạấầẩẫậắằẳẵặ"
        r"éèẻẽẹếềểễệ"
        r"íìỉĩị"
        r"óòỏõọốồổỗộớờởỡợ"
        r"úùủũụứừửữự"
        r"ýỳỷỹỵ]"
    )

    _MAP_CACHE = {}
    _MAP_MTIME_NS = None
    _PATTERN_CACHE = ()
    _PATTERN_MTIME_NS = None

    @classmethod
    def _normalize_lang(cls, value):
        code = (value or "").lower()[:2]
        return code if code in cls.SUPPORTED else ""

    @classmethod
    def _normalize_segment(cls, value):
        cleaned = cls.WS_RE.sub(" ", html.unescape(value or "")).strip()
        return unicodedata.normalize("NFC", cleaned)

    @classmethod
    def _generated_map(cls):
        try:
            mtime_ns = cls.GENERATED_MAP_FILE.stat().st_mtime_ns
        except Exception:
            cls._MAP_CACHE = {}
            cls._MAP_MTIME_NS = None
            cls._PATTERN_CACHE = ()
            cls._PATTERN_MTIME_NS = None
            return {}

        if cls._MAP_MTIME_NS == mtime_ns and cls._MAP_CACHE:
            return cls._MAP_CACHE

        try:
            payload = json.loads(cls.GENERATED_MAP_FILE.read_text(encoding="utf-8"))
        except Exception:
            payload = {}

        if not isinstance(payload, dict):
            payload = {}

        out = {}
        for src, dst in payload.items():
            src_key = cls._normalize_segment(cls._fix_mojibake(src or ""))
            dst_text = cls._normalize_segment(cls._fix_mojibake(dst or ""))
            if src_key and dst_text:
                out[src_key] = dst_text

        cls._MAP_CACHE = out
        cls._MAP_MTIME_NS = mtime_ns
        cls._PATTERN_CACHE = ()
        cls._PATTERN_MTIME_NS = None
        return out

    @classmethod
    @lru_cache(maxsize=1)
    def _manual_patterns(cls):
        patterns = []
        for src, dst in sorted(cls.MANUAL_REPLACEMENTS, key=lambda pair: len(pair[0]), reverse=True):
            regex = re.escape(src).replace(r"\ ", r"\s+")
            patterns.append((re.compile(regex, re.IGNORECASE), dst))
        return tuple(patterns)

    @classmethod
    @lru_cache(maxsize=1)
    def _en_force_patterns(cls):
        patterns = []
        for src, dst in sorted(cls.EN_FORCE_REPLACEMENTS, key=lambda pair: len(pair[0]), reverse=True):
            regex = re.escape(src).replace(r"\ ", r"\s+")
            patterns.append((re.compile(regex, re.IGNORECASE), dst))
        return tuple(patterns)

    @classmethod
    @lru_cache(maxsize=1)
    def _en_force_ascii_patterns(cls):
        patterns = []
        for src, dst in sorted(cls.EN_FORCE_ASCII_REPLACEMENTS, key=lambda pair: len(pair[0]), reverse=True):
            regex = re.escape(src).replace(r"\ ", r"\s+")
            patterns.append((re.compile(regex, re.IGNORECASE), dst))
        return tuple(patterns)

    @classmethod
    def _generated_patterns(cls):
        _ = cls._generated_map()
        if cls._PATTERN_MTIME_NS == cls._MAP_MTIME_NS and cls._PATTERN_CACHE:
            return cls._PATTERN_CACHE

        patterns = []
        for src, dst in sorted(cls._MAP_CACHE.items(), key=lambda pair: len(pair[0]), reverse=True):
            regex = re.escape(src).replace(r"\ ", r"\s+")
            patterns.append((re.compile(regex, re.IGNORECASE), dst))

        cls._PATTERN_CACHE = tuple(patterns)
        cls._PATTERN_MTIME_NS = cls._MAP_MTIME_NS
        return cls._PATTERN_CACHE

    @classmethod
    def _strip_diacritics(cls, text):
        if not text:
            return text
        out = "".join(
            ch
            for ch in unicodedata.normalize("NFD", text)
            if unicodedata.category(ch) != "Mn"
        )
        return out.replace("đ", "d").replace("Đ", "D")

    @classmethod
    def _looks_like_ascii_vietnamese(cls, text):
        if not text:
            return False
        # Check de-accented text because generated values may already lose diacritics.
        candidate = cls._strip_diacritics(text).lower()
        words = cls.ASCII_WORD_RE.findall(candidate)
        if len(words) < 2:
            return False
        hits = sum(1 for word in words if word in cls.ASCII_VI_WORDS)
        english_hits = sum(1 for word in words if word in cls.ASCII_EN_WORDS)
        if english_hits >= 3 and english_hits > hits:
            return False
        if hits >= 3:
            return True
        return hits >= 2 and (hits / len(words)) >= 0.25


    @classmethod
    def _repair_score(cls, text):
        if not text:
            return 0
        vi_count = len(cls.VI_CHAR_RE.findall(text))
        mojibake_count = len(cls.MOJIBAKE_HINT_RE.findall(text))
        replacement_count = text.count("\ufffd")
        control_count = len(cls.CTRL_CHAR_RE.findall(text))
        cp1252_punct_count = len(cls.CP1252_PUNCT_RE.findall(text))
        return (
            (vi_count * 2)
            - (mojibake_count * 6)
            - (replacement_count * 20)
            - (control_count * 30)
            - (cp1252_punct_count * 4)
        )

    @classmethod
    @lru_cache(maxsize=1)
    def _cp1252_reverse_map(cls):
        reverse = {}
        for byte in range(0x80, 0xA0):
            try:
                char = bytes([byte]).decode("cp1252")
            except Exception:
                continue
            reverse[char] = byte
        return reverse

    @classmethod
    def _decode_mixed_bytes_once(cls, text):
        if not text:
            return text

        reverse_map = cls._cp1252_reverse_map()
        out = bytearray()
        for ch in text:
            codepoint = ord(ch)
            if codepoint <= 0xFF:
                out.append(codepoint)
                continue
            mapped = reverse_map.get(ch)
            if mapped is None:
                return text
            out.append(mapped)
        try:
            return out.decode("utf-8")
        except Exception:
            return text

    @classmethod
    def _decode_mojibake_once(cls, text):
        best = text
        best_score = cls._repair_score(text)
        for codec in ("latin1", "cp1252"):
            try:
                candidate = text.encode(codec).decode("utf-8")
            except Exception:
                continue
            score = cls._repair_score(candidate)
            if score > best_score:
                best = candidate
                best_score = score

        mixed_candidate = cls._decode_mixed_bytes_once(text)
        mixed_score = cls._repair_score(mixed_candidate)
        if mixed_score > best_score:
            best = mixed_candidate
            best_score = mixed_score
        return best

    @classmethod
    def _fix_mojibake(cls, text):

        if not text or not cls.MOJIBAKE_HINT_RE.search(text):
            return text

        def _fix_piece(piece):
            current = piece
            for _ in range(2):
                candidate = cls._decode_mojibake_once(current)
                if candidate == current:
                    break
                if cls._repair_score(candidate) <= cls._repair_score(current):
                    break
                current = candidate
                if not cls.MOJIBAKE_HINT_RE.search(current):
                    break

            # If punctuation is attached, decode the core then re-attach punctuation.
            if current == piece:
                start = 0
                end = len(current)
                while start < end and current[start] in cls.PUNCT_TRIM_CHARS:
                    start += 1
                while end > start and current[end - 1] in cls.PUNCT_TRIM_CHARS:
                    end -= 1
                if start or end < len(current):
                    core = current[start:end]
                    if core:
                        fixed_core = _fix_piece(core)
                        recomposed = current[:start] + fixed_core + current[end:]
                        if cls._repair_score(recomposed) > cls._repair_score(current):
                            current = recomposed
            return current

        # Decode by token first so mixed proper-vietnamese + mojibake segments can still recover.
        # Split only ASCII whitespace + punctuation separators. Keep NBSP in token because
        # mojibake bytes often include \u00A0.
        tokens = re.split(r"([ \t\r\n]+|[\"'.,;:!?()\[\]{}])", text)
        changed = False
        for idx, token in enumerate(tokens):
            if not token or token in {" ", "\t", "\r", "\n"} or not cls.MOJIBAKE_HINT_RE.search(token):
                continue
            fixed = _fix_piece(token)
            if fixed != token:
                tokens[idx] = fixed
                changed = True

        current = "".join(tokens) if changed else text

        # Final pass over the whole segment in case mojibake spans across token boundaries.
        current = _fix_piece(current)
        return current

    def _repair_segment(self, text):
        if not text:
            return text

        # Keep NBSP inside the core segment because mojibake bytes often include \u00A0.
        match = re.match(r"^([ \t\r\n]*)(.*?)([ \t\r\n]*)$", text, re.DOTALL)
        if not match:
            return self._fix_mojibake(text)
        prefix, core, suffix = match.groups()
        return f"{prefix}{self._fix_mojibake(core)}{suffix}"

    def _repair_visible_content(self, html_text):
        masked_blocks = []

        def _mask(match):
            masked_blocks.append(match.group(0))
            return f"__HV_BLOCK_{len(masked_blocks) - 1}__"

        masked = self.SCRIPT_STYLE_RE.sub(_mask, html_text)
        masked = self.TEXT_NODE_RE.sub(lambda m: ">" + self._repair_segment(m.group(1)) + "<", masked)
        masked = self.ATTR_DQ_RE.sub(
            lambda m: m.group(1) + self._repair_segment(m.group(2)) + m.group(3),
            masked,
        )
        masked = self.ATTR_SQ_RE.sub(
            lambda m: m.group(1) + self._repair_segment(m.group(2)) + m.group(3),
            masked,
        )

        for idx, block in enumerate(masked_blocks):
            masked = masked.replace(f"__HV_BLOCK_{idx}__", block)
        return masked

    def _finalize_english_segment(self, text):
        if not text:
            return text

        out = text
        for pattern, dst in self._en_force_patterns():
            out = pattern.sub(dst, out)

        if not self.VI_CHAR_RE.search(out) and not self._looks_like_ascii_vietnamese(out):
            return out

        stripped = self._strip_diacritics(out)
        for pattern, dst in self._en_force_ascii_patterns():
            stripped = pattern.sub(dst, stripped)

        if not self.VI_CHAR_RE.search(stripped) and not self._looks_like_ascii_vietnamese(stripped):
            return stripped

        return stripped or out

    def _translate_segment_to_en(self, text):
        if not text:
            return text

        # Keep NBSP inside the core segment because mojibake bytes often include \u00A0.
        match = re.match(r"^([ \t\r\n]*)(.*?)([ \t\r\n]*)$", text, re.DOTALL)
        if not match:
            return text
        prefix, core, suffix = match.groups()
        core_fixed = self._fix_mojibake(core)
        source_key = self._normalize_segment(core_fixed)
        if not source_key:
            return text

        auto_translated = self._generated_map().get(source_key)
        if auto_translated:
            return f"{prefix}{self._finalize_english_segment(auto_translated)}{suffix}"

        replaced = core_fixed

        # Generated map patterns first (longest-first), then deterministic manual patterns.
        for pattern, dst in self._generated_patterns():
            replaced = pattern.sub(dst, replaced)
        for pattern, dst in self._manual_patterns():
            replaced = pattern.sub(dst, replaced)

        return f"{prefix}{self._finalize_english_segment(replaced)}{suffix}"

    def _translate_visible_content_to_en(self, html_text):
        masked_blocks = []

        def _mask(match):
            masked_blocks.append(match.group(0))
            return f"__HV_BLOCK_{len(masked_blocks) - 1}__"

        masked = self.SCRIPT_STYLE_RE.sub(_mask, html_text)
        masked = self.TEXT_NODE_RE.sub(lambda m: ">" + self._translate_segment_to_en(m.group(1)) + "<", masked)
        masked = self.ATTR_DQ_RE.sub(
            lambda m: m.group(1) + self._translate_segment_to_en(m.group(2)) + m.group(3),
            masked,
        )
        masked = self.ATTR_SQ_RE.sub(
            lambda m: m.group(1) + self._translate_segment_to_en(m.group(2)) + m.group(3),
            masked,
        )

        for idx, block in enumerate(masked_blocks):
            masked = masked.replace(f"__HV_BLOCK_{idx}__", block)
        return masked

    def _pick_language(self, request):
        cookie_value = request.COOKIES.get(settings.LANGUAGE_COOKIE_NAME)
        return self._normalize_lang(cookie_value) or self.DEFAULT_LANGUAGE

    def process_request(self, request):
        lang = self._pick_language(request)
        translation.activate(lang)
        request.LANGUAGE_CODE = lang
        return None

    def process_response(self, request, response):
        current_lang = (
            self._normalize_lang(getattr(request, "LANGUAGE_CODE", ""))
            or self._normalize_lang(translation.get_language())
            or self.DEFAULT_LANGUAGE
        )

        lang_cookie = settings.LANGUAGE_COOKIE_NAME
        cookie_lang = self._normalize_lang(request.COOKIES.get(lang_cookie, ""))
        if (not cookie_lang or cookie_lang != current_lang) and lang_cookie not in response.cookies:
            response.set_cookie(
                lang_cookie,
                current_lang,
                max_age=settings.LANGUAGE_COOKIE_AGE,
                path=settings.LANGUAGE_COOKIE_PATH,
                domain=settings.LANGUAGE_COOKIE_DOMAIN,
                secure=settings.LANGUAGE_COOKIE_SECURE,
                httponly=settings.LANGUAGE_COOKIE_HTTPONLY,
                samesite=settings.LANGUAGE_COOKIE_SAMESITE,
            )

        content_type = (response.get("Content-Type") or "").lower()
        if "text/html" not in content_type:
            return response

        try:
            html_text = response.content.decode("utf-8")
        except Exception:
            return response

        if getattr(request, "path", "").startswith("/handsviet_admin/"):
            repaired_html = self._repair_visible_content(html_text)
            response.content = repaired_html.encode("utf-8")
            if response.has_header("Content-Length"):
                response["Content-Length"] = str(len(response.content))
            return response

        repaired_html = self._repair_visible_content(html_text)
        if current_lang == "en":
            output = self._translate_visible_content_to_en(repaired_html)
        else:
            output = repaired_html

        response.content = output.encode("utf-8")
        if response.has_header("Content-Length"):
            response["Content-Length"] = str(len(response.content))
        return response
