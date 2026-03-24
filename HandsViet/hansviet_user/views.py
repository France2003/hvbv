import uuid
import re
import json
import hashlib
import logging
import unicodedata
from difflib import SequenceMatcher
from decimal import Decimal, InvalidOperation
from datetime import timedelta
from datetime import datetime
from urllib.parse import parse_qs, quote, urlparse

from django.conf import settings
from django.contrib import messages
from django.contrib.auth import authenticate, login, logout
from django.contrib.auth.forms import AuthenticationForm
from django.contrib.auth.models import User
from django.shortcuts import get_object_or_404, redirect, render
from django.utils import timezone
from django.utils.translation import get_language
from django.http import Http404, HttpResponse, JsonResponse
from django.db.models import F, Q
from django.core.paginator import Paginator
from django.core.mail import send_mail
from django.urls import reverse

from django.views.decorators.csrf import csrf_exempt
from hansviet_admin.models import (
    ExerciseLog,
    ExerciseProfile,
    Lead,
    NewsArticle,
    NewsCategory,
    Package,
    PatientProfile,
    ProgressNote,
    Purchase,
    Service,
    ServiceCategory,
    SessionSchedule,
    Transaction,
    Video,
)
from hansviet_admin.service_category_meta import (
    SERVICE_CATEGORY_LABELS,
    sync_service_categories,
)
from hansviet_admin.news_category_meta import (
    get_news_category_label,
    sync_news_categories,
)
from .forms import LeadForm
from .middleware_i18n import GlobalContentTranslationMiddleware

NEWS_HERO_DESCRIPTIONS = {
    "tin-tuc-y-khoa": {
        "vi": "Cáº­p nháº­t kiáº¿n thá»©c y khoa, xu hÆ°á»›ng Ä‘iá»u trá»‹ vÃ  cÃ¡c nghiÃªn cá»©u há»¯u Ã­ch cho phá»¥c há»“i chá»©c nÄƒng.",
        "en": "Updates on medical knowledge, treatment trends, and useful rehabilitation research.",
    },
    "cau-chuyen-khach-hang": {
        "vi": "Nhá»¯ng cÃ¢u chuyá»‡n phá»¥c há»“i thá»±c táº¿ tá»« bá»‡nh nhÃ¢n vÃ  gia Ä‘Ã¬nh, truyá»n cáº£m há»©ng má»—i ngÃ y.",
        "en": "Real recovery stories from patients and families, bringing daily inspiration.",
    },
    "tin-truyen-thong": {
        "vi": "ThÃ´ng tin bÃ¡o chÃ­, hoáº¡t Ä‘á»™ng truyá»n thÃ´ng vÃ  cÃ¡c dáº¥u má»‘c ná»•i báº­t cá»§a HandsViet.",
        "en": "Press coverage, media activities, and important milestones of HandsViet.",
    },
    "tu-van-phcn": {
        "vi": "GÃ³c tÆ° váº¥n chuyÃªn mÃ´n vá» phá»¥c há»“i chá»©c nÄƒng: triá»‡u chá»©ng, lá»™ trÃ¬nh vÃ  cÃ¡ch chÄƒm sÃ³c Ä‘Ãºng.",
        "en": "Professional rehabilitation guidance on symptoms, treatment plans, and proper care.",
    },
    "khuyen-mai-su-kien": {
        "vi": "ThÃ´ng bÃ¡o Æ°u Ä‘Ã£i, workshop, sá»± kiá»‡n cá»™ng Ä‘á»“ng vÃ  chÆ°Æ¡ng trÃ¬nh Ä‘á»“ng hÃ nh cÃ¹ng ngÆ°á»i bá»‡nh.",
        "en": "Updates on promotions, workshops, community events, and patient support programs.",
    },
}

SERVICE_CYCLE_META = {
    "week": {"rank": 0, "label": {"vi": "tuáº§n", "en": "week"}, "group": {"vi": "GÃ³i theo tuáº§n", "en": "Weekly packages"}},
    "month": {"rank": 1, "label": {"vi": "thÃ¡ng", "en": "month"}, "group": {"vi": "GÃ³i theo thÃ¡ng", "en": "Monthly packages"}},
    "year": {"rank": 2, "label": {"vi": "nÄƒm", "en": "year"}, "group": {"vi": "GÃ³i theo nÄƒm", "en": "Yearly packages"}},
    "other": {"rank": 3, "label": {"vi": "", "en": ""}, "group": {"vi": "GÃ³i khÃ¡c", "en": "Other packages"}},
}

PAYMENT_TIMEOUT_SECONDS = 180
PAYMENT_REF_PATTERN = re.compile(r"(HV[A-Z0-9]{10,})")
VIDEO_ACCESS_LABELS = {
    Video.ACCESS_FREE: {"vi": "Miá»…n phÃ­", "en": "Free"},
    Video.ACCESS_PAID: {"vi": "Tráº£ phÃ­", "en": "Paid"},
}
BOOKING_SPECIALTY_LABELS = {
    "xuong-khop": {"vi": "PHCN Cơ xương khớp", "en": "Musculoskeletal Rehabilitation"},
    "chan-thuong": {"vi": "PHCN Chấn thương", "en": "Trauma Rehabilitation"},
    "than-kinh": {"vi": "PHCN Thần kinh", "en": "Neurological Rehabilitation"},
    "nhi-khoa": {"vi": "PHCN Nhi khoa", "en": "Pediatric Rehabilitation"},
}
BOOKING_SERVICE_LABELS = {
    "bai-tap": {"vi": "Bài tập trị liệu", "en": "Therapeutic Exercise"},
    "vat-ly": {"vi": "Vật lý trị liệu", "en": "Physical Therapy"},
    "hoat-dong": {"vi": "Hoạt động trị liệu", "en": "Occupational Therapy"},
    "ngon-ngu": {"vi": "Ngôn ngữ trị liệu", "en": "Speech Therapy"},
}

logger = logging.getLogger(__name__)
EN_NEWS_PLACEHOLDER = "__HV_EN_PLACEHOLDER__"
LEGACY_EN_PLACEHOLDERS = {
    "this section is shown in english.",
    "english content is being updated.",
}
EN_NEWS_TITLE_FALLBACK = "Medical update"
EN_NEWS_SUMMARY_FALLBACK = (
    "Latest medical insights and practical guidance from the HandsViet content team."
)
VI_CHAR_HINT_RE = re.compile(r"[ÄƒÃ¢Ä‘ÃªÃ´Æ¡Æ°Ä‚Ã‚ÄÃŠÃ”Æ Æ¯Ã¡Ã áº£Ã£áº¡áº¥áº§áº©áº«áº­áº¯áº±áº³áºµáº·Ã©Ã¨áº»áº½áº¹áº¿á»á»ƒá»…á»‡Ã­Ã¬á»‰Ä©á»‹Ã³Ã²á»Ãµá»á»‘á»“á»•á»—á»™á»›á»á»Ÿá»¡á»£ÃºÃ¹á»§Å©á»¥á»©á»«á»­á»¯á»±Ã½á»³á»·á»¹á»µ]")
NEWS_ASCII_VI_HINTS = {
    "benh", "vien", "chinh", "thuc", "ra", "mat", "trung", "tam", "phau", "thuat",
    "chi", "vai", "phut", "buoi", "sang", "viec", "giup", "giam", "nguy", "co",
    "thua", "can", "beo", "phi", "tre", "em", "thang", "suc", "khoe", "nguoi",
    "y", "te", "thanh", "pho", "khuyen", "mai", "su", "kien", "cau", "chuyen",
    "khach", "hang", "tu", "van", "tim", "mach", "dong", "hanh", "gay", "xuong",
    "dot", "quy", "lai", "xe", "lam", "viec", "doi", "khoa", "ngot", "do", "an",
}
_RUNTIME_I18N_TRANSLATOR = None

REHAB_FIELD_DETAILS = {
    "co-xuong-khop": {
        "title": "PhÃ¡Â»Â¥c hÃ¡Â»â€œi cÃ†Â¡ xÃ†Â°Ã†Â¡ng khÃ¡Â»â€ºp",
        "subtitle": "DÃƒÂ nh cho thoÃƒÂ¡i hÃƒÂ³a khÃ¡Â»â€ºp, Ã„â€˜au cÃ¡Â»â„¢t sÃ¡Â»â€˜ng, viÃƒÂªm quanh khÃ¡Â»â€ºp, hÃ¡Â»â„¢i chÃ¡Â»Â©ng quÃƒÂ¡ tÃ¡ÂºÂ£i vÃ¡ÂºÂ­n Ã„â€˜Ã¡Â»â„¢ng.",
        "image": "/static/images/team/doctor_new_1.jpg",
        "overview": "LÃ„Â©nh vÃ¡Â»Â±c phÃ¡Â»Â¥c hÃ¡Â»â€œi cÃ†Â¡ xÃ†Â°Ã†Â¡ng khÃ¡Â»â€ºp tÃ¡ÂºÂ¡i HandsViet tÃ¡ÂºÂ­p trung vÃƒÂ o giÃ¡ÂºÂ£m Ã„â€˜au, phÃ¡Â»Â¥c hÃ¡Â»â€œi tÃ¡ÂºÂ§m vÃ¡ÂºÂ­n Ã„â€˜Ã¡Â»â„¢ng vÃƒÂ  nÃƒÂ¢ng cao chÃ¡ÂºÂ¥t lÃ†Â°Ã¡Â»Â£ng sinh hoÃ¡ÂºÂ¡t. ChÃ†Â°Ã†Â¡ng trÃƒÂ¬nh Ã„â€˜Ã†Â°Ã¡Â»Â£c xÃƒÂ¢y dÃ¡Â»Â±ng theo mÃ¡Â»Â©c Ã„â€˜Ã¡Â»â„¢ tÃ¡Â»â€¢n thÃ†Â°Ã†Â¡ng vÃƒÂ  Ã„â€˜Ã¡ÂºÂ·c thÃƒÂ¹ nghÃ¡Â»Â nghiÃ¡Â»â€¡p cÃ¡Â»Â§a tÃ¡Â»Â«ng ngÃ†Â°Ã¡Â»Âi bÃ¡Â»â€¡nh.",
        "highlights": [
            "Ã„ÂÃƒÂ¡nh giÃƒÂ¡ vÃ¡ÂºÂ­n Ã„â€˜Ã¡Â»â„¢ng vÃƒÂ  mÃ¡Â»Â©c Ã„â€˜Ã¡Â»â„¢ Ã„â€˜au theo tÃ¡Â»Â«ng giai Ã„â€˜oÃ¡ÂºÂ¡n.",
            "PhÃƒÂ¡c Ã„â€˜Ã¡Â»â€œ tÃ¡ÂºÂ­p luyÃ¡Â»â€¡n cÃƒÂ¡ nhÃƒÂ¢n hÃƒÂ³a theo mÃ¡Â»Â¥c tiÃƒÂªu phÃ¡Â»Â¥c hÃ¡Â»â€œi.",
            "KÃ¡ÂºÂ¿t hÃ¡Â»Â£p vÃ¡ÂºÂ­t lÃƒÂ½ trÃ¡Â»â€¹ liÃ¡Â»â€¡u Ã„â€˜Ã¡Â»Æ’ giÃ¡ÂºÂ£m Ã„â€˜au vÃƒÂ  cÃ¡ÂºÂ£i thiÃ¡Â»â€¡n biÃƒÂªn Ã„â€˜Ã¡Â»â„¢ khÃ¡Â»â€ºp.",
        ],
        "conditions": ["ThoÃƒÂ¡i hÃƒÂ³a cÃ¡Â»â„¢t sÃ¡Â»â€˜ng cÃ¡Â»â€¢/lÃ†Â°ng", "Ã„Âau vai gÃƒÂ¡y, viÃƒÂªm quanh khÃ¡Â»â€ºp vai", "Ã„Âau gÃ¡Â»â€˜i, thoÃƒÂ¡i hÃƒÂ³a khÃ¡Â»â€ºp gÃ¡Â»â€˜i", "HÃ¡Â»â„¢i chÃ¡Â»Â©ng Ã¡Â»â€˜ng cÃ¡Â»â€¢ tay"],
        "methods": ["TÃ¡ÂºÂ­p trÃ¡Â»â€¹ liÃ¡Â»â€¡u vÃ¡ÂºÂ­n Ã„â€˜Ã¡Â»â„¢ng", "Ã„ÂiÃ¡Â»â€¡n xung, siÃƒÂªu ÃƒÂ¢m trÃ¡Â»â€¹ liÃ¡Â»â€¡u", "Manual therapy", "HÃ†Â°Ã¡Â»â€ºng dÃ¡ÂºÂ«n tÃ†Â° thÃ¡ÂºÂ¿ vÃƒÂ  phÃƒÂ²ng ngÃ¡Â»Â«a tÃƒÂ¡i phÃƒÂ¡t"],
        "process": ["KhÃƒÂ¡m Ã„â€˜ÃƒÂ¡nh giÃƒÂ¡ ban Ã„â€˜Ã¡ÂºÂ§u", "Ã„ÂÃ¡ÂºÂ·t mÃ¡Â»Â¥c tiÃƒÂªu theo tuÃ¡ÂºÂ§n", "Can thiÃ¡Â»â€¡p tÃ¡ÂºÂ¡i cÃ†Â¡ sÃ¡Â»Å¸ + bÃƒÂ i tÃ¡ÂºÂ­p tÃ¡ÂºÂ¡i nhÃƒÂ ", "TÃƒÂ¡i khÃƒÂ¡m vÃƒÂ  Ã„â€˜iÃ¡Â»Âu chÃ¡Â»â€°nh phÃƒÂ¡c Ã„â€˜Ã¡Â»â€œ"],
        "outcomes": ["GiÃ¡ÂºÂ£m Ã„â€˜au rÃƒÂµ sau 2-4 tuÃ¡ÂºÂ§n", "TÃ„Æ’ng linh hoÃ¡ÂºÂ¡t vÃƒÂ  sÃ¡Â»Â©c mÃ¡ÂºÂ¡nh cÃ†Â¡", "CÃ¡ÂºÂ£i thiÃ¡Â»â€¡n khÃ¡ÂºÂ£ nÃ„Æ’ng lao Ã„â€˜Ã¡Â»â„¢ng"],
        "faqs": [
            {"q": "CÃ¡ÂºÂ§n tÃ¡ÂºÂ­p bao lÃƒÂ¢u?", "a": "ThÃƒÂ´ng thÃ†Â°Ã¡Â»Âng 6-12 tuÃ¡ÂºÂ§n, tÃƒÂ¹y mÃ¡Â»Â©c Ã„â€˜Ã¡Â»â„¢ tÃ¡Â»â€¢n thÃ†Â°Ã†Â¡ng vÃƒÂ  mÃ¡Â»Â¥c tiÃƒÂªu phÃ¡Â»Â¥c hÃ¡Â»â€œi."},
            {"q": "CÃƒÂ³ cÃ¡ÂºÂ§n dÃƒÂ¹ng thuÃ¡Â»â€˜c khÃƒÂ´ng?", "a": "PhÃƒÂ¡c Ã„â€˜Ã¡Â»â€œ Ã†Â°u tiÃƒÂªn tÃ¡ÂºÂ­p vÃƒÂ  vÃ¡ÂºÂ­t lÃƒÂ½ trÃ¡Â»â€¹ liÃ¡Â»â€¡u, thuÃ¡Â»â€˜c chÃ¡Â»â€° dÃƒÂ¹ng khi cÃƒÂ³ chÃ¡Â»â€° Ã„â€˜Ã¡Â»â€¹nh bÃƒÂ¡c sÃ„Â©."},
        ],
        "gallery": [
            "https://images.unsplash.com/photo-1516549655169-df83a0774514?auto=format&fit=crop&q=80&w=1200",
            "https://images.unsplash.com/photo-1571019614242-c5c5dee9f50b?auto=format&fit=crop&q=80&w=1200",
        ],
    },
    "chan-thuong-chinh-hinh": {
        "title": "PhÃ¡Â»Â¥c hÃ¡Â»â€œi chÃ¡ÂºÂ¥n thÃ†Â°Ã†Â¡ng chÃ¡Â»â€°nh hÃƒÂ¬nh",
        "subtitle": "Ã„ÂÃ¡Â»â€œng hÃƒÂ nh sau gÃƒÂ£y xÃ†Â°Ã†Â¡ng, Ã„â€˜Ã¡Â»Â©t dÃƒÂ¢y chÃ¡ÂºÂ±ng, chÃ¡ÂºÂ¥n thÃ†Â°Ã†Â¡ng thÃ¡Â»Æ’ thao.",
        "image": "/static/images/team/doctor_new_2.jpg",
        "overview": "LÃ„Â©nh vÃ¡Â»Â±c nÃƒÂ y hÃ†Â°Ã¡Â»â€ºng Ã„â€˜Ã¡ÂºÂ¿n khÃƒÂ´i phÃ¡Â»Â¥c vÃ¡ÂºÂ­n Ã„â€˜Ã¡Â»â„¢ng sau chÃ¡ÂºÂ¥n thÃ†Â°Ã†Â¡ng vÃƒÂ  phÃ¡ÂºÂ«u thuÃ¡ÂºÂ­t chÃ¡Â»â€°nh hÃƒÂ¬nh. ChÃ†Â°Ã†Â¡ng trÃƒÂ¬nh cÃƒÂ³ lÃ¡Â»â„¢ trÃƒÂ¬nh rÃƒÂµ rÃƒÂ ng theo tÃ¡Â»Â«ng mÃ¡Â»â€˜c lÃƒÂ nh thÃ†Â°Ã†Â¡ng mÃƒÂ´ mÃ¡Â»Âm, xÃ†Â°Ã†Â¡ng vÃƒÂ  dÃƒÂ¢y chÃ¡ÂºÂ±ng.",
        "highlights": [
            "KiÃ¡Â»Æ’m soÃƒÂ¡t Ã„â€˜au vÃƒÂ  phÃƒÂ¹ nÃ¡Â»Â sau chÃ¡ÂºÂ¥n thÃ†Â°Ã†Â¡ng.",
            "TÃ¡ÂºÂ­p mÃ¡ÂºÂ¡nh cÃ†Â¡ - Ã¡Â»â€¢n Ã„â€˜Ã¡Â»â€¹nh khÃ¡Â»â€ºp theo tÃ¡Â»Â«ng mÃ¡Â»â€˜c phÃ¡Â»Â¥c hÃ¡Â»â€œi.",
            "HÃ†Â°Ã¡Â»â€ºng dÃ¡ÂºÂ«n quay lÃ¡ÂºÂ¡i sinh hoÃ¡ÂºÂ¡t vÃƒÂ  thÃ¡Â»Æ’ thao an toÃƒÂ n.",
        ],
        "conditions": ["Gay xuong sau bat bot/ket xuong", "Rach day chang cheo", "Tran thuong co khop do the thao", "Sau noi soi khop goi/vai"],
        "methods": ["TÃ¡ÂºÂ­p phÃ¡Â»Â¥c hÃ¡Â»â€œi theo giai Ã„â€˜oÃ¡ÂºÂ¡n", "BÃƒÂ i tÃ¡ÂºÂ­p proprioception", "TÃ¡ÂºÂ­p trÃ¡Â»Å¸ lÃ¡ÂºÂ¡i chÃ¡ÂºÂ¡y nhÃ¡ÂºÂ£y Ã„â€˜Ã¡Â»â€¢i hÃ†Â°Ã¡Â»â€ºng", "Ã„ÂÃƒÂ¡nh giÃƒÂ¡ biomechanics khi quay lÃ¡ÂºÂ¡i thÃ¡Â»Æ’ thao"],
        "process": ["Ã„ÂÃƒÂ¡nh giÃƒÂ¡ ROM vÃƒÂ  sÃ¡Â»Â©c mÃ¡ÂºÂ¡nh", "TÃ¡ÂºÂ­p phÃ¡Â»Â¥c hÃ¡Â»â€œi vÃ¡ÂºÂ­n Ã„â€˜Ã¡Â»â„¢ng nÃ¡Â»Ân", "TÃ¡ÂºÂ­p chuyÃƒÂªn sÃƒÂ¢u theo mÃƒÂ´n thÃ¡Â»Æ’ thao", "KiÃ¡Â»Æ’m tra sÃ¡ÂºÂµn sÃƒÂ ng quay lÃ¡ÂºÂ¡i thi Ã„â€˜Ã¡ÂºÂ¥u"],
        "outcomes": ["GiÃ¡ÂºÂ£m nguy cÃ†Â¡ tÃƒÂ¡i chÃ¡ÂºÂ¥n thÃ†Â°Ã†Â¡ng", "TrÃ¡Â»Å¸ lÃ¡ÂºÂ¡i tÃ¡ÂºÂ­p luyÃ¡Â»â€¡n an toÃƒÂ n", "CÃ¡ÂºÂ£i thiÃ¡Â»â€¡n sÃ¡Â»Â©c bÃ¡Â»Ân vÃƒÂ  phÃ¡ÂºÂ£n xÃ¡ÂºÂ¡"],
        "faqs": [
            {"q": "Sau mo bao lau thi tap?", "a": "Tuy loai mo, nhung nen bat dau som theo huong dan bac si va ky thuat vien."},
            {"q": "CÃƒÂ³ cÃ¡ÂºÂ§n ngÃ¡Â»Â«ng chÃ†Â¡i thÃ¡Â»Æ’ thao?", "a": "KhÃƒÂ´ng cÃ¡ÂºÂ§n ngÃ¡Â»Â«ng hoÃƒÂ n toÃƒÂ n, sÃ¡ÂºÂ½ cÃƒÂ³ lÃ¡Â»â„¢ trÃƒÂ¬nh tÃ¡ÂºÂ­p thay thÃ¡ÂºÂ¿ phÃƒÂ¹ hÃ¡Â»Â£p."},
        ],
        "gallery": [
            "https://images.unsplash.com/photo-1461896836934-ffe607ba8211?auto=format&fit=crop&q=80&w=1200",
            "https://images.unsplash.com/photo-1576671494903-8ec23c1f97f2?auto=format&fit=crop&q=80&w=1200",
        ],
    },
    "than-kinh": {
        "title": "PhÃ¡Â»Â¥c hÃ¡Â»â€œi tÃ¡Â»â€¢n thÃ†Â°Ã†Â¡ng thÃ¡ÂºÂ§n kinh",
        "subtitle": "ÃƒÂp dÃ¡Â»Â¥ng cho bÃ¡Â»â€¡nh nhÃƒÂ¢n sau Ã„â€˜Ã¡Â»â„¢t quÃ¡Â»Âµ, tÃ¡Â»â€¢n thÃ†Â°Ã†Â¡ng tÃ¡Â»Â§y sÃ¡Â»â€˜ng, liÃ¡Â»â€¡t dÃƒÂ¢y thÃ¡ÂºÂ§n kinh.",
        "image": "/static/images/team/doctor_new_3.jpg",
        "overview": "PhÃ¡Â»Â¥c hÃ¡Â»â€œi thÃ¡ÂºÂ§n kinh cÃ¡ÂºÂ§n cÃƒÂ¡ch tiÃ¡ÂºÂ¿p cÃ¡ÂºÂ­n Ã„â€˜a chuyÃƒÂªn khoa vÃƒÂ  theo dÃƒÂµi liÃƒÂªn tÃ¡Â»Â¥c. HandsViet kÃ¡ÂºÂ¿t hÃ¡Â»Â£p tÃ¡ÂºÂ­p vÃ¡ÂºÂ­n Ã„â€˜Ã¡Â»â„¢ng, tÃ¡ÂºÂ­p cÃƒÂ¢n bÃ¡ÂºÂ±ng vÃƒÂ  huÃ¡ÂºÂ¥n luyÃ¡Â»â€¡n kÃ¡Â»Â¹ nÃ„Æ’ng sinh hoÃ¡ÂºÂ¡t Ã„â€˜Ã¡Â»Æ’ tÃ„Æ’ng mÃ¡Â»Â©c Ã„â€˜Ã¡Â»â„¢ Ã„â€˜Ã¡Â»â„¢c lÃ¡ÂºÂ­p cho ngÃ†Â°Ã¡Â»Âi bÃ¡Â»â€¡nh.",
        "highlights": [
            "Ã„ÂÃƒÂ¡nh giÃƒÂ¡ chÃ¡Â»Â©c nÃ„Æ’ng vÃ¡ÂºÂ­n Ã„â€˜Ã¡Â»â„¢ng, thÃ„Æ’ng bÃ¡ÂºÂ±ng vÃƒÂ  sinh hoÃ¡ÂºÂ¡t hÃ¡ÂºÂ±ng ngÃƒÂ y.",
            "TÃ¡ÂºÂ­p tÃƒÂ¡i hÃ¡Â»Âc vÃ¡ÂºÂ­n Ã„â€˜Ã¡Â»â„¢ng theo nguyÃƒÂªn tÃ¡ÂºÂ¯c phÃ¡Â»Â¥c hÃ¡Â»â€œi thÃ¡ÂºÂ§n kinh.",
            "Phoi hop gia dinh de duy tri tap luyen tai nha.",
        ],
        "conditions": ["Sau dot quy", "Liet day than kinh ngoai bien", "Ton thuong tuy song", "Roi loan thang bang va dang di"],
        "methods": ["Task-oriented training", "TÃ¡ÂºÂ­p thÃ„Æ’ng bÃ¡ÂºÂ±ng vÃƒÂ  phÃƒÂ¢n bÃ¡Â»â€˜ trÃ¡Â»Âng lÃ†Â°Ã¡Â»Â£ng", "TÃ¡ÂºÂ­p ADL", "HÃ†Â°Ã¡Â»â€ºng dÃ¡ÂºÂ«n ngÃ†Â°Ã¡Â»Âi chÃ„Æ’m sÃƒÂ³c"],
        "process": ["Ã„ÂÃƒÂ¡nh giÃƒÂ¡ MMT, Berg, FIM", "Ã„ÂÃ¡ÂºÂ·t mÃ¡Â»Â¥c tiÃƒÂªu chÃ¡Â»Â©c nÃ„Æ’ng", "Can thiÃ¡Â»â€¡p Ã„â€˜a mÃƒÂ´ hÃƒÂ¬nh", "Ã„ÂÃƒÂ¡nh giÃƒÂ¡ lÃ¡ÂºÂ¡i Ã„â€˜Ã¡Â»â€¹nh kÃ¡Â»Â³ 2-4 tuÃ¡ÂºÂ§n"],
        "outcomes": ["CÃ¡ÂºÂ£i thiÃ¡Â»â€¡n khÃ¡ÂºÂ£ nÃ„Æ’ng tÃ¡Â»Â± chÃ„Æ’m sÃƒÂ³c", "TÃ„Æ’ng Ã„â€˜Ã¡Â»â„¢ an toÃƒÂ n khi di chuyÃ¡Â»Æ’n", "GiÃ¡ÂºÂ£m nguy cÃ†Â¡ tÃƒÂ© ngÃƒÂ£ vÃƒÂ  biÃ¡ÂºÂ¿n chÃ¡Â»Â©ng"],
        "faqs": [
            {"q": "Dot quy lau nam co tap duoc khong?", "a": "Van co the cai thien neu tap dung muc tieu va duy tri deu dan."},
            {"q": "Gia dinh can lam gi?", "a": "Gia dinh dong vai tro lon trong viec ho tro tap tai nha va du phong bien chung."},
        ],
        "gallery": [
            "https://images.unsplash.com/photo-1579154204601-01588f351e67?auto=format&fit=crop&q=80&w=1200",
            "https://images.unsplash.com/photo-1584515933487-779824d29309?auto=format&fit=crop&q=80&w=1200",
        ],
    },
    "sau-tai-bien": {
        "title": "PhÃ¡Â»Â¥c hÃ¡Â»â€œi sau tai biÃ¡ÂºÂ¿n",
        "subtitle": "Can thiÃ¡Â»â€¡p sÃ¡Â»â€ºm Ã„â€˜Ã¡Â»Æ’ cÃ¡ÂºÂ£i thiÃ¡Â»â€¡n vÃ¡ÂºÂ­n Ã„â€˜Ã¡Â»â„¢ng, ngÃƒÂ´n ngÃ¡Â»Â¯ vÃƒÂ  Ã„â€˜Ã¡Â»â„¢c lÃ¡ÂºÂ­p sinh hoÃ¡ÂºÂ¡t.",
        "image": "/static/images/team/doctor_new_4.jpg",
        "overview": "TrÃ¡ÂºÂ¡ng thÃƒÂ¡i sau tai biÃ¡ÂºÂ¿n cÃ¡ÂºÂ§n chÃ†Â°Ã†Â¡ng trÃƒÂ¬nh phÃ¡Â»Â¥c hÃ¡Â»â€œi toÃƒÂ n diÃ¡Â»â€¡n vÃƒÂ  kÃ¡Â»â€¹p thÃ¡Â»Âi. HandsViet xÃƒÂ¢y dÃ¡Â»Â±ng lÃ¡Â»â„¢ trÃƒÂ¬nh chi tiÃ¡ÂºÂ¿t theo mÃ¡Â»Â©c Ã„â€˜Ã¡Â»â„¢ tÃ¡Â»â€¢n thÃ†Â°Ã†Â¡ng, tÃƒÂ¬nh trÃ¡ÂºÂ¡ng tim mÃ¡ÂºÂ¡ch vÃƒÂ  mÃ¡Â»Â¥c tiÃƒÂªu cÃ¡Â»Â§a gia Ã„â€˜ÃƒÂ¬nh.",
        "highlights": [
            "Ã„ÂÃƒÂ¡nh giÃƒÂ¡ toÃƒÂ n diÃ¡Â»â€¡n chÃ¡Â»Â©c nÃ„Æ’ng ngay tÃ¡Â»Â« giai Ã„â€˜oÃ¡ÂºÂ¡n Ã„â€˜Ã¡ÂºÂ§u.",
            "XÃƒÂ¢y dÃ¡Â»Â±ng lÃ¡Â»â„¢ trÃƒÂ¬nh phÃ¡Â»Â¥c hÃ¡Â»â€œi theo mÃ¡Â»Â¥c tiÃƒÂªu ngÃ¡ÂºÂ¯n hÃ¡ÂºÂ¡n vÃƒÂ  dÃƒÂ i hÃ¡ÂºÂ¡n.",
            "HÃ†Â°Ã¡Â»â€ºng dÃ¡ÂºÂ«n chÃ„Æ’m sÃƒÂ³c vÃƒÂ  phÃƒÂ²ng tÃƒÂ¡i biÃ¡ÂºÂ¿n tÃ¡ÂºÂ¡i nhÃƒÂ .",
        ],
        "conditions": ["YÃ¡ÂºÂ¿u/liÃ¡Â»â€¡t nÃ¡Â»Â­a ngÃ†Â°Ã¡Â»Âi", "RÃ¡Â»â€˜i loÃ¡ÂºÂ¡n ngÃƒÂ´n ngÃ¡Â»Â¯ sau tai biÃ¡ÂºÂ¿n", "NuÃ¡Â»â€˜t nghÃ¡ÂºÂ¹n", "GiÃ¡ÂºÂ£m trÃƒÂ­ nhÃ¡Â»â€º sau tai biÃ¡ÂºÂ¿n"],
        "methods": ["TÃ¡ÂºÂ­p chuyÃ¡Â»Æ’n Ã„â€˜Ã¡Â»â€¢i tÃ†Â° thÃ¡ÂºÂ¿", "TÃ¡ÂºÂ­p Ã„â€˜i vÃ¡Â»â€ºi dÃ¡Â»Â¥ng cÃ¡Â»Â¥ hÃ¡Â»â€” trÃ¡Â»Â£", "TÃ¡ÂºÂ­p ngÃƒÂ´n ngÃ¡Â»Â¯ trÃ¡Â»â€¹ liÃ¡Â»â€¡u phÃ¡Â»â€˜i hÃ¡Â»Â£p", "TÃ†Â° vÃ¡ÂºÂ¥n dinh dÃ†Â°Ã¡Â»Â¡ng vÃƒÂ  dÃ¡Â»Â± phÃƒÂ²ng tÃƒÂ¡i biÃ¡ÂºÂ¿n"],
        "process": ["SÃƒÂ ng lÃ¡Â»Âc nguy cÃ†Â¡ vÃƒÂ  mÃ¡Â»Â©c Ã„â€˜Ã¡Â»â„¢ phÃ¡Â»Â¥ thuÃ¡Â»â„¢c", "Can thiÃ¡Â»â€¡p hÃ¡ÂºÂ±ng ngÃƒÂ y", "Ã„ÂÃƒÂ¡nh giÃƒÂ¡ lÃ¡ÂºÂ¡i hÃ¡ÂºÂ±ng tuÃ¡ÂºÂ§n", "LÃ¡ÂºÂ­p kÃ¡ÂºÂ¿ hoÃ¡ÂºÂ¡ch duy trÃƒÂ¬ sau xuÃ¡ÂºÂ¥t viÃ¡Â»â€¡n"],
        "outcomes": ["TÃ„Æ’ng khÃ¡ÂºÂ£ nÃ„Æ’ng tÃ¡Â»Â± lÃ¡ÂºÂ­p", "CÃ¡ÂºÂ£i thiÃ¡Â»â€¡n giao tiÃ¡ÂºÂ¿p vÃƒÂ  vÃ¡ÂºÂ­n Ã„â€˜Ã¡Â»â„¢ng", "GiÃ¡ÂºÂ£m tÃƒÂ¡i nhÃ¡ÂºÂ­p viÃ¡Â»â€¡n do biÃ¡ÂºÂ¿n chÃ¡Â»Â©ng"],
        "faqs": [
            {"q": "Bao lau thay tien bo?", "a": "Tien bo thuong thay ro sau 2-6 tuan neu tap deu va dung phac do."},
            {"q": "Co tap tai nha duoc khong?", "a": "Co, nhung can duoc huong dan bai ban va theo doi dinh ky."},
        ],
        "gallery": [
            "https://images.unsplash.com/photo-1576765608535-5f04d1e3f289?auto=format&fit=crop&q=80&w=1200",
            "https://images.unsplash.com/photo-1582719478250-c89cae4dc85b?auto=format&fit=crop&q=80&w=1200",
        ],
    },
    "sau-phau-thuat": {
        "title": "PhÃ¡Â»Â¥c hÃ¡Â»â€œi sau phÃ¡ÂºÂ«u thuÃ¡ÂºÂ­t",
        "subtitle": "DÃƒÂ nh cho ngÃ†Â°Ã¡Â»Âi bÃ¡Â»â€¡nh sau thay khÃ¡Â»â€ºp, phÃ¡ÂºÂ«u thuÃ¡ÂºÂ­t cÃ¡Â»â„¢t sÃ¡Â»â€˜ng, phÃ¡ÂºÂ«u thuÃ¡ÂºÂ­t dÃƒÂ¢y chÃ¡ÂºÂ±ng.",
        "image": "/static/images/team/doctor_new_5.jpg",
        "overview": "Sau phÃ¡ÂºÂ«u thuÃ¡ÂºÂ­t, phÃ¡Â»Â¥c hÃ¡Â»â€œi Ã„â€˜ÃƒÂºng thÃ¡Â»Âi Ã„â€˜iÃ¡Â»Æ’m giÃƒÂºp rÃƒÂºt ngÃ¡ÂºÂ¯n thÃ¡Â»Âi gian hÃ¡Â»â€œi phÃ¡Â»Â¥c vÃƒÂ  hÃ¡ÂºÂ¡n chÃ¡ÂºÂ¿ biÃ¡ÂºÂ¿n chÃ¡Â»Â©ng. HandsViet theo sÃƒÂ¡t tÃ¡Â»Â«ng giai Ã„â€˜oÃ¡ÂºÂ¡n Ã„â€˜Ã¡Â»Æ’ bÃ¡ÂºÂ£o Ã„â€˜Ã¡ÂºÂ£m an toÃƒÂ n vÃƒÂ  hiÃ¡Â»â€¡u quÃ¡ÂºÂ£.",
        "highlights": [
            "GiÃ¡ÂºÂ£m Ã„â€˜au, giÃ¡ÂºÂ£m co cÃ¡Â»Â©ng vÃƒÂ  cÃ¡ÂºÂ£i thiÃ¡Â»â€¡n tÃ¡ÂºÂ§m vÃ¡ÂºÂ­n Ã„â€˜Ã¡Â»â„¢ng sÃ¡Â»â€ºm.",
            "TÃ¡ÂºÂ­p Ã„â€˜iÃ¡Â»Æ’m tuÃ¡ÂºÂ§n tÃ¡Â»Â± theo chÃ¡Â»â€° Ã„â€˜Ã¡Â»â€¹nh hÃ¡ÂºÂ­u phÃ¡ÂºÂ«u.",
            "Theo dÃƒÂµi sÃƒÂ¡t tiÃ¡ÂºÂ¿n Ã„â€˜Ã¡Â»â„¢ Ã„â€˜Ã¡Â»Æ’ trÃ¡Â»Å¸ lÃ¡ÂºÂ¡i sinh hoÃ¡ÂºÂ¡t bÃƒÂ¬nh thÃ†Â°Ã¡Â»Âng.",
        ],
        "conditions": ["Sau thay khÃ¡Â»â€ºp hÃƒÂ¡ng/gÃ¡Â»â€˜i", "Sau mÃ¡Â»â€¢ dÃƒÂ¢y chÃ¡ÂºÂ±ng", "Sau mÃ¡Â»â€¢ cÃ¡Â»â„¢t sÃ¡Â»â€˜ng", "Sau kÃ¡ÂºÂ¿t hÃ¡Â»Â£p xÃ†Â°Ã†Â¡ng"],
        "methods": ["TÃ¡ÂºÂ­p thÃ¡Â»Å¸ vÃƒÂ  vÃ¡ÂºÂ­n Ã„â€˜Ã¡Â»â„¢ng sÃ¡Â»â€ºm", "TÃ¡ÂºÂ­p ROM cÃƒÂ³ kiÃ¡Â»Æ’m soÃƒÂ¡t", "TÃ¡ÂºÂ­p mÃ¡ÂºÂ¡nh cÃ†Â¡ trung tÃƒÂ¢m vÃƒÂ  chi", "HÃ†Â°Ã¡Â»â€ºng dÃ¡ÂºÂ«n phÃƒÂ²ng ngÃ¡Â»Â«a huyÃ¡ÂºÂ¿t khÃ¡Â»â€˜i vÃƒÂ  tÃƒÂ© ngÃƒÂ£"],
        "process": ["KhÃƒÂ¡m hÃ¡ÂºÂ­u phÃ¡ÂºÂ«u vÃƒÂ  sÃƒÂ ng lÃ¡Â»Âc nguy cÃ†Â¡", "Can thiÃ¡Â»â€¡p theo mÃ¡Â»â€˜c 1-3-6-12 tuÃ¡ÂºÂ§n", "Ã„ÂÃƒÂ¡nh giÃƒÂ¡ chÃ¡Â»Â©c nÃ„Æ’ng theo mÃ¡Â»Â¥c tiÃƒÂªu", "BÃƒÂ n giao chÃ†Â°Ã†Â¡ng trÃƒÂ¬nh duy trÃƒÂ¬ dÃƒÂ i hÃ¡ÂºÂ¡n"],
        "outcomes": ["RÃƒÂºt ngÃ¡ÂºÂ¯n thÃ¡Â»Âi gian hÃ¡Â»â€œi phÃ¡Â»Â¥c", "TÃ„Æ’ng biÃƒÂªn Ã„â€˜Ã¡Â»â„¢ khÃ¡Â»â€ºp vÃƒÂ  sÃ¡Â»Â©c mÃ¡ÂºÂ¡nh", "TrÃ¡Â»Å¸ lÃ¡ÂºÂ¡i sinh hoÃ¡ÂºÂ¡t vÃƒÂ  cÃƒÂ´ng viÃ¡Â»â€¡c sÃ¡Â»â€ºm hÃ†Â¡n"],
        "faqs": [
            {"q": "Sau mÃ¡Â»â€¢ cÃƒÂ³ nÃƒÂªn nÃ¡ÂºÂ±m nghÃ¡Â»â€° nhiÃ¡Â»Âu?", "a": "KhÃƒÂ´ng. VÃ¡ÂºÂ­n Ã„â€˜Ã¡Â»â„¢ng sÃ¡Â»â€ºm Ã„â€˜ÃƒÂºng cÃƒÂ¡ch giÃƒÂºp giÃ¡ÂºÂ£m biÃ¡ÂºÂ¿n chÃ¡Â»Â©ng vÃƒÂ  hÃ¡Â»â€œi phÃ¡Â»Â¥c nhanh hÃ†Â¡n."},
            {"q": "Khi nÃƒÂ o cÃƒÂ³ thÃ¡Â»Æ’ lÃƒÂ¡i xe/lÃƒÂ m viÃ¡Â»â€¡c?", "a": "TÃƒÂ¹y loÃ¡ÂºÂ¡i mÃ¡Â»â€¢ vÃƒÂ  nghÃ¡Â»Â nghiÃ¡Â»â€¡p, sÃ¡ÂºÂ½ Ã„â€˜Ã†Â°Ã¡Â»Â£c Ã„â€˜ÃƒÂ¡nh giÃƒÂ¡ theo mÃ¡Â»â€˜c tÃƒÂ¡i khÃƒÂ¡m."},
        ],
        "gallery": [
            "https://images.unsplash.com/photo-1580281657527-47e49f3f5f0f?auto=format&fit=crop&q=80&w=1200",
            "https://images.unsplash.com/photo-1538108149393-fbbd81895907?auto=format&fit=crop&q=80&w=1200",
        ],
    },
}

REHAB_FIELD_EN_DETAILS = {
    "co-xuong-khop": {
        "title": "Musculoskeletal and Joint Rehabilitation",
        "subtitle": "For degenerative joint disease, spinal pain, periarthritis, and overuse-related conditions.",
        "overview": "HandsViet's musculoskeletal rehabilitation program focuses on pain relief, restoring range of motion, and improving everyday function. Each plan is built around the level of injury, movement limitations, work demands, and the patient's personal recovery goals.",
        "highlights": [
            "Movement screening and pain assessment matched to each stage of recovery.",
            "Personalized exercise plans built around practical functional goals.",
            "Combined physical therapy techniques to reduce pain and improve joint mobility.",
        ],
        "conditions": [
            "Cervical or lumbar spondylosis",
            "Neck and shoulder pain or periarthritis",
            "Knee pain and osteoarthritis",
            "Carpal tunnel syndrome",
        ],
        "methods": [
            "Therapeutic exercise",
            "Electrotherapy and therapeutic ultrasound",
            "Manual therapy",
            "Posture coaching and relapse prevention",
        ],
        "process": [
            "Initial functional and pain assessment",
            "Weekly goal setting",
            "In-clinic treatment plus home exercise",
            "Reassessment and program adjustment",
        ],
        "outcomes": [
            "Noticeable pain reduction within 2 to 4 weeks",
            "Improved flexibility and muscle strength",
            "Better tolerance for work and daily activities",
        ],
        "faqs": [
            {
                "q": "How long should rehabilitation last?",
                "a": "Most programs last 6 to 12 weeks, depending on the severity of the condition and the functional goals we set together.",
            },
            {
                "q": "Do I need medication during treatment?",
                "a": "The plan usually prioritizes exercise and physical therapy. Medication is added only when prescribed by the doctor.",
            },
        ],
    },
    "chan-thuong-chinh-hinh": {
        "title": "Orthopedic Trauma Rehabilitation",
        "subtitle": "Support after fractures, ligament tears, orthopedic surgery, and sports injuries.",
        "overview": "This program is designed to restore mobility after trauma or orthopedic surgery. The recovery pathway is structured around tissue healing milestones so that exercise intensity, loading, and joint control progress safely.",
        "highlights": [
            "Control pain and swelling after injury or surgery.",
            "Rebuild muscle strength and joint stability step by step.",
            "Guide a safe return to daily life, training, and sport.",
        ],
        "conditions": [
            "Fracture recovery after casting or fixation",
            "Anterior cruciate ligament injuries",
            "Sports-related muscle and joint injuries",
            "Recovery after knee or shoulder arthroscopy",
        ],
        "methods": [
            "Phase-based rehabilitation exercise",
            "Proprioception and balance training",
            "Return-to-run and change-of-direction training",
            "Biomechanical assessment before return to sport",
        ],
        "process": [
            "Assess range of motion and muscle strength",
            "Rebuild foundational movement patterns",
            "Progress to sport-specific or work-specific exercise",
            "Test readiness before full return",
        ],
        "outcomes": [
            "Lower risk of reinjury",
            "Safer return to training and competition",
            "Improved endurance, coordination, and reaction control",
        ],
        "faqs": [
            {
                "q": "How soon can I start after surgery?",
                "a": "That depends on the procedure, but guided early rehabilitation is usually recommended as soon as your surgeon allows it.",
            },
            {
                "q": "Do I have to stop all sports activity?",
                "a": "Not always. We can usually provide a modified training plan that protects healing tissues while maintaining fitness.",
            },
        ],
    },
    "than-kinh": {
        "title": "Neurological Rehabilitation",
        "subtitle": "For patients after stroke, spinal cord injury, peripheral nerve injury, and balance disorders.",
        "overview": "Neurological rehabilitation requires a multidisciplinary approach and close follow-up. HandsViet combines movement retraining, balance practice, and daily living training to improve safety, independence, and long-term participation in life roles.",
        "highlights": [
            "Assessment of movement, balance, and daily functional performance.",
            "Motor relearning based on neurological rehabilitation principles.",
            "Family coordination to maintain effective home practice.",
        ],
        "conditions": [
            "Recovery after stroke",
            "Peripheral nerve palsy",
            "Spinal cord injury",
            "Balance and gait disorders",
        ],
        "methods": [
            "Task-oriented training",
            "Balance and weight-shift training",
            "Activities of daily living training",
            "Caregiver education and home guidance",
        ],
        "process": [
            "Functional assessment with strength and balance scales",
            "Goal setting around meaningful daily tasks",
            "Multimodal intervention in clinic and at home",
            "Reassessment every 2 to 4 weeks",
        ],
        "outcomes": [
            "Better self-care and daily independence",
            "Safer walking and transfers",
            "Lower risk of falls and secondary complications",
        ],
        "faqs": [
            {
                "q": "Can long-term neurological patients still improve?",
                "a": "Yes. Progress is still possible when treatment stays goal-based, specific, and consistent over time.",
            },
            {
                "q": "What should family members do during recovery?",
                "a": "Family support is essential for supervised home exercise, safe positioning, and prevention of avoidable complications.",
            },
        ],
    },
    "sau-tai-bien": {
        "title": "Post-stroke Rehabilitation",
        "subtitle": "Early intervention to improve movement, speech, swallowing, and independence in daily life.",
        "overview": "Recovery after stroke needs timely, comprehensive rehabilitation. HandsViet builds a detailed plan around the severity of impairment, cardiovascular status, communication needs, and the priorities of the patient and family.",
        "highlights": [
            "Comprehensive functional assessment from the earliest stage possible.",
            "Short-term and long-term goals mapped into a structured recovery pathway.",
            "Home-care education and secondary stroke prevention guidance.",
        ],
        "conditions": [
            "Weakness or paralysis on one side of the body",
            "Language or speech difficulties after stroke",
            "Swallowing difficulty",
            "Memory and cognitive changes after stroke",
        ],
        "methods": [
            "Bed mobility and transfer training",
            "Walking practice with the right assistive devices",
            "Coordinated speech and language therapy",
            "Nutrition counseling and stroke prevention guidance",
        ],
        "process": [
            "Screen risk level and degree of dependence",
            "Begin daily targeted intervention",
            "Reassess progress every week",
            "Prepare a maintenance plan before discharge",
        ],
        "outcomes": [
            "Higher independence in daily activities",
            "Improved communication and mobility",
            "Lower rehospitalization risk from complications",
        ],
        "faqs": [
            {
                "q": "How soon can improvement be seen?",
                "a": "Many patients show meaningful changes within 2 to 6 weeks when they follow the program consistently.",
            },
            {
                "q": "Can post-stroke exercise continue at home?",
                "a": "Yes, but it should follow a structured home program with regular review by the rehabilitation team.",
            },
        ],
    },
    "sau-phau-thuat": {
        "title": "Postoperative Rehabilitation",
        "subtitle": "For patients after joint replacement, spine surgery, ligament reconstruction, and fracture fixation.",
        "overview": "Rehabilitation at the right time after surgery shortens recovery and reduces complications. HandsViet follows each healing stage closely so that movement can be restored safely and efficiently.",
        "highlights": [
            "Early pain control, stiffness reduction, and range-of-motion recovery.",
            "Progressive loading based on postoperative precautions.",
            "Close monitoring to support a safe return to normal daily activity.",
        ],
        "conditions": [
            "After hip or knee replacement",
            "After ligament surgery",
            "After spine surgery",
            "After fracture fixation",
        ],
        "methods": [
            "Breathing exercise and early mobilization",
            "Controlled range-of-motion training",
            "Core and limb strengthening",
            "Guidance to prevent blood clots and falls",
        ],
        "process": [
            "Postoperative review and risk screening",
            "Intervention across 1-, 3-, 6-, and 12-week milestones",
            "Functional assessment tied to recovery goals",
            "Handover of a long-term maintenance program",
        ],
        "outcomes": [
            "Shorter recovery time",
            "Better joint mobility and muscle strength",
            "Earlier return to daily life and work",
        ],
        "faqs": [
            {
                "q": "Should I stay in bed most of the time after surgery?",
                "a": "No. Safe early movement usually reduces complications and supports faster recovery.",
            },
            {
                "q": "When can I drive or return to work?",
                "a": "That depends on the procedure and your job demands. The team will assess readiness at each follow-up milestone.",
            },
        ],
    },
}


def ensure_news_categories():
    sync_news_categories()


def ensure_service_categories():
    sync_service_categories()


def _get_runtime_i18n_translator():
    global _RUNTIME_I18N_TRANSLATOR
    if _RUNTIME_I18N_TRANSLATOR is None:
        _RUNTIME_I18N_TRANSLATOR = GlobalContentTranslationMiddleware(lambda request: None)
    return _RUNTIME_I18N_TRANSLATOR


def _normalize_lang_code(lang_code: str) -> str:
    code = (lang_code or "").lower()[:2]
    return code if code in {"en", "vi"} else "en"


def _clone_rehab_field(field: dict) -> dict:
    cloned = {}
    for key, value in (field or {}).items():
        if isinstance(value, list):
            if value and isinstance(value[0], dict):
                cloned[key] = [dict(item) for item in value]
            else:
                cloned[key] = list(value)
        else:
            cloned[key] = value
    return cloned


def _localize_rehab_field(slug: str, lang_code: str) -> dict | None:
    field = REHAB_FIELD_DETAILS.get(slug)
    if not field:
        return None

    localized = _clone_rehab_field(field)
    if _normalize_lang_code(lang_code) != "en":
        return localized

    override = REHAB_FIELD_EN_DETAILS.get(slug, {})
    for key in ("title", "subtitle", "overview", "highlights", "conditions", "methods", "process", "outcomes"):
        if key in override:
            value = override[key]
            localized[key] = list(value) if isinstance(value, list) else value
    if "faqs" in override:
        localized["faqs"] = [dict(item) for item in override["faqs"]]
    return localized


def _strip_diacritics(text: str) -> str:
    if not text:
        return ""
    out = "".join(
        ch for ch in unicodedata.normalize("NFD", text) if unicodedata.category(ch) != "Mn"
    )
    return out.replace("Ä‘", "d").replace("Ä", "D")


def _is_legacy_english_placeholder(text: str) -> bool:
    cleaned = GlobalContentTranslationMiddleware._fix_mojibake(text or "").strip().lower()
    return cleaned in LEGACY_EN_PLACEHOLDERS


def _looks_like_mixed_news_translation(original: str, translated: str) -> bool:
    if not original or not translated or translated == EN_NEWS_PLACEHOLDER:
        return translated == EN_NEWS_PLACEHOLDER

    original_fixed = GlobalContentTranslationMiddleware._fix_mojibake(original)
    translated_fixed = GlobalContentTranslationMiddleware._fix_mojibake(translated)

    if not VI_CHAR_HINT_RE.search(original_fixed):
        return False

    original_ascii = _strip_diacritics(original_fixed).lower()
    translated_ascii = _strip_diacritics(translated_fixed).lower()
    similarity = SequenceMatcher(None, original_ascii, translated_ascii).ratio()
    if similarity >= 0.72:
        return True

    translated_words = set(re.findall(r"[a-z]+", translated_ascii))
    return len(translated_words & NEWS_ASCII_VI_HINTS) >= 3


def _translate_news_text(text: str, lang_code: str, english_fallback: str = EN_NEWS_TITLE_FALLBACK) -> str:
    cleaned = GlobalContentTranslationMiddleware._fix_mojibake(text or "")
    if not cleaned:
        return english_fallback if _normalize_lang_code(lang_code) == "en" else ""
    if _normalize_lang_code(lang_code) != "en":
        if _is_legacy_english_placeholder(cleaned):
            return "Nội dung đang được cập nhật."
        return cleaned
    if _is_legacy_english_placeholder(cleaned):
        return english_fallback

    translator = _get_runtime_i18n_translator()
    translated = translator._translate_segment_to_en(cleaned)
    translated = GlobalContentTranslationMiddleware._fix_mojibake(translated or "")

    if _looks_like_mixed_news_translation(cleaned, translated):
        return english_fallback
    if translated == EN_NEWS_PLACEHOLDER:
        return english_fallback
    if GlobalContentTranslationMiddleware._looks_like_ascii_vietnamese(translated):
        return english_fallback
    return translated or english_fallback


def _translate_news_html(html_text: str, lang_code: str, english_fallback: str = "") -> str:
    cleaned = GlobalContentTranslationMiddleware._fix_mojibake(html_text or "")
    if not cleaned:
        return english_fallback if _normalize_lang_code(lang_code) == "en" else ""
    if _normalize_lang_code(lang_code) != "en":
        if _is_legacy_english_placeholder(cleaned):
            return "<p>Nội dung đang được cập nhật.</p>"
        return cleaned
    if _is_legacy_english_placeholder(cleaned):
        return english_fallback

    translator = _get_runtime_i18n_translator()
    repaired = translator._repair_visible_content(cleaned)
    translated = translator._translate_visible_content_to_en(repaired)
    translated_plain = re.sub(r"<[^>]+>", " ", translated)
    original_plain = re.sub(r"<[^>]+>", " ", cleaned)

    if translated.count(EN_NEWS_PLACEHOLDER) > 2:
        return english_fallback
    if GlobalContentTranslationMiddleware._looks_like_ascii_vietnamese(translated_plain):
        return english_fallback
    if _looks_like_mixed_news_translation(original_plain, translated_plain):
        return english_fallback
    return translated or english_fallback


def _looks_like_mixed_runtime_translation(original: str, translated: str) -> bool:
    if not original or not translated or translated == EN_NEWS_PLACEHOLDER:
        return translated == EN_NEWS_PLACEHOLDER

    original_fixed = GlobalContentTranslationMiddleware._fix_mojibake(original)
    translated_fixed = GlobalContentTranslationMiddleware._fix_mojibake(translated)
    original_ascii = _strip_diacritics(original_fixed).lower()
    translated_ascii = _strip_diacritics(translated_fixed).lower()

    if not (
        VI_CHAR_HINT_RE.search(original_fixed)
        or GlobalContentTranslationMiddleware._looks_like_ascii_vietnamese(original_ascii)
    ):
        return False

    if VI_CHAR_HINT_RE.search(translated_fixed):
        return True

    if GlobalContentTranslationMiddleware._looks_like_ascii_vietnamese(translated_ascii):
        return True

    return SequenceMatcher(None, original_ascii, translated_ascii).ratio() >= 0.72


def _translate_runtime_text(text: str, lang_code: str, english_fallback: str = "") -> str:
    cleaned = GlobalContentTranslationMiddleware._fix_mojibake(text or "")
    if not cleaned:
        return ""
    if _normalize_lang_code(lang_code) != "en":
        if _is_legacy_english_placeholder(cleaned):
            return "Nội dung đang được cập nhật."
        return cleaned
    if _is_legacy_english_placeholder(cleaned):
        fallback = (english_fallback or "").strip()
        if fallback and fallback != EN_NEWS_PLACEHOLDER:
            return fallback
        return "Content update in progress."

    translator = _get_runtime_i18n_translator()
    translated = translator._translate_segment_to_en(cleaned)
    translated = GlobalContentTranslationMiddleware._fix_mojibake(translated or "")
    if _looks_like_mixed_runtime_translation(cleaned, translated):
        fallback = (english_fallback or "").strip()
        if fallback and fallback != EN_NEWS_PLACEHOLDER:
            return fallback
        return _strip_diacritics(cleaned).strip() or cleaned
    if translated:
        return translated
    fallback = (english_fallback or "").strip()
    if fallback and fallback != EN_NEWS_PLACEHOLDER:
        return fallback
    return _strip_diacritics(cleaned).strip() or cleaned


def _localize_service_category_name(category: ServiceCategory | None, lang_code: str) -> str:
    if not category:
        return "Other" if _normalize_lang_code(lang_code) == "en" else "KhÃ¡c"
    labels = SERVICE_CATEGORY_LABELS.get(category.slug)
    if labels:
        return labels.get(_normalize_lang_code(lang_code), category.name)
    return _translate_runtime_text(category.name, lang_code)


def _localize_duration_text(duration_text: str, lang_code: str, empty_fallback: str = "") -> str:
    cleaned = GlobalContentTranslationMiddleware._fix_mojibake(duration_text or "").strip()
    if not cleaned:
        return empty_fallback
    if _normalize_lang_code(lang_code) != "en":
        return cleaned

    normalized = _strip_diacritics(cleaned).lower()
    count_match = re.search(r"(\d+)", normalized)
    count = int(count_match.group(1)) if count_match else None
    if count is not None:
        if any(token in normalized for token in ("phut", "minute", "min")):
            return f"{count} min"
        if any(token in normalized for token in ("gio", "hour", "hr")):
            return f"{count} hour" + ("s" if count != 1 else "")
        if any(token in normalized for token in ("ngay", "day")):
            return f"{count} day" + ("s" if count != 1 else "")
        if any(token in normalized for token in ("tuan", "week", "wk")):
            return f"{count} week" + ("s" if count != 1 else "")
        if any(token in normalized for token in ("thang", "month", "mo")):
            return f"{count} month" + ("s" if count != 1 else "")
        if any(token in normalized for token in ("nam", "year", "yr")):
            return f"{count} year" + ("s" if count != 1 else "")

    return _translate_runtime_text(cleaned, lang_code)


def _news_category_label(category: NewsCategory | None, lang_code: str) -> str:
    if not category:
        return "News" if _normalize_lang_code(lang_code) == "en" else "Tin tá»©c"
    label = get_news_category_label(category.slug, _normalize_lang_code(lang_code))
    if label:
        return label
    return _translate_news_text(category.name, lang_code, english_fallback="Medical News")


def _news_title_fallback(article: NewsArticle, lang_code: str) -> str:
    if _normalize_lang_code(lang_code) != "en":
        return GlobalContentTranslationMiddleware._fix_mojibake(article.title or "")
    category_label = _news_category_label(article.category, "en")
    if article.published_at:
        return f"{category_label} update - {article.published_at.strftime('%d/%m/%Y')}"
    return f"{category_label} update"


def _news_summary_fallback(article: NewsArticle, lang_code: str) -> str:
    if _normalize_lang_code(lang_code) != "en":
        return GlobalContentTranslationMiddleware._fix_mojibake(article.summary or "")
    category_label = _news_category_label(article.category, "en")
    source_name = GlobalContentTranslationMiddleware._fix_mojibake(article.source_name or "").strip()
    if source_name:
        return f"Latest {category_label.lower()} highlights curated from {source_name}."
    return f"Latest {category_label.lower()} highlights with practical guidance for patients and families."


def _news_content_fallback(article: NewsArticle, lang_code: str) -> str:
    if _normalize_lang_code(lang_code) != "en":
        return GlobalContentTranslationMiddleware._fix_mojibake(article.content or "")
    category_label = _news_category_label(article.category, "en")
    published_text = article.published_at.strftime("%B %d, %Y") if article.published_at else "recently"
    source_name = GlobalContentTranslationMiddleware._fix_mojibake(article.source_name or "").strip()
    source_line = f"<p><strong>Source:</strong> {source_name}</p>" if source_name else ""
    return (
        f"<h2>{category_label}</h2>"
        f"<p>This article provides key updates in the {category_label.lower()} section.</p>"
        f"<p><strong>Published on:</strong> {published_text}</p>"
        f"{source_line}"
        "<p>Main points include practical recommendations, warning signs, and follow-up actions for readers and caregivers.</p>"
    )


def _decorate_news_article(article: NewsArticle, lang_code: str, include_content: bool = False) -> NewsArticle:
    normalized_lang = _normalize_lang_code(lang_code)
    title_fallback = _news_title_fallback(article, lang_code)
    summary_fallback = _news_summary_fallback(article, lang_code)
    content_fallback = _news_content_fallback(article, lang_code) if include_content else ""

    if normalized_lang == "en":
        source_title = (article.title_en or "").strip() or article.title
        source_summary = (article.summary_en or "").strip() or article.summary
        source_content = (article.content_en or "").strip() or article.content
    else:
        source_title = article.title
        source_summary = article.summary
        source_content = article.content

    article.display_title = _translate_news_text(source_title, lang_code, english_fallback=title_fallback)
    article.display_summary = _translate_news_text(source_summary, lang_code, english_fallback=summary_fallback)
    article.display_category_name = _news_category_label(article.category, lang_code)
    article.display_content = (
        _translate_news_html(source_content, lang_code, english_fallback=content_fallback)
        if include_content
        else ""
    )
    return article


def _parse_service_cycle(duration_text: str) -> tuple[str, int]:
    text = (duration_text or "").strip().lower()
    normalized_text = "".join(
        ch for ch in unicodedata.normalize("NFD", text) if unicodedata.category(ch) != "Mn"
    )
    count_match = re.search(r"(\d+)", normalized_text)
    cycle_count = int(count_match.group(1)) if count_match else 1

    if any(token in normalized_text for token in ("tuan", "week", "wk")):
        return "week", max(1, cycle_count)
    if any(token in normalized_text for token in ("thang", "month", "mo")):
        return "month", max(1, cycle_count)
    if any(token in normalized_text for token in ("nam", "year", "yr")):
        return "year", max(1, cycle_count)
    return "other", max(1, cycle_count)


def _decorate_service(service: Service, lang_code: str | None = None) -> Service:
    lang_code = _normalize_lang_code(lang_code or get_language())
    cycle_key, cycle_count = _parse_service_cycle(service.duration or "")
    meta = SERVICE_CYCLE_META.get(cycle_key, SERVICE_CYCLE_META["other"])

    service.cycle_key = cycle_key
    service.cycle_rank = int(meta["rank"])
    service.cycle_count = cycle_count
    service.cycle_group_label = str(meta["group"].get(lang_code, meta["group"]["vi"]))
    service.display_title = _translate_runtime_text(service.title, lang_code)
    service.display_summary = _translate_runtime_text(service.summary, lang_code)
    service.display_category_name = _localize_service_category_name(service.category, lang_code)
    service.display_featured_tag = (
        _translate_runtime_text(service.featured_tag, lang_code, english_fallback="Recommended")
        if service.featured_tag
        else ""
    )
    service.display_price = (service.price_text or "").strip() or (
        "Contact us" if lang_code == "en" else "LiÃªn há»‡"
    )
    service.display_duration = _localize_duration_text(
        service.duration,
        lang_code,
        empty_fallback="Not updated yet" if lang_code == "en" else "ChÆ°a cáº­p nháº­t",
    )
    service.display_full_info = f"{service.display_price} / {service.display_duration}"
    return service


def _sorted_services(rows, lang_code: str | None = None) -> list[Service]:
    decorated = [_decorate_service(service, lang_code) for service in rows]
    return sorted(
        decorated,
        key=lambda service: (
            int(getattr(service, "cycle_rank", 9)),
            int(getattr(service, "cycle_count", 999)),
            int(service.order or 0),
            (service.title or "").lower(),
        ),
    )


def _group_services(rows, lang_code: str | None = None) -> list[dict]:
    services = list(rows)
    if not services:
        return []
    if not hasattr(services[0], "cycle_key"):
        services = _sorted_services(services, lang_code)

    groups = {key: [] for key in ("week", "month", "year", "other")}
    for service in services:
        groups.setdefault(service.cycle_key, []).append(service)

    out = []
    for key in ("week", "month", "year", "other"):
        items = groups.get(key) or []
        if not items:
            continue
        out.append(
            {
                "key": key,
                "label": SERVICE_CYCLE_META[key]["group"].get(
                    _normalize_lang_code(lang_code or get_language()),
                    SERVICE_CYCLE_META[key]["group"]["vi"],
                ),
                "services": items,
            }
        )
    return out


def _parse_amount_text(value: str) -> Decimal:
    digits = re.sub(r"[^\d]", "", value or "")
    if not digits:
        return Decimal("0")
    return Decimal(digits)


def _duration_to_days(duration_text: str) -> int:
    cycle_key, cycle_count = _parse_service_cycle(duration_text or "")
    if cycle_key == "week":
        return max(1, cycle_count * 7)
    if cycle_key == "month":
        return max(1, cycle_count * 30)
    if cycle_key == "year":
        return max(1, cycle_count * 365)
    return max(1, cycle_count)


def _service_package_slug(service_slug: str) -> str:
    base = f"svc-{service_slug}"
    if len(base) <= 50:
        return base
    digest = hashlib.sha1(service_slug.encode("utf-8")).hexdigest()[:8]
    return f"svc-{service_slug[:37]}-{digest}"


def _sync_package_from_service(service: Service) -> Package:
    price = _parse_amount_text(service.price_text or "")
    if price <= 0:
        raise ValueError("GiÃƒÂ¡ dÃ¡Â»â€¹ch vÃ¡Â»Â¥ chÃ†Â°a hÃ¡Â»Â£p lÃ¡Â»â€¡ Ã„â€˜Ã¡Â»Æ’ thanh toÃƒÂ¡n.")

    duration_days = _duration_to_days(service.duration or "")
    package_slug = _service_package_slug(service.slug)
    defaults = {
        "name": service.title,
        "description": service.summary or f"GÃƒÂ³i dÃ¡Â»â€¹ch vÃ¡Â»Â¥ {service.title}",
        "duration_days": duration_days,
        "price": price,
        "is_active": True,
    }
    package, created = Package.objects.get_or_create(slug=package_slug, defaults=defaults)
    if created:
        return package

    update_fields = []
    if package.name != defaults["name"]:
        package.name = defaults["name"]
        update_fields.append("name")
    if package.description != defaults["description"]:
        package.description = defaults["description"]
        update_fields.append("description")
    if package.duration_days != defaults["duration_days"]:
        package.duration_days = defaults["duration_days"]
        update_fields.append("duration_days")
    if package.price != defaults["price"]:
        package.price = defaults["price"]
        update_fields.append("price")
    if not package.is_active:
        package.is_active = True
        update_fields.append("is_active")

    if update_fields:
        package.save(update_fields=update_fields)
    return package


def _generate_transaction_ref() -> str:
    while True:
        suffix = uuid.uuid4().hex[:4].upper()
        candidate = f"HV{timezone.now():%y%m%d%H%M%S}{suffix}"
        if not Transaction.objects.filter(txn_ref=candidate).exists():
            return candidate


def _transaction_deadline(txn: Transaction):
    return txn.created_at + timedelta(seconds=PAYMENT_TIMEOUT_SECONDS)


def _transaction_remaining_seconds(txn: Transaction) -> int:
    remaining = int((_transaction_deadline(txn) - timezone.now()).total_seconds())
    return max(0, remaining)


def _mark_transaction_failed(txn: Transaction, reason: str = "timeout") -> Transaction:
    if txn.status != "pending":
        return txn

    raw = dict(txn.raw_params or {})
    raw["failed_reason"] = reason
    raw["failed_at"] = timezone.now().isoformat()
    txn.status = "failed"
    txn.raw_params = raw
    txn.save(update_fields=["status", "raw_params"])

    Purchase.objects.filter(payment_ref=txn.txn_ref, status="active").update(
        status="canceled",
        expires_at=timezone.now(),
    )
    return txn


def _expire_transaction_if_needed(txn: Transaction) -> Transaction:
    if txn.status == "pending" and _transaction_remaining_seconds(txn) <= 0:
        return _mark_transaction_failed(txn, reason="timeout")
    return txn


def _activate_purchase_for_transaction(txn: Transaction) -> Purchase:
    now = timezone.now()
    expires = now + timedelta(days=max(1, int(txn.package.duration_days or 1)))
    purchase = Purchase.objects.filter(payment_ref=txn.txn_ref).first()
    if purchase:
        purchase.user = txn.user
        purchase.package = txn.package
        purchase.status = "active"
        purchase.expires_at = expires
        purchase.save(update_fields=["user", "package", "status", "expires_at"])
        return purchase

    return Purchase.objects.create(
        user=txn.user,
        package=txn.package,
        expires_at=expires,
        status="active",
        payment_ref=txn.txn_ref,
    )


def _extract_txn_ref_from_payload(payload: dict) -> str:
    direct_keys = ("txn_ref", "reference", "order_code", "payment_ref", "orderCode")
    for key in direct_keys:
        value = str(payload.get(key) or "").strip().upper()
        if value:
            return value

    text_keys = ("description", "content", "addInfo", "transferContent", "message", "note")
    for key in text_keys:
        text = str(payload.get(key) or "")
        match = PAYMENT_REF_PATTERN.search(text.upper())
        if match:
            return match.group(1)
    return ""


def _parse_payload_amount(payload: dict) -> Decimal | None:
    amount_candidates = (
        payload.get("amount"),
        payload.get("transferAmount"),
        payload.get("totalAmount"),
        payload.get("value"),
    )
    for candidate in amount_candidates:
        if candidate in ("", None):
            continue
        try:
            if isinstance(candidate, (int, float, Decimal)):
                return Decimal(str(candidate))
            cleaned = re.sub(r"[^\d]", "", str(candidate))
            if cleaned:
                return Decimal(cleaned)
        except (InvalidOperation, ValueError):
            continue
    return None


def _build_transfer_content(package: Package, service: Service, txn_ref: str) -> str:
    service_name = (
        getattr(service, "display_title", None)
        or (service.title or "").strip()
        or (package.name or "").strip()
    )
    duration_text = (
        getattr(service, "display_duration", None)
        or (service.duration or "").strip()
        or f"{package.duration_days} days"
    )
    return f"{service_name} - {duration_text} - {txn_ref}"


def _build_vietqr_url(amount: Decimal, transfer_content: str) -> tuple[str, str]:
    bank_id = str(getattr(settings, "QR_BANK_ID", "") or "").strip()
    account_no = str(getattr(settings, "QR_ACCOUNT_NO", "") or "").strip()
    account_name = str(getattr(settings, "QR_ACCOUNT_NAME", "") or "").strip()
    if not bank_id or not account_no or not account_name:
        return "", "ThiÃ¡ÂºÂ¿u cÃ¡ÂºÂ¥u hÃƒÂ¬nh QR_BANK_ID / QR_ACCOUNT_NO / QR_ACCOUNT_NAME trong settings."

    amount_int = int(amount)
    info_q = quote(transfer_content, safe="")
    account_name_q = quote(account_name, safe="")
    url = (
        f"https://img.vietqr.io/image/{bank_id}-{account_no}-compact2.png"
        f"?amount={amount_int}&addInfo={info_q}&accountName={account_name_q}"
    )
    return url, ""


def _parse_recipient_emails(value) -> list[str]:
    if isinstance(value, str):
        candidates = [item.strip() for item in value.split(",")]
    elif isinstance(value, (list, tuple, set)):
        candidates = [str(item).strip() for item in value]
    else:
        candidates = [str(value).strip()] if value else []
    return [email for email in candidates if email]


def _send_email_safe(subject: str, body: str, recipients: list[str]) -> bool:
    to_emails = _parse_recipient_emails(recipients)
    if not to_emails:
        return False
    try:
        send_mail(
            subject=subject,
            message=body,
            from_email=getattr(settings, "DEFAULT_FROM_EMAIL", ""),
            recipient_list=to_emails,
            fail_silently=False,
        )
        return True
    except Exception:
        logger.exception("Failed to send email '%s' to %s", subject, to_emails)
        return False


def _booking_option_label(options: dict, key: str, lang_code: str) -> str:
    payload = options.get(key)
    if not payload:
        return key
    if isinstance(payload, dict):
        return (payload.get(lang_code) or payload.get("en") or payload.get("vi") or key).strip()
    return str(payload).strip()


def _extract_booking_meta(post_data) -> dict:
    date_raw = (post_data.get("date") or "").strip()
    specialty_key = (post_data.get("specialty") or "").strip()
    service_key = (post_data.get("service") or "").strip()
    lang_code = _normalize_lang_code(get_language())

    appointment_date_obj = None
    appointment_date = date_raw
    if date_raw:
        try:
            appointment_date_obj = datetime.strptime(date_raw, "%Y-%m-%d").date()
            appointment_date = appointment_date_obj.strftime("%d/%m/%Y")
        except ValueError:
            appointment_date = date_raw

    specialty = _booking_option_label(BOOKING_SPECIALTY_LABELS, specialty_key, lang_code)
    service_name = _booking_option_label(BOOKING_SERVICE_LABELS, service_key, lang_code)
    return {
        "appointment_date_obj": appointment_date_obj,
        "appointment_date": appointment_date,
        "specialty": specialty,
        "service_name": service_name,
    }


def _merge_booking_message(base_message: str, booking_meta: dict) -> str:
    lines = []
    if booking_meta.get("appointment_date"):
        lines.append(_tr(f"- Ngày khám mong muốn: {booking_meta['appointment_date']}", f"- Preferred date: {booking_meta['appointment_date']}"))
    if booking_meta.get("specialty"):
        lines.append(_tr(f"- Chuyên khoa: {booking_meta['specialty']}", f"- Specialty: {booking_meta['specialty']}"))
    if booking_meta.get("service_name"):
        lines.append(_tr(f"- Dịch vụ quan tâm: {booking_meta['service_name']}", f"- Requested service: {booking_meta['service_name']}"))

    details_text = ""
    if lines:
        details_text = _tr("Thông tin đặt lịch:\n", "Booking details:\n") + "\n".join(lines)

    base = (base_message or "").strip()
    if base and details_text:
        return f"{base}\n\n{details_text}"
    if details_text:
        return details_text
    return base


def _send_booking_notifications(lead: Lead, booking_meta: dict):
    appointment_date = booking_meta.get("appointment_date") or _tr("Chưa chọn", "Not selected")
    specialty = booking_meta.get("specialty") or _tr("Chưa chọn", "Not selected")
    service_name = booking_meta.get("service_name") or _tr("Chưa chọn", "Not selected")
    created_at_text = timezone.localtime(lead.created_at).strftime("%d/%m/%Y %H:%M")
    message_text = (lead.message or "").strip() or _tr("Không có ghi chú thêm.", "No additional notes.")

    phone_text = lead.phone or _tr("Chưa cập nhật", "Not updated yet")
    email_text = lead.email or _tr("Chưa cập nhật", "Not updated yet")

    user_email = (lead.email or "").strip()
    if user_email:
        user_subject = _tr(
            "HandsViet đã nhận yêu cầu đặt lịch khám của bạn",
            "HandsViet has received your booking request",
        )
        user_body = (
            _tr(f"Chào {lead.name},\n\n", f"Hello {lead.name},\n\n")
            + _tr(
                "HandsViet đã nhận được yêu cầu đặt lịch khám của bạn.\n\n",
                "HandsViet confirms that we have received your booking request.\n\n",
            )
            + _tr("Thông tin:\n", "Details:\n")
            + _tr(f"- Họ tên: {lead.name}\n", f"- Full name: {lead.name}\n")
            + _tr(f"- Số điện thoại: {phone_text}\n", f"- Phone number: {phone_text}\n")
            + f"- Email: {user_email}\n"
            + _tr(f"- Ngày khám mong muốn: {appointment_date}\n", f"- Preferred date: {appointment_date}\n")
            + _tr(f"- Chuyên khoa: {specialty}\n", f"- Specialty: {specialty}\n")
            + _tr(f"- Dịch vụ quan tâm: {service_name}\n", f"- Requested service: {service_name}\n")
            + _tr(f"- Ghi chú: {message_text}\n", f"- Notes: {message_text}\n")
            + _tr(f"- Thời gian gửi: {created_at_text}\n\n", f"- Submitted at: {created_at_text}\n\n")
            + _tr(
                "Bộ phận chăm sóc khách hàng sẽ liên hệ bạn sớm.\nHandsViet.",
                "Our care team will contact you shortly.\nHandsViet.",
            )
        )
        _send_email_safe(user_subject, user_body, [user_email])

    internal_recipients = _parse_recipient_emails(getattr(settings, "BOOKING_CONTACT_EMAIL", ""))
    if internal_recipients:
        internal_subject = _tr(
            f"[Booking] Yêu cầu mới từ {lead.name}",
            f"[Booking] New request from {lead.name}",
        )
        internal_body = (
            _tr(
                "Có yêu cầu đặt lịch khám mới từ website.\n\n",
                "There is a new booking request from the website.\n\n",
            )
            + _tr("Thông tin khách:\n", "Customer details:\n")
            + _tr(f"- Họ tên: {lead.name}\n", f"- Full name: {lead.name}\n")
            + _tr(f"- Số điện thoại: {phone_text}\n", f"- Phone number: {phone_text}\n")
            + f"- Email: {email_text}\n"
            + _tr(f"- Ngày khám mong muốn: {appointment_date}\n", f"- Preferred date: {appointment_date}\n")
            + _tr(f"- Chuyên khoa: {specialty}\n", f"- Specialty: {specialty}\n")
            + _tr(f"- Dịch vụ quan tâm: {service_name}\n", f"- Requested service: {service_name}\n")
            + _tr(f"- Nguồn: {lead.page or 'booking'}\n", f"- Source: {lead.page or 'booking'}\n")
            + _tr(f"- Ghi chú: {message_text}\n", f"- Notes: {message_text}\n")
            + _tr(f"- Thời gian: {created_at_text}\n", f"- Time: {created_at_text}\n")
        )
        _send_email_safe(internal_subject, internal_body, internal_recipients)


def _handle_lead(request, page_slug):
    """Create Lead from simple public form."""
    form = LeadForm(request.POST or None, initial={"page": page_slug})
    if request.method == "POST" and form.is_valid():
        form.save()
        messages.success(
            request,
            _tr("Đã nhận thông tin, chúng tôi sẽ liên hệ sớm.", "Your request has been received. We will contact you shortly."),
        )
        return True, form
    return False, form


def _user_can_view_paid(user):
    """Check if user has an active purchase."""
    if not user.is_authenticated:
        return False
    return Purchase.objects.filter(
        user=user, status="active", expires_at__gt=timezone.now()
    ).exists()


def _tr(vi_text, en_text):
    lang = (get_language() or "en").lower()
    selected = en_text if lang.startswith("en") else vi_text
    return GlobalContentTranslationMiddleware._fix_mojibake(selected)


def _team_data():
    categories = [
        {"name": _tr("CÆ¡ xÆ°Æ¡ng khá»›p", "Musculoskeletal care"), "slug": "co-xuong-khop"},
        {"name": _tr("Cháº¥n thÆ°Æ¡ng chá»‰nh hÃ¬nh", "Orthopedic trauma"), "slug": "chan-thuong-chinh-hinh"},
        {"name": _tr("Tháº§n kinh", "Neurology"), "slug": "than-kinh"},
        {"name": _tr("Sau tai biáº¿n", "Post-stroke"), "slug": "sau-tai-bien"},
        {"name": _tr("Sau pháº«u thuáº­t", "Postoperative care"), "slug": "sau-phau-thuat"},
    ]
    doctors = [
        {
            "id": 1,
            "name": "BS.CKII Nguyá»…n HoÃ ng Minh",
            "role": _tr("BÃ¡c sÄ© Phá»¥c há»“i chá»©c nÄƒng", "Rehabilitation physician"),
            "specialty": "co-xuong-khop",
            "specialty_name": _tr("PHCN CÆ¡ xÆ°Æ¡ng khá»›p", "Musculoskeletal and joint rehabilitation"),
            "exp": _tr("15+ nÄƒm", "15+ years"),
            "education": _tr("CKII PHCN - Äáº¡i há»c Y DÆ°á»£c TP.HCM", "Specialist level II in rehabilitation medicine - University of Medicine and Pharmacy at Ho Chi Minh City"),
            "strengths": _tr("ÄÃ¡nh giÃ¡ Ä‘au máº¡n tÃ­nh, Ä‘iá»u trá»‹ thoÃ¡i hÃ³a khá»›p vÃ  phá»¥c há»“i váº­n Ä‘á»™ng chuyÃªn sÃ¢u.", "Specializes in chronic pain assessment, degenerative joint care, and advanced movement restoration."),
            "bio": _tr("Æ¯u tiÃªn phÃ¡c Ä‘á»“ cÃ¡ nhÃ¢n hÃ³a, theo dÃµi sÃ¡t tiáº¿n trÃ¬nh vÃ  tá»‘i Æ°u kháº£ nÄƒng váº­n Ä‘á»™ng cho ngÆ°á»i bá»‡nh.", "Prioritizes personalized care plans, close progress monitoring, and practical movement recovery for each patient."),
            "achievements": [
                _tr("BÃ¡c sÄ© tiÃªu biá»ƒu", "Top doctor"),
                _tr("Cá»‘ váº¥n lÃ¢m sÃ ng", "Clinical mentor"),
            ],
            "image": "/static/images/team/doctor_new_1.jpg",
        },
        {
            "id": 2,
            "name": "BS.CKI Tráº§n Thu HÃ ",
            "role": _tr("BÃ¡c sÄ© PHCN Tháº§n kinh", "Neurological rehabilitation physician"),
            "specialty": "than-kinh",
            "specialty_name": _tr("PHCN Tá»•n thÆ°Æ¡ng tháº§n kinh", "Neurological rehabilitation"),
            "exp": _tr("12+ nÄƒm", "12+ years"),
            "education": _tr("CKI Tháº§n kinh - Äáº¡i há»c Y HÃ  Ná»™i", "Specialist level I in neurology - Hanoi Medical University"),
            "strengths": _tr("Phá»¥c há»“i chá»©c nÄƒng sau Ä‘á»™t quá»µ, rá»‘i loáº¡n thÄƒng báº±ng vÃ  tÃ¡i há»c váº­n Ä‘á»™ng.", "Focuses on post-stroke rehabilitation, balance disorders, and motor relearning."),
            "bio": _tr("Káº¿t há»£p táº­p chá»©c nÄƒng vÃ  giÃ¡o dá»¥c gia Ä‘Ã¬nh Ä‘á»ƒ cáº£i thiá»‡n má»©c Ä‘á»™ Ä‘á»™c láº­p trong sinh hoáº¡t.", "Combines functional training with caregiver education to improve independence in daily living."),
            "achievements": [
                _tr("Phá»¥c há»“i Ä‘á»™t quá»µ", "Stroke rehab"),
                _tr("ChÄƒm sÃ³c tháº§n kinh", "Neuro care"),
            ],
            "image": "/static/images/team/doctor_new_2.jpg",
        },
        {
            "id": 3,
            "name": "BS. LÃª Quá»‘c Báº£o",
            "role": _tr("BÃ¡c sÄ© Cháº¥n thÆ°Æ¡ng chá»‰nh hÃ¬nh", "Orthopedic trauma physician"),
            "specialty": "chan-thuong-chinh-hinh",
            "specialty_name": _tr("PHCN Cháº¥n thÆ°Æ¡ng chá»‰nh hÃ¬nh", "Orthopedic trauma rehabilitation"),
            "exp": _tr("10+ nÄƒm", "10+ years"),
            "education": _tr("BS Äa khoa - ChuyÃªn sÃ¢u Y há»c thá»ƒ thao", "Medical doctor - advanced training in sports medicine"),
            "strengths": _tr("Phá»¥c há»“i sau cháº¥n thÆ°Æ¡ng thá»ƒ thao, sau má»• dÃ¢y cháº±ng vÃ  tÃ¡i hÃ²a nháº­p váº­n Ä‘á»™ng.", "Experienced in recovery after sports injury, ligament surgery, and return-to-movement programs."),
            "bio": _tr("Táº­p trung vÃ o kiá»ƒm soÃ¡t Ä‘au, tÄƒng sá»©c máº¡nh vÃ  phÃ²ng ngá»«a tÃ¡i cháº¥n thÆ°Æ¡ng dÃ i háº¡n.", "Focuses on pain control, strength rebuilding, and long-term reinjury prevention."),
            "achievements": [
                _tr("PHCN thá»ƒ thao", "Sports rehab"),
                _tr("Quay láº¡i thi Ä‘áº¥u", "Return to play"),
            ],
            "image": "/static/images/team/doctor_new_3.jpg",
        },
        {
            "id": 4,
            "name": "BS. Pháº¡m Gia HÆ°ng",
            "role": _tr("BÃ¡c sÄ© PHCN Sau pháº«u thuáº­t", "Postoperative rehabilitation physician"),
            "specialty": "sau-phau-thuat",
            "specialty_name": _tr("PHCN Sau pháº«u thuáº­t", "Postoperative rehabilitation"),
            "exp": _tr("11+ nÄƒm", "11+ years"),
            "education": _tr("ÄÃ o táº¡o háº­u pháº«u chuyÃªn khoa ngoáº¡i", "Specialized training in postoperative surgical recovery"),
            "strengths": _tr("Phá»¥c há»“i sau thay khá»›p, pháº«u thuáº­t cá»™t sá»‘ng vÃ  can thiá»‡p chá»‰nh hÃ¬nh.", "Specializes in recovery after joint replacement, spine surgery, and orthopedic procedures."),
            "bio": _tr("XÃ¢y dá»±ng lá»™ trÃ¬nh táº­p theo tá»«ng má»‘c há»“i phá»¥c Ä‘á»ƒ rÃºt ngáº¯n thá»i gian trá»Ÿ láº¡i sinh hoáº¡t.", "Builds milestone-based recovery plans to shorten the time needed to return to daily life."),
            "achievements": [
                _tr("ChÄƒm sÃ³c háº­u pháº«u", "Post-op care"),
                _tr("Há»“i phá»¥c nhanh", "Fast recovery"),
            ],
            "image": "/static/images/team/doctor_new_4.jpg",
        },
        {
            "id": 5,
            "name": "THS.BSNT Nguyá»…n ThÃ¡i Thá»‹ Má»¹ Háº¡nh",
            "role": _tr("BÃ¡c sÄ© Chuyáº©n Ä‘oÃ¡n hÃ¬nh áº£nh", "Diagnostic imaging physician"),
            "specialty": "co-xuong-khop",
            "specialty_name": _tr("PHCN Chuyáº©n Ä‘oÃ¡n hÃ¬nh áº£nh", "Rehab imaging support"),
            "exp": _tr("9+ nÄƒm", "9+ years"),
            "education": _tr("Tháº¡c sÄ© Y khoa - Bá»‡nh viá»‡n Chá»£ Ráº«y", "Master of Medicine - Cho Ray Hospital"),
            "strengths": _tr("Äá»c hÃ¬nh áº£nh cÆ¡ xÆ°Æ¡ng khá»›p, phá»‘i há»£p Ä‘iá»u trá»‹ can thiá»‡p PHCN chÃ­nh xÃ¡c.", "Interprets musculoskeletal imaging to support precise rehabilitation decisions."),
            "bio": _tr("Äá»“ng hÃ nh cÃ¹ng bÃ¡c sÄ© Ä‘iá»u trá»‹ Ä‘á»ƒ chuáº©n hÃ³a chÆ°Æ¡ng trÃ¬nh can thiá»‡p theo báº±ng chá»©ng hÃ¬nh áº£nh.", "Works with physicians to optimize interventions based on imaging evidence."),
            "achievements": [_tr("Äá»c phim chuyÃªn sÃ¢u", "Advanced imaging"), _tr("Há»— trá»£ can thiá»‡p", "Intervention support")],
            "image": "/static/images/team/doctor_new_5.jpg",
        },
        {
            "id": 6,
            "name": "BS.CKI BÃ¹i Thá»‹ PhÆ°Æ¡ng Loan",
            "role": _tr("BÃ¡c sÄ© PHCN Nhi khoa", "Pediatric rehabilitation physician"),
            "specialty": "than-kinh",
            "specialty_name": _tr("PHCN Nhi khoa", "Pediatric rehabilitation"),
            "exp": _tr("8+ nÄƒm", "8+ years"),
            "education": _tr("CKI Nhi khoa - Äáº¡i há»c Y DÆ°á»£c Huáº¿", "Specialist level I in pediatrics - Hue University of Medicine and Pharmacy"),
            "strengths": _tr("Can thiá»‡p sá»›m cho tráº» cháº­m phÃ¡t triá»ƒn váº­n Ä‘á»™ng vÃ  rá»‘i loáº¡n giao tiáº¿p.", "Early intervention for developmental motor and communication disorders in children."),
            "bio": _tr("Káº¿t há»£p báº£ng Ä‘Ã¡nh giÃ¡ chá»©c nÄƒng vÃ  kÃ© hoáº¡ch can thiá»‡p cÃ¡ nhÃ¢n hÃ³a cho tá»«ng tráº».", "Combines functional assessment and individualized intervention plans for each child."),
            "achievements": [_tr("Can thiá»‡p sá»›m", "Early intervention"), _tr("Äá»“ng hÃ nh cÃ¹ng gia Ä‘Ã¬nh", "Family-centered care")],
            "image": "/static/images/team/doctor_new_6.jpg",
        },
    ]
    technicians = [
        {
            "name": "KTV Nguyá»…n Thanh TÃ¢m",
            "role": _tr("Ká»¹ thuáº­t viÃªn Váº­t lÃ½ trá»‹ liá»‡u", "Physical therapy technician"),
            "exp": _tr("8+ nÄƒm", "8+ years"),
            "cert": _tr("Chá»©ng chá»‰ Manual Therapy", "Manual therapy certification"),
            "strengths": _tr("Äiá»u trá»‹ Ä‘au cá»™t sá»‘ng, vai gÃ¡y, phá»¥c há»“i chá»©c nÄƒng váº­n Ä‘á»™ng.", "Treats spinal and neck-shoulder pain while supporting movement recovery."),
            "image": "/static/images/team/ktv_new_1.jpg",
        },
        {
            "name": "KTV LÃ½ HoÃ i Nam",
            "role": _tr("Ká»¹ thuáº­t viÃªn Hoáº¡t Ä‘á»™ng trá»‹ liá»‡u", "Occupational therapy technician"),
            "exp": _tr("7+ nÄƒm", "7+ years"),
            "cert": _tr("Chá»©ng chá»‰ OT lÃ¢m sÃ ng", "Clinical OT certification"),
            "strengths": _tr("Phá»¥c há»“i ká»¹ nÄƒng sinh hoáº¡t háº±ng ngÃ y vÃ  váº­n Ä‘á»™ng tinh.", "Restores daily living skills and fine motor function."),
            "image": "/static/images/team/ktv_new_2.jpg",
        },
        {
            "name": "KTV TrÆ°Æ¡ng Má»¹ Linh",
            "role": _tr("Ká»¹ thuáº­t viÃªn PHCN tháº§n kinh", "Neurological rehabilitation technician"),
            "exp": _tr("6+ nÄƒm", "6+ years"),
            "cert": _tr("Chá»©ng chá»‰ Neuro-Rehab", "Neuro-rehab certification"),
            "strengths": _tr("Táº­p thÄƒng báº±ng, kiá»ƒm soÃ¡t tÆ° tháº¿ vÃ  cáº£i thiá»‡n dÃ¡ng Ä‘i.", "Works on balance, posture control, and gait improvement."),
            "image": "/static/images/team/ktv_new_3.jpg",
        },
        {
            "name": "KTV VÅ© Äá»©c An",
            "role": _tr("Ká»¹ thuáº­t viÃªn sau cháº¥n thÆ°Æ¡ng", "Post-injury rehabilitation technician"),
            "exp": _tr("9+ nÄƒm", "9+ years"),
            "cert": _tr("Chá»©ng chá»‰ Sports Rehab", "Sports rehab certification"),
            "strengths": _tr("Phá»¥c há»“i sau má»• dÃ¢y cháº±ng, táº­p sá»©c máº¡nh vÃ  kháº£ nÄƒng quay láº¡i thá»ƒ thao.", "Supports recovery after ligament surgery, strength rebuilding, and return-to-sport readiness."),
            "image": "/static/images/team/ktv_new_4.jpg",
        },
        {
            "name": "KTV Tráº§n Ngá»c HÃ¢n",
            "role": _tr("Ká»¹ thuáº­t viÃªn NgÃ´n ngá»¯ trá»‹ liá»‡u", "Speech therapy technician"),
            "exp": _tr("5+ nÄƒm", "5+ years"),
            "cert": _tr("Chá»©ng chá»‰ Speech Rehab", "Speech rehab certification"),
            "strengths": _tr("Há»— trá»£ cháº­m nÃ³i, rá»‘i loáº¡n nuá»‘t vÃ  luyá»‡n phÃ¡t Ã¢m chuáº©n cho tráº».", "Supports delayed speech, swallowing disorders, and articulation training for children."),
            "image": "/static/images/team/ktv_new_1.jpg",
        },
        {
            "name": "KTV HoÃ ng Minh Tuáº¥n",
            "role": _tr("Ká»¹ thuáº­t viÃªn PHCN tim phá»•i", "Cardiopulmonary rehab technician"),
            "exp": _tr("6+ nÄƒm", "6+ years"),
            "cert": _tr("Chá»©ng chá»‰ Cardio Rehab", "Cardio rehab certification"),
            "strengths": _tr("Theo dÃµi táº­p luyá»‡n an toÃ n cho ngÆ°á»i bá»‡nh tim máº¡ch, hÃ´ háº¥p vÃ  sau pháº«u thuáº­t.", "Monitors safe training for cardiovascular, respiratory, and postoperative patients."),
            "image": "/static/images/team/ktv_new_2.jpg",
        },
    ]
    def _fix_obj(value):
        if isinstance(value, str):
            return GlobalContentTranslationMiddleware._fix_mojibake(value).strip()
        if isinstance(value, list):
            return [_fix_obj(v) for v in value]
        if isinstance(value, dict):
            return {k: _fix_obj(v) for k, v in value.items()}
        return value

    categories = [_fix_obj(c) for c in categories]
    doctors = [_fix_obj(d) for d in doctors]
    technicians = [_fix_obj(t) for t in technicians]

    return categories, doctors, technicians


def _home_press_mentions(lang_code: str) -> list[dict]:
    mention_filter = (
        Q(title__icontains="handsviet")
        | Q(summary__icontains="handsviet")
        | Q(content__icontains="handsviet")
        | Q(source_name__icontains="handsviet")
        | Q(source_url__icontains="handsviet")
    )
    articles = (
        NewsArticle.objects.select_related("category")
        .filter(is_published=True, category__slug="tin-truyen-thong")
        .filter(mention_filter)
        .order_by("-published_at")[:3]
    )

    items = []
    for article in articles:
        article = _decorate_news_article(article, lang_code)
        items.append(
            {
                "publisher_name": GlobalContentTranslationMiddleware._fix_mojibake(article.source_name or "").strip()
                or "HandsViet",
                "publisher_logo": None,
                "created_at": article.published_at,
                "title": article.display_title,
                "summary": article.display_summary,
                "url": article.source_url or reverse("news:news_detail", kwargs={"slug": article.slug}),
            }
        )
    return items


def _handsviet_public_highlights() -> list[dict]:
    return [
        {
            "source_name": "HandsViet",
            "source_badge": _tr("Nguồn chính thức", "Official source"),
            "date_label": _tr("Từ 2018", "Since 2018"),
            "title": _tr(
                "HandsViet giới thiệu là đơn vị tiên phong về phục hồi chức năng và y học thể thao tại Đà Nẵng",
                "HandsViet presents itself as a pioneering rehabilitation and sports medicine center in Da Nang",
            ),
            "summary": _tr(
                "Trên website chính thức, HandsViet cho biết đơn vị hoạt động từ năm 2018, tập trung vào liệu trình cá nhân hóa, không xâm lấn cho các vấn đề cột sống, dây chằng, vận động và phòng ngừa chấn thương.",
                "On its official website, HandsViet says it has operated since 2018 with personalized, non-invasive programs for spine care, ligament recovery, movement restoration, and injury prevention.",
            ),
            "url": "https://handsviet.com/",
        },
        {
            "source_name": "Lao Động / Sông Hàn",
            "source_badge": _tr("Báo chí", "Media"),
            "date_label": "26/10/2025",
            "title": _tr(
                "Báo Lao Động ghi nhận HandsViet mở cơ sở 2 tại Trung tâm Huấn luyện VĐV trẻ Quốc gia ở Đà Nẵng",
                "Lao Dong reported HandsViet opening Facility 2 at the National Youth Athletes Training Center in Da Nang",
            ),
            "summary": _tr(
                "Bài báo ngày 26/10/2025 cho biết HandsViet khai trương cơ sở 2 để phục vụ thêm người dân và vận động viên, mở rộng hiện diện trong mảng phục hồi chức năng và y học thể thao.",
                "A Lao Dong article dated October 26, 2025 reported that HandsViet opened Facility 2 to serve both residents and athletes, expanding its rehabilitation and sports medicine presence.",
            ),
            "url": "https://news.laodong.vn/ldt/suc-khoe/da-nang-them-co-so-phuc-hoi-chuc-nang-cho-nguoi-dan-va-van-dong-vien-1598296.ldo",
        },
        {
            "source_name": "GHAPAC 2025",
            "source_badge": _tr("Ghi nhận", "Recognition"),
            "date_label": "25/06/2025",
            "title": _tr(
                "HandsViet công bố được vinh danh tại Global Health Asia-Pacific Awards 2025",
                "HandsViet announced recognition at the Global Health Asia-Pacific Awards 2025",
            ),
            "summary": _tr(
                "Theo bài đăng ngày 25/06/2025 trên website chính thức, HandsViet cho biết được vinh danh ở hạng mục 'Sports Rehab and Physiotherapy Centre of the Year in Asia-Pacific'.",
                "According to the official post published on June 25, 2025, HandsViet said it was recognized as 'Sports Rehab and Physiotherapy Centre of the Year in Asia-Pacific'.",
            ),
            "url": "https://handsviet.com/handsviet-duoc-vinh-danh-trung-tam-phuc-hoi-chuc-nang-va-vat-ly-tri-lieu-the-thao-cua-nam-tai-chau-a-thai-binh-duong/",
        },
        {
            "source_name": "HandsViet / Bệnh viện 199",
            "source_badge": _tr("Chuyên môn", "Expertise"),
            "date_label": "17/03/2025",
            "title": _tr(
                "Đội ngũ HandsViet tham gia báo cáo tại hội thảo phục hồi sau ACLR ở Bệnh viện 199",
                "The HandsViet team presented at an ACLR rehabilitation workshop hosted at Hospital 199",
            ),
            "summary": _tr(
                "Bài đăng ngày 17/03/2025 cho biết BS.CKII Võ Thị Hồng Hướng, BS.CKII Phùng Cao Cường và đội ngũ HandsViet tham gia chia sẻ chuyên môn về phục hồi sau tái tạo dây chằng chéo trước.",
                "A post dated March 17, 2025 says Dr. Vo Thi Hong Huong, Dr. Phung Cao Cuong, and the HandsViet team shared expertise on rehabilitation after anterior cruciate ligament reconstruction.",
            ),
            "url": "https://handsviet.com/doi-ngu-handsviet-tham-gia-va-bao-cao-tai-hoi-thao-hanh-trinh-phuc-hoi-toan-dien-sau-aclr/",
        },
    ]


def _home_press_section_copy(has_press_mentions: bool) -> dict:
    if has_press_mentions:
        return {
            "eyebrow": _tr("Uy tín & lan tỏa", "Trust & reach"),
            "title": _tr("Báo chí nói về chúng tôi", "Press mentions"),
            "description": _tr(
                "Tổng hợp các bài viết và nguồn truyền thông công khai nhắc đến HandsViet.",
                "A selection of articles and public media references mentioning HandsViet.",
            ),
            "read_more_label": _tr("Xem nguồn", "Open source"),
            "verified_prefix": "",
            "fallback_note": "",
        }
    return {
        "eyebrow": _tr("Thông tin công khai", "Public profile"),
        "title": _tr("Tổng quan về HandsViet", "HandsViet at a glance"),
        "description": _tr(
            "Trong khi đội ngũ cập nhật danh sách báo chí chuyên biệt, đây là các nguồn công khai tiêu biểu về HandsViet đã được đối chiếu.",
            "While the dedicated press list is being updated, these are notable public references about HandsViet that have been cross-checked.",
        ),
        "read_more_label": _tr("Mở nguồn tham khảo", "Open source"),
        "verified_prefix": _tr("Đối chiếu nguồn ngày", "Sources checked on"),
        "fallback_note": _tr(
            "Khi có thêm bài báo độc lập phù hợp, section này có thể chuyển lại sang chế độ hiển thị báo chí.",
            "Once suitable independent coverage is available, this section can switch back to a press-focused layout.",
        ),
    }


def home(request):
    _, doctors, technicians = _team_data()
    lang_code = _normalize_lang_code(get_language())
    services = _sorted_services(Service.objects.select_related("category").all(), lang_code)[:8]
    press_mentions = _home_press_mentions(lang_code)
    public_highlights = _handsviet_public_highlights() if not press_mentions else []
    return render(
        request,
        "pages/home.html",
        {
            "doctors": doctors,
            "technicians": technicians,
            "services": services,
            "press_mentions": press_mentions,
            "public_highlights": public_highlights,
            "press_section_copy": _home_press_section_copy(bool(press_mentions)),
            "public_highlights_verified_at": timezone.localdate().strftime("%d/%m/%Y"),
        },
    )


def about(request):
    return render(request, "pages/about.html")


def booking(request):
    booking_meta = {"appointment_date": "", "specialty": "", "service_name": ""}
    form_data = request.POST.copy() if request.method == "POST" else None
    if form_data is not None:
        booking_meta = _extract_booking_meta(form_data)
        merged_message = _merge_booking_message(form_data.get("message", ""), booking_meta)
        if merged_message:
            form_data["message"] = merged_message
        form_data["page"] = "booking"

    form = LeadForm(form_data or None, initial={"page": "booking"})
    if request.method == "POST" and form.is_valid():
        lead = form.save(commit=False)
        lead.page = "booking"
        lead.booking_date = booking_meta.get("appointment_date_obj")
        lead.booking_specialty = booking_meta.get("specialty", "")
        lead.booking_service = booking_meta.get("service_name", "")
        lead.save()
        _send_booking_notifications(lead, booking_meta)
        messages.success(
            request,
            _tr("Đã nhận lịch khám. Chúng tôi sẽ liên hệ bạn sớm.", "Booking request received. We will contact you soon."),
        )
        return redirect(request.path)

    return render(request, "pages/booking.html", {"lead_form": form})


def contact(request):
    saved, form = _handle_lead(request, "contact")
    if saved:
        return redirect(request.path)
    return render(request, "pages/contact.html", {"lead_form": form})


@csrf_exempt
def contact_click_track(request):
    if request.method != "POST":
        return JsonResponse({"ok": False, "error": "method_not_allowed"}, status=405)

    try:
        payload = json.loads((request.body or b"{}").decode("utf-8"))
    except json.JSONDecodeError:
        payload = {}

    channel = str(payload.get("channel") or "").strip()[:50]
    href = str(payload.get("href") or "").strip()[:255]
    if not channel:
        channel = "unknown"

    Lead.objects.create(
        name=f"contact-click:{channel}",
        phone="",
        email="",
        page="contact",
        message=f"href={href}",
    )
    return JsonResponse({"ok": True})


def exercise_library(request):
    lang_code = _normalize_lang_code(get_language())
    can_paid = _user_can_view_paid(request.user)

    def normalize_provider_id(video_obj):
        raw = (video_obj.provider_id or "").strip()
        if not raw:
            return ""
        if "://" not in raw:
            return raw

        parsed = urlparse(raw)
        host = (parsed.netloc or "").lower().replace("www.", "")
        path = parsed.path.strip("/")

        if video_obj.provider == Video.PROVIDER_YT:
            if host == "youtu.be" and path:
                return path.split("/")[0]
            if host in {"youtube.com", "m.youtube.com"}:
                if path == "watch":
                    return parse_qs(parsed.query).get("v", [""])[0]
                if path.startswith("embed/") or path.startswith("shorts/"):
                    return path.split("/", 1)[1].split("/")[0]

        if video_obj.provider == Video.PROVIDER_VI:
            if host == "vimeo.com" and path:
                return path.split("/")[0]
            if host == "player.vimeo.com" and path.startswith("video/"):
                return path.split("/", 1)[1].split("/")[0]

        return raw

    videos = Video.objects.filter(is_active=True).select_related("category").order_by("title")
    normalized_videos = []
    for v in videos:
        provider_id = normalize_provider_id(v)
        if v.provider == Video.PROVIDER_YT and provider_id:
            embed_url = f"https://www.youtube.com/embed/{provider_id}"
            thumb_url = f"https://img.youtube.com/vi/{provider_id}/hqdefault.jpg"
            watch_url = f"https://www.youtube.com/watch?v={provider_id}"
        elif v.provider == Video.PROVIDER_VI and provider_id:
            embed_url = f"https://player.vimeo.com/video/{provider_id}"
            thumb_url = ""
            watch_url = f"https://vimeo.com/{provider_id}"
        else:
            embed_url = ""
            thumb_url = ""
            watch_url = ""

        normalized_videos.append(
            {
                "pk": v.pk,
                "display_title": _translate_runtime_text(v.title, lang_code),
                "display_duration": _localize_duration_text(
                    v.duration,
                    lang_code,
                    empty_fallback="Updated soon" if lang_code == "en" else "Sáº¯p cáº­p nháº­t",
                ),
                "display_category_name": _localize_service_category_name(v.category, lang_code),
                "category_slug": v.category.slug if v.category else "other",
                "display_access_label": VIDEO_ACCESS_LABELS.get(v.access, {}).get(
                    lang_code,
                    "Free" if v.access == Video.ACCESS_FREE else "Paid",
                ),
                "provider": v.provider,
                "provider_id": provider_id,
                "embed_url": embed_url,
                "watch_url": watch_url,
                "thumb_url": thumb_url,
                "access": v.access,
                "can_watch": (v.access == Video.ACCESS_FREE) or can_paid,
            }
        )

    grouped_videos = {}
    for v in normalized_videos:
        group = grouped_videos.setdefault(
            v["category_slug"],
            {
                "category_slug": v["category_slug"],
                "display_category_name": v["display_category_name"],
                "videos": [],
            },
        )
        group["videos"].append(v)
    exercises = [grouped_videos[key] for key in sorted(grouped_videos.keys())]

    return render(
        request,
        "pages/exercise_library.html",
        {
            "can_watch_paid": can_paid,
            "exercises": exercises,
        },
    )


def experts(request):
    categories, doctors, technicians = _team_data()
    return render(
        request,
        "pages/experts.html",
        {"categories": categories, "doctors": doctors, "technicians": technicians},
    )



def facilities(request):
    return render(request, "pages/facilities.html")


def faq(request):
    return render(request, "pages/faq.html")


def news_list(request, category_slug=None):
    ensure_news_categories()
    lang_code = _normalize_lang_code(get_language())
    qs = NewsArticle.objects.filter(is_published=True).select_related("category", "author").order_by("-published_at", "-id")
    current_category = None
    if category_slug:
        current_category = get_object_or_404(NewsCategory, slug=category_slug)
        qs = qs.filter(category=current_category)
    page_number = request.GET.get("page")
    if qs.count() >= 2:
        featured = qs.first()
        latest_qs = qs[1:]
    else:
        featured = None
        latest_qs = qs
    page_obj = Paginator(latest_qs, 9).get_page(page_number)
    hero_description = (
        NEWS_HERO_DESCRIPTIONS.get(current_category.slug, {}).get(lang_code)
        if current_category
        else (
            "A place to share knowledge, experience, and inspiring stories on the journey to comprehensive recovery."
            if lang_code == "en"
            else "NÆ¡i chia sáº» kiáº¿n thá»©c, kinh nghiá»‡m vÃ  nhá»¯ng cÃ¢u chuyá»‡n truyá»n cáº£m há»©ng trÃªn hÃ nh trÃ¬nh phá»¥c há»“i sá»©c khá»e toÃ n diá»‡n."
        )
    )
    featured = _decorate_news_article(featured, lang_code) if featured else None
    latest_articles = [_decorate_news_article(article, lang_code) for article in page_obj.object_list]
    current_category_display_name = _news_category_label(current_category, lang_code) if current_category else ""
    context = {
        "current_category": current_category,
        "current_category_display_name": current_category_display_name,
        "hero_description": hero_description,
        "featured_news": featured,
        "latest_news": latest_articles,
        "page_obj": page_obj,
        "categories": NewsCategory.objects.all(),
    }
    return render(request, "pages/news.html", context)


def news_category(request, category_slug):
    ensure_news_categories()
    return news_list(request, category_slug=category_slug)


def news_detail(request, slug=None):
    lang_code = _normalize_lang_code(get_language())
    article = get_object_or_404(
        NewsArticle.objects.select_related("category", "author"),
        slug=slug,
        is_published=True,
    )
    NewsArticle.objects.filter(pk=article.pk).update(view_count=F("view_count") + 1)
    article.refresh_from_db(fields=["view_count"])
    related = (
        NewsArticle.objects.filter(category=article.category, is_published=True)
        .exclude(pk=article.pk)
        .order_by("-published_at", "-id")[:3]
    )
    article = _decorate_news_article(article, lang_code, include_content=True)
    related_articles = [_decorate_news_article(item, lang_code) for item in related]
    return render(request, "pages/news_detail.html", {"article": article, "related_articles": related_articles})


def occupational_therapy(request):
    return render(request, "pages/occupational_therapy.html")


def partners(request):
    return render(request, "pages/partners.html")


def physical_therapy(request):
    return render(request, "pages/physical_therapy.html")


def rehab_fields(request):
    return render(request, "pages/rehab_fields.html")


def rehab_field_detail(request, slug):
    lang_code = _normalize_lang_code(get_language())
    field = _localize_rehab_field(slug, lang_code)
    if not field:
        raise Http404("KhÃƒÂ´ng tÃƒÂ¬m thÃ¡ÂºÂ¥y lÃ„Â©nh vÃ¡Â»Â±c phÃ¡Â»Â¥c hÃ¡Â»â€œi")
    saved, form = _handle_lead(request, f"rehab-{slug}")
    if saved:
        return redirect(request.path)
    return render(
        request,
        "pages/rehab_field_detail.html",
        {
            "field": field,
            "field_slug": slug,
            "lead_form": form,
            "lang_code": lang_code,
        },
    )


def services(request):
    ensure_service_categories()
    categories = ServiceCategory.objects.all()
    services = _sorted_services(Service.objects.select_related("category").all())
    service_groups = _group_services(services)
    return render(
        request,
        "pages/services.html",
        {"categories": categories, "services": services, "service_groups": service_groups, "category": None},
    )


def services_temp(request):
    return render(request, "pages/services_temp.html")


def category_detail(request, slug):
    ensure_service_categories()
    category = get_object_or_404(ServiceCategory, slug=slug)
    services = _sorted_services(Service.objects.select_related("category").filter(category=category))
    service_groups = _group_services(services)
    categories = ServiceCategory.objects.all()
    context = {
        "category": category,
        "services": services,
        "service_groups": service_groups,
        "categories": categories,
    }
    return render(request, "pages/services.html", context)


def service_detail(request, slug):
    service = get_object_or_404(Service.objects.select_related("category"), slug=slug)
    service = _decorate_service(service)
    package_price = _parse_amount_text(service.price_text or "")
    package_duration_days = _duration_to_days(service.duration or "")
    can_checkout = package_price > 0

    related_qs = Service.objects.select_related("category").exclude(pk=service.pk)
    if service.category_id:
        related_qs = related_qs.filter(category_id=service.category_id)
    related_services = _sorted_services(related_qs)[:4]

    return render(
        request,
        "pages/service_detail.html",
        {
            "service": service,
            "related_services": related_services,
            "can_checkout": can_checkout,
            "package_duration_days": package_duration_days,
            "checkout_url": reverse("services:service_checkout", kwargs={"slug": service.slug}) if can_checkout else "",
        },
    )


def service_checkout(request, slug):
    if not request.user.is_authenticated:
        messages.error(
            request,
            _tr("Vui lòng đăng nhập để thanh toán gói dịch vụ.", "Please log in to checkout this service package."),
        )
        return redirect(f"{settings.LOGIN_URL}?next={request.path}")

    service = get_object_or_404(Service.objects.select_related("category"), slug=slug)
    service = _decorate_service(service)
    try:
        package = _sync_package_from_service(service)
    except ValueError as exc:
        messages.error(request, str(exc))
        return redirect(service.get_absolute_url())

    latest_pending = (
        Transaction.objects.filter(user=request.user, package=package, status="pending")
        .order_by("-created_at")
        .first()
    )
    if latest_pending:
        latest_pending = _expire_transaction_if_needed(latest_pending)

    if latest_pending and latest_pending.status == "pending":
        txn = latest_pending
    else:
        txn_ref = _generate_transaction_ref()
        transfer_content = _build_transfer_content(package, service, txn_ref)
        buyer_name = (
            request.user.get_full_name().strip()
            or request.user.username
            or f"User#{request.user.pk}"
        )
        txn = Transaction.objects.create(
            user=request.user,
            package=package,
            amount=package.price,
            status="pending",
            txn_ref=txn_ref,
            raw_params={
                "service_slug": service.slug,
                "service_duration": service.display_duration,
                "transfer_content": transfer_content,
                "created_via": "service_checkout",
                "buyer_name": buyer_name,
                "buyer_username": request.user.username,
                "buyer_email": request.user.email,
            },
        )

    pending_duplicates = Transaction.objects.filter(user=request.user, package=package, status="pending").exclude(pk=txn.pk)
    for duplicate in pending_duplicates:
        _mark_transaction_failed(duplicate, reason="replaced")

    raw = dict(txn.raw_params or {})
    buyer_name = request.user.get_full_name().strip() or request.user.username
    transfer_content = str(raw.get("transfer_content") or _build_transfer_content(package, service, txn.txn_ref))
    needs_update = False
    if raw.get("transfer_content") != transfer_content:
        raw["transfer_content"] = transfer_content
        needs_update = True
    if raw.get("service_slug") != service.slug:
        raw["service_slug"] = service.slug
        needs_update = True
    if raw.get("service_duration") != service.display_duration:
        raw["service_duration"] = service.display_duration
        needs_update = True
    if raw.get("buyer_name") != buyer_name:
        raw["buyer_name"] = buyer_name
        needs_update = True
    if raw.get("buyer_username") != request.user.username:
        raw["buyer_username"] = request.user.username
        needs_update = True
    if raw.get("buyer_email") != (request.user.email or ""):
        raw["buyer_email"] = request.user.email or ""
        needs_update = True

    if needs_update:
        txn.raw_params = raw
        txn.save(update_fields=["raw_params"])

    qr_url, qr_error = _build_vietqr_url(package.price, transfer_content)

    context = {
        "service": service,
        "package": package,
        "transaction": txn,
        "buyer_name": request.user.get_full_name().strip() or request.user.username,
        "buyer_username": request.user.username,
        "buyer_email": request.user.email or _tr("Chưa cập nhật", "Not updated yet"),
        "transfer_content": transfer_content,
        "qr_url": qr_url,
        "qr_error": qr_error,
        "payment_timeout_seconds": PAYMENT_TIMEOUT_SECONDS,
        "deadline_iso": _transaction_deadline(txn).isoformat(),
        "status_url": reverse("services:service_checkout_status", kwargs={"txn_ref": txn.txn_ref}),
    }
    return render(request, "pages/service_checkout.html", context)


def service_checkout_status(request, txn_ref):
    if not request.user.is_authenticated:
        return JsonResponse({"status": "unauthenticated"}, status=401)

    txn = get_object_or_404(
        Transaction.objects.select_related("package"),
        txn_ref=txn_ref,
        user=request.user,
    )
    txn = _expire_transaction_if_needed(txn)
    remaining_seconds = _transaction_remaining_seconds(txn) if txn.status == "pending" else 0

    payload = {
        "status": txn.status,
        "txn_ref": txn.txn_ref,
        "remaining_seconds": remaining_seconds,
        "amount": str(txn.amount),
    }
    if txn.status == "success":
        payload["redirect_url"] = "/auth/profile/"
        payload["message"] = _tr("Thanh toán thành công. Gói đã được kích hoạt.", "Payment successful. Your package is now active.")
    elif txn.status == "failed":
        payload["message"] = _tr("Thanh toán thất bại hoặc đã quá hạn 3 phút.", "Payment failed or timed out after 3 minutes.")

    return JsonResponse(payload)


def speech_therapy(request):
    return render(request, "pages/speech_therapy.html")


def visit_guide(request):
    return render(request, "pages/visit_guide.html")


def buy_package(request, slug):
    package = Package.objects.filter(slug=slug, is_active=True).first()
    if not package:
        messages.error(request, "GÃƒÂ³i tÃ¡ÂºÂ­p chÃ†Â°a sÃ¡ÂºÂµn sÃƒÂ ng, vui lÃƒÂ²ng chÃ¡Â»Ân dÃ¡Â»â€¹ch vÃ¡Â»Â¥ khÃƒÂ¡c.")
        return redirect('/services/')
    if not request.user.is_authenticated:
        messages.error(request, _tr("Vui lòng đăng nhập để mua gói.", "Please log in to buy this package."))
        return redirect(f"{settings.LOGIN_URL}?next={request.path}")
    if request.method == "POST":
        expires = timezone.now() + timedelta(days=package.duration_days)
        Purchase.objects.create(
            user=request.user,
            package=package,
            expires_at=expires,
            status="active",
        )
        messages.success(request, "Ã„ÂÃƒÂ£ kÃƒÂ­ch hoÃ¡ÂºÂ¡t gÃƒÂ³i.")
        return redirect("/exercise-library/")
    return render(request, "pages/package_buy.html", {"package": package})


@csrf_exempt
def qr_payment_webhook(request):
    if request.method != "POST":
        return JsonResponse({"ok": False, "error": "method_not_allowed"}, status=405)

    webhook_secret = str(getattr(settings, "QR_WEBHOOK_SECRET", "") or "").strip()
    if webhook_secret and request.headers.get("X-QR-SECRET", "") != webhook_secret:
        return JsonResponse({"ok": False, "error": "invalid_secret"}, status=403)

    try:
        payload = json.loads((request.body or b"{}").decode("utf-8"))
    except json.JSONDecodeError:
        return JsonResponse({"ok": False, "error": "invalid_json"}, status=400)

    if not isinstance(payload, dict):
        return JsonResponse({"ok": False, "error": "payload_must_be_object"}, status=400)

    txn_ref = _extract_txn_ref_from_payload(payload)
    if not txn_ref:
        return JsonResponse({"ok": False, "error": "missing_txn_ref"}, status=400)

    txn = Transaction.objects.select_related("package", "user").filter(txn_ref=txn_ref).first()
    if not txn:
        return JsonResponse({"ok": False, "error": "transaction_not_found"}, status=404)

    txn = _expire_transaction_if_needed(txn)
    if txn.status == "failed":
        return JsonResponse({"ok": False, "status": "failed", "error": "transaction_expired"}, status=409)
    if txn.status == "success":
        return JsonResponse({"ok": True, "status": "success", "txn_ref": txn.txn_ref})

    provider_status = str(
        payload.get("status")
        or payload.get("result")
        or payload.get("event")
        or ""
    ).strip().lower()
    if provider_status in {"failed", "error", "cancel", "cancelled", "timeout"}:
        _mark_transaction_failed(txn, reason=provider_status or "provider_failed")
        return JsonResponse({"ok": False, "status": "failed", "txn_ref": txn.txn_ref}, status=400)
    if provider_status in {"pending", "processing", "waiting"}:
        return JsonResponse({"ok": True, "status": "pending", "txn_ref": txn.txn_ref})

    paid_amount = _parse_payload_amount(payload)
    if paid_amount is not None and paid_amount < txn.amount:
        _mark_transaction_failed(txn, reason="amount_mismatch")
        return JsonResponse(
            {
                "ok": False,
                "error": "amount_mismatch",
                "txn_ref": txn.txn_ref,
                "expected": str(txn.amount),
                "received": str(paid_amount),
            },
            status=400,
        )

    raw = dict(txn.raw_params or {})
    raw["webhook_payload"] = payload
    raw["paid_amount"] = str(paid_amount) if paid_amount is not None else ""
    raw["paid_at"] = timezone.now().isoformat()
    txn.status = "success"
    txn.raw_params = raw
    txn.save(update_fields=["status", "raw_params"])

    purchase = _activate_purchase_for_transaction(txn)
    return JsonResponse(
        {
            "ok": True,
            "status": "success",
            "txn_ref": txn.txn_ref,
            "purchase_id": purchase.pk,
        }
    )


@csrf_exempt
def login_view(request):
    """
    Simple username/password login using Django's AuthenticationForm.
    Supports ?next= redirect.
    """
    def _resolve_next(default_target):
        target = (request.POST.get("next") or request.GET.get("next") or "").strip()
        if not target.startswith("/"):
            return default_target
        if target.startswith("//"):
            return default_target
        return target

    def _user_next():
        target = _resolve_next("/")
        if target.startswith("/handsviet_admin/"):
            return "/"
        return target

    def _admin_next():
        target = _resolve_next(settings.LOGIN_REDIRECT_URL)
        if not target.startswith("/handsviet_admin/"):
            return settings.LOGIN_REDIRECT_URL
        return target

    if request.user.is_authenticated:
        if request.user.is_staff or request.user.is_superuser:
            return redirect(settings.LOGIN_REDIRECT_URL)
        return redirect(_user_next())

    admin_login_url = getattr(settings, "ADMIN_LOGIN_URL", "/handsviet_admin/login/")
    form = AuthenticationForm(request, data=request.POST or None)
    if request.method == "POST":
        if form.is_valid():
            user = form.get_user()
            if user.is_staff or user.is_superuser:
                messages.error(request, "Admin accounts must sign in from the admin login page.")
                return redirect(f"{admin_login_url}?next={_admin_next()}")
            login(request, user)

            return redirect(_user_next())
        else:
            messages.error(request, "Invalid username or password.")

    return render(request, "auth/login.html", {"form": form, "next": _user_next()})


def register_view(request):
    """
    Minimal registration: collects username, email, password, password_confirm.
    Creates a new user then logs them in.
    """
    if request.user.is_authenticated:
        return redirect("/")

    form_data = {
        "username": "",
        "email": "",
    }
    errors = {}

    if request.method == "POST":
        username = (request.POST.get("username") or "").strip()
        email = (request.POST.get("email") or "").strip()
        password = request.POST.get("password") or ""
        password_confirm = request.POST.get("password_confirm") or ""

        form_data["username"] = username
        form_data["email"] = email

        if not username:
            errors["username"] = "Please enter a username."
        elif len(username) < 3:
            errors["username"] = "Username must be at least 3 characters."
        elif User.objects.filter(username__iexact=username).exists():
            errors["username"] = "This username is already taken. Please choose another one."

        if not email:
            errors["email"] = "Please enter an email address."

        if not password:
            errors["password"] = "Please enter a password."
        elif len(password) < 6:
            errors["password"] = "Password must be at least 6 characters."

        if password != password_confirm:
            errors["password_confirm"] = "Password confirmation does not match."

        if not errors:
            user = User.objects.create_user(
                username=username,
                email=email,
                password=password,
            )
            login(request, user)
            messages.success(request, "Registration successful.")
            return redirect("/")

    return render(request, "auth/register.html", {"form_data": form_data, "errors": errors})


def logout_view(request):
    """
    Allow logout via GET (and POST) then redirect home.
    """
    logout(request)
    return redirect("/")


def profile_view(request):
    if not request.user.is_authenticated:
        return redirect(f"{settings.LOGIN_URL}?next=/auth/profile/")

    purchases = (
        Purchase.objects.select_related("package")
        .filter(user=request.user)
        .order_by("-started_at", "-id")
    )
    now = timezone.now()
    active_purchases = []
    purchase_history = []
    for item in purchases:
        is_active_now = item.status == "active" and item.expires_at > now
        item.is_active_now = is_active_now
        if is_active_now:
            active_purchases.append(item)
        else:
            purchase_history.append(item)

    context = {
        "active_purchases": active_purchases,
        "purchase_history": purchase_history,
        "purchase_count": purchases.count(),
    }
    return render(request, "auth/profile.html", context)


def care_management_view(request):
    if not request.user.is_authenticated:
        return redirect(f"{settings.LOGIN_URL}?next=/auth/care-management/")

    user = request.user
    patient_profile, _ = PatientProfile.objects.get_or_create(user=user)
    exercise_profile, _ = ExerciseProfile.objects.get_or_create(user=user)

    action = request.POST.get("action")
    if request.method == "POST":
        if action == "update_medical":
            patient_profile.condition = (request.POST.get("condition") or "").strip()
            patient_profile.notes = (request.POST.get("medical_notes") or "").strip()
            patient_profile.save()
            messages.success(
                request,
                _tr("Ã„ÂÃƒÂ£ cÃ¡ÂºÂ­p nhÃ¡ÂºÂ­t hÃ¡Â»â€œ sÃ†Â¡ bÃ¡Â»â€¡nh ÃƒÂ¡n Ã„â€˜Ã†Â¡n giÃ¡ÂºÂ£n.", "Simple medical profile updated."),
            )
            return redirect("/auth/care-management/")

        if action == "add_progress":
            summary = (request.POST.get("summary") or "").strip()
            score_raw = (request.POST.get("score") or "").strip()
            if summary:
                score = int(score_raw) if score_raw.isdigit() else None
                ProgressNote.objects.create(profile=patient_profile, summary=summary, score=score)
                messages.success(request, _tr("Ã„ÂÃƒÂ£ thÃƒÂªm ghi chÃƒÂº tiÃ¡ÂºÂ¿n triÃ¡Â»Æ’n.", "Progress note added."))
            else:
                messages.error(
                    request,
                    _tr("NÃ¡Â»â„¢i dung tiÃ¡ÂºÂ¿n triÃ¡Â»Æ’n khÃƒÂ´ng Ã„â€˜Ã†Â°Ã¡Â»Â£c Ã„â€˜Ã¡Â»Æ’ trÃ¡Â»â€˜ng.", "Progress summary cannot be empty."),
                )
            return redirect("/auth/care-management/")

        if action == "add_schedule":
            title = (request.POST.get("title") or "").strip()
            start_at = request.POST.get("start_at")
            end_at = request.POST.get("end_at")
            is_zoom = request.POST.get("is_zoom") == "on"
            if title and start_at and end_at:
                try:
                    start_dt = datetime.fromisoformat(start_at)
                    end_dt = datetime.fromisoformat(end_at)
                except ValueError:
                    messages.error(request, _tr("Ã„ÂÃ¡Â»â€¹nh dÃ¡ÂºÂ¡ng ngÃƒÂ y giÃ¡Â»Â khÃƒÂ´ng hÃ¡Â»Â£p lÃ¡Â»â€¡.", "Invalid date/time format."))
                    return redirect("/auth/care-management/")
                SessionSchedule.objects.create(
                    user=user,
                    title=title,
                    start_at=start_dt,
                    end_at=end_dt,
                    is_zoom=is_zoom,
                    zoom_join_url=(request.POST.get("zoom_join_url") or "").strip(),
                    zoom_meeting_id=(request.POST.get("zoom_meeting_id") or "").strip(),
                )
                messages.success(request, _tr("Ã„ÂÃƒÂ£ thÃƒÂªm lÃ¡Â»â€¹ch tÃ¡ÂºÂ­p.", "Schedule added."))
            else:
                messages.error(
                    request,
                    _tr("Vui lÃƒÂ²ng nhÃ¡ÂºÂ­p Ã„â€˜Ã¡Â»Â§ tiÃƒÂªu Ã„â€˜Ã¡Â»Â vÃƒÂ  thÃ¡Â»Âi gian lÃ¡Â»â€¹ch tÃ¡ÂºÂ­p.", "Please provide title and schedule time."),
                )
            return redirect("/auth/care-management/")

        if action == "update_exercise_profile":
            exercise_profile.goals = (request.POST.get("goals") or "").strip()
            exercise_profile.contraindications = (request.POST.get("contraindications") or "").strip()
            exercise_profile.current_level = (request.POST.get("current_level") or "").strip()
            exercise_profile.save()
            messages.success(request, _tr("Ã„ÂÃƒÂ£ cÃ¡ÂºÂ­p nhÃ¡ÂºÂ­t hÃ¡Â»â€œ sÃ†Â¡ bÃƒÂ i tÃ¡ÂºÂ­p.", "Exercise profile updated."))
            return redirect("/auth/care-management/")

        if action == "add_exercise_log":
            exercise_name = (request.POST.get("exercise_name") or "").strip()
            if exercise_name:
                duration_raw = (request.POST.get("duration_minutes") or "0").strip()
                pain_raw = (request.POST.get("pain_score") or "0").strip()
                ExerciseLog.objects.create(
                    user=user,
                    exercise_name=exercise_name,
                    category=(request.POST.get("exercise_category") or "").strip(),
                    duration_minutes=int(duration_raw) if duration_raw.isdigit() else 0,
                    pain_score=int(pain_raw) if pain_raw.isdigit() else 0,
                    notes=(request.POST.get("exercise_notes") or "").strip(),
                )
                messages.success(request, _tr("Ã„ÂÃƒÂ£ lÃ†Â°u lÃ¡Â»â€¹ch sÃ¡Â»Â­ bÃƒÂ i tÃ¡ÂºÂ­p.", "Exercise log saved."))
            else:
                messages.error(request, _tr("TÃƒÂªn bÃƒÂ i tÃ¡ÂºÂ­p khÃƒÂ´ng Ã„â€˜Ã†Â°Ã¡Â»Â£c Ã„â€˜Ã¡Â»Æ’ trÃ¡Â»â€˜ng.", "Exercise name cannot be empty."))
            return redirect("/auth/care-management/")

    schedules = SessionSchedule.objects.filter(user=user).order_by("-start_at")
    progress_notes = ProgressNote.objects.filter(profile=patient_profile).order_by("-recorded_at")
    exercise_logs = ExerciseLog.objects.filter(user=user).order_by("-trained_at")
    context = {
        "patient_profile": patient_profile,
        "exercise_profile": exercise_profile,
        "schedules": schedules,
        "progress_notes": progress_notes,
        "exercise_logs": exercise_logs,
    }
    return render(request, "auth/care_management.html", context)


# VNPay stub handlers
def vnpay_start(request, slug):
    """
    KhÃ¡Â»Å¸i tÃ¡ÂºÂ¡o thanh toÃƒÂ¡n VNPay (stub). CÃ¡ÂºÂ§n bÃ¡Â»â€¢ sung cÃ¡ÂºÂ¥u hÃƒÂ¬nh merchant + kÃƒÂ½ HMAC.
    """
    package = get_object_or_404(Package, slug=slug, is_active=True)
    txn_ref = uuid.uuid4().hex[:12]
    Transaction = None  # placeholder to avoid import loop if unused
    # TODO: tÃ¡ÂºÂ¡o Transaction entry vÃƒÂ  build URL VNPay
    messages.info(request, "VNPay chÃ†Â°a Ã„â€˜Ã†Â°Ã¡Â»Â£c cÃ¡ÂºÂ¥u hÃƒÂ¬nh. Vui lÃƒÂ²ng hoÃƒÂ n tÃ¡ÂºÂ¥t tÃƒÂ­ch hÃ¡Â»Â£p.")
    return redirect(request.META.get("HTTP_REFERER", "/"))


def vnpay_return(request):
    """
    Ã„ÂiÃ¡Â»Æ’m nhÃ¡ÂºÂ­n callback/return tÃ¡Â»Â« VNPay. CÃ¡ÂºÂ§n verify signature + cÃ¡ÂºÂ­p nhÃ¡ÂºÂ­t Transaction/Purchase.
    """
    return HttpResponse("VNPay return placeholder")

