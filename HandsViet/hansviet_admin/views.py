from datetime import datetime
import hashlib
import re
from types import SimpleNamespace

from django.conf import settings
from django.contrib import messages
from django.contrib.auth import get_user_model, login, logout
from django.contrib.auth.decorators import login_required, user_passes_test
from django.contrib.auth.forms import AuthenticationForm
from django.core.mail import send_mail
from django.core.paginator import Paginator
from django.db.models import Count, Prefetch, Q
from django.http import JsonResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.utils import timezone
from django.utils.http import url_has_allowed_host_and_scheme
from django.utils.translation import get_language

from .forms import (
    DashboardUserCreateForm,
    DashboardUserUpdateForm,
    NewsArticleForm,
    NewsCategoryForm,
    PackageForm,
    ServiceCategoryForm,
    ServiceForm,
    VideoForm,
)
from hansviet_user.middleware_i18n import GlobalContentTranslationMiddleware
from .models import Lead, NewsArticle, NewsCategory, Package, Purchase, Service, ServiceCategory, Video
from .news_category_meta import get_news_category_label, sync_news_categories
from .service_category_meta import (
    auto_assign_service_categories,
    get_service_category_description,
    get_service_category_label,
    sync_service_categories,
)


def _lang_code() -> str:
    code = (get_language() or "en").lower()
    return "en" if code.startswith("en") else "vi"


def _tr(vi_text: str, en_text: str) -> str:
    return en_text if _lang_code() == "en" else vi_text


def _decorate_service_category(category: ServiceCategory):
    lang = _lang_code()
    mapped_name = get_service_category_label(category.slug, lang)
    mapped_description = get_service_category_description(category.slug, lang)
    if lang == "en":
        category.display_name = mapped_name or _translate_admin_text(category.name, "Service category")
        category.display_description = mapped_description or _translate_admin_text(category.description or "")
    else:
        category.display_name = mapped_name or category.name
        category.display_description = mapped_description or category.description or ""
    return category


def _decorate_service_category_name(category: ServiceCategory | None) -> str:
    if not category:
        return _tr("ChÆ°a phÃ¢n loáº¡i", "Unassigned")
    mapped_name = get_service_category_label(category.slug, _lang_code())
    if mapped_name:
        return mapped_name
    return _translate_admin_text(category.name, "Service category")


ADMIN_NEWS_PLACEHOLDER = "__HV_EN_PLACEHOLDER__"
ADMIN_NEWS_OLD_PLACEHOLDERS = {
    "This section is shown in English.",
    "English content is being updated.",
}
ADMIN_VI_CHAR_HINT_RE = re.compile(
    r"[ÄƒÃ¢Ä‘ÃªÃ´Æ¡Æ°Ä‚Ã‚ÄÃŠÃ”Æ Æ¯Ã¡Ã áº£Ã£áº¡áº¥áº§áº©áº«áº­áº¯áº±áº³áºµáº·Ã©Ã¨áº»áº½áº¹áº¿á»á»ƒá»…á»‡Ã­Ã¬á»‰Ä©á»‹Ã³Ã²á»Ãµá»á»‘á»“á»•á»—á»™á»›á»á»Ÿá»¡á»£ÃºÃ¹á»§Å©á»¥á»©á»«á»­á»¯á»±Ã½á»³á»·á»¹á»µ]"
)
_ADMIN_RUNTIME_I18N_TRANSLATOR = None


def _get_admin_runtime_i18n_translator():
    global _ADMIN_RUNTIME_I18N_TRANSLATOR
    if _ADMIN_RUNTIME_I18N_TRANSLATOR is None:
        _ADMIN_RUNTIME_I18N_TRANSLATOR = GlobalContentTranslationMiddleware(lambda request: None)
    return _ADMIN_RUNTIME_I18N_TRANSLATOR


def _fix_admin_text(text: str) -> str:
    return GlobalContentTranslationMiddleware._fix_mojibake(text or "").strip()


def _is_vietnamese_like(text: str) -> bool:
    cleaned = _fix_admin_text(text)
    if not cleaned:
        return False
    if ADMIN_VI_CHAR_HINT_RE.search(cleaned):
        return True
    return GlobalContentTranslationMiddleware._looks_like_ascii_vietnamese(cleaned)


def _translate_admin_text(text: str, english_fallback: str = "") -> str:
    cleaned = _fix_admin_text(text)
    if _lang_code() != "en":
        return cleaned
    if not cleaned:
        return english_fallback
    translated = _get_admin_runtime_i18n_translator()._translate_segment_to_en(cleaned)
    translated = _fix_admin_text(translated)
    if (
        not translated
        or translated == ADMIN_NEWS_PLACEHOLDER
        or translated in ADMIN_NEWS_OLD_PLACEHOLDERS
        or _is_vietnamese_like(translated)
    ):
        if english_fallback:
            return english_fallback
        stripped = GlobalContentTranslationMiddleware._strip_diacritics(cleaned).strip()
        return stripped or cleaned
    return translated


def _translate_admin_news_text(text: str, english_fallback: str) -> str:
    return _translate_admin_text(text, english_fallback)


def _decorate_news_category(category: NewsCategory) -> NewsCategory:
    mapped_name = get_news_category_label(category.slug, _lang_code())
    if mapped_name:
        category.display_name = mapped_name
    else:
        category.display_name = _translate_admin_text(category.name, "News category")
    return category


def _decorate_news_category_name(category: NewsCategory | None) -> str:
    if not category:
        return _tr("ChÆ°a phÃ¢n loáº¡i", "Unassigned")
    mapped_name = get_news_category_label(category.slug, _lang_code())
    if mapped_name:
        return mapped_name
    return _translate_admin_text(category.name, "News category")


def _news_article_title_fallback(article: NewsArticle) -> str:
    if _lang_code() != "en":
        return _fix_admin_text(article.title)
    category_name = _decorate_news_category_name(article.category)
    if article.published_at:
        return f"{category_name} update - {article.published_at.strftime('%d/%m/%Y')}"
    return f"{category_name} update"


def _decorate_news_article(article: NewsArticle) -> NewsArticle:
    article.display_category_name = _decorate_news_category_name(article.category)
    source_title = article.title_en if _lang_code() == "en" and (article.title_en or "").strip() else article.title
    article.display_title = _translate_admin_news_text(
        source_title,
        _news_article_title_fallback(article),
    )
    return article


def staff_required(view_func):
    """Ensure user is staff/superuser and authenticated."""
    admin_login_url = getattr(settings, "ADMIN_LOGIN_URL", "/handsviet_admin/login/")
    check_staff = user_passes_test(lambda u: u.is_staff or u.is_superuser, login_url=admin_login_url)
    return login_required(check_staff(view_func), login_url=admin_login_url)


def _safe_admin_next(request):
    fallback = "/handsviet_admin/"
    candidate = request.GET.get("next") or request.POST.get("next") or ""
    if not candidate:
        return fallback
    if not url_has_allowed_host_and_scheme(
        candidate,
        allowed_hosts={request.get_host()},
        require_https=request.is_secure(),
    ):
        return fallback
    if not candidate.startswith("/handsviet_admin/"):
        return fallback
    return candidate


def admin_login_view(request):
    """Dedicated login screen for staff/admin users."""
    next_url = _safe_admin_next(request)

    if request.user.is_authenticated:
        if request.user.is_staff or request.user.is_superuser:
            return redirect(next_url)
        messages.error(
            request,
            _tr(
                "TÃ i khoáº£n nÃ y khÃ´ng cÃ³ quyá»n vÃ o trang admin.",
                "This account does not have permission to access the admin area.",
            ),
        )
        return redirect(settings.LOGIN_URL)

    form = AuthenticationForm(request, data=request.POST or None)
    if request.method == "POST":
        if form.is_valid():
            user = form.get_user()
            if user.is_staff or user.is_superuser:
                login(request, user)
                return redirect(next_url)
            messages.error(
                request,
                _tr(
                    "Trang nÃ y chá»‰ dÃ nh cho tÃ i khoáº£n admin.",
                    "This page is only available to admin accounts.",
                ),
            )
            return redirect(settings.LOGIN_URL)
        messages.error(
            request,
            _tr(
                "TÃªn Ä‘Äƒng nháº­p hoáº·c máº­t kháº©u khÃ´ng Ä‘Ãºng.",
                "Incorrect username or password.",
            ),
        )

    return render(request, "admin/admin_login.html", {"form": form, "next": next_url})


def dashboard_logout(request):
    logout(request)
    admin_login_url = getattr(settings, "ADMIN_LOGIN_URL", "/handsviet_admin/login/")
    return redirect(f"{admin_login_url}?next=/handsviet_admin/")


def _greeting_by_local_time():
    hour = timezone.localtime().hour
    if 5 <= hour < 12:
        return _tr("ChÃ o buá»•i sÃ¡ng", "Good morning")
    if 12 <= hour < 18:
        return _tr("ChÃ o buá»•i chiá»u", "Good afternoon")
    return _tr("ChÃ o buá»•i tá»‘i", "Good evening")


def _initials(text):
    raw = (text or "").strip()
    if not raw:
        return "NA"
    parts = [part for part in raw.replace("_", " ").split() if part]
    if len(parts) >= 2:
        return f"{parts[0][0]}{parts[-1][0]}".upper()
    return raw[:2].upper()


def _relative_time_label(dt):
    if not dt:
        return _tr("Vá»«a xong", "Just now")
    if timezone.is_naive(dt):
        dt = timezone.make_aware(dt, timezone.get_current_timezone())
    seconds = max(int((timezone.now() - dt).total_seconds()), 0)
    if seconds < 60:
        return _tr("Vá»«a xong", "Just now")
    minutes = seconds // 60
    if minutes < 60:
        return _tr(f"{minutes} phÃºt trÆ°á»›c", f"{minutes} minutes ago")
    hours = minutes // 60
    if hours < 24:
        return _tr(f"{hours} giá» trÆ°á»›c", f"{hours} hours ago")
    days = hours // 24
    if days < 7:
        return _tr(f"{days} ngÃ y trÆ°á»›c", f"{days} days ago")
    return timezone.localtime(dt).strftime("%d/%m/%Y %H:%M")


def _event_sort_key(dt):
    if not dt:
        return 0
    if timezone.is_naive(dt):
        dt = timezone.make_aware(dt, timezone.get_current_timezone())
    return dt.timestamp()


def _service_package_slug(service_slug: str) -> str:
    base = f"svc-{service_slug}"
    if len(base) <= 50:
        return base
    digest = hashlib.sha1(service_slug.encode("utf-8")).hexdigest()[:8]
    return f"svc-{service_slug[:37]}-{digest}"


def _extract_booking_meta_from_message(message_text: str) -> dict:
    text = (message_text or "").strip()
    if not text:
        return {
            "appointment_date": "",
            "specialty": "",
            "service_name": "",
            "note": "",
        }

    lines = [line.strip() for line in text.splitlines() if line.strip()]
    appointment_date = ""
    specialty = ""
    service_name = ""
    note_lines = []

    for line in lines:
        date_match = re.match(r"^-+\s*NgÃ y khÃ¡m mong muá»‘n:\s*(.+)$", line, flags=re.IGNORECASE)
        if date_match:
            appointment_date = date_match.group(1).strip()
            continue

        specialty_match = re.match(r"^-+\s*ChuyÃªn khoa:\s*(.+)$", line, flags=re.IGNORECASE)
        if specialty_match:
            specialty = specialty_match.group(1).strip()
            continue

        service_match = re.match(r"^-+\s*Dá»‹ch vá»¥ quan tÃ¢m:\s*(.+)$", line, flags=re.IGNORECASE)
        if service_match:
            service_name = service_match.group(1).strip()
            continue

        if line.lower().startswith("thÃ´ng tin Ä‘áº·t lá»‹ch:"):
            continue
        note_lines.append(line)

    return {
        "appointment_date": appointment_date,
        "specialty": specialty,
        "service_name": service_name,
        "note": "\n".join(note_lines).strip(),
    }


def _decorate_booking_lead(lead: Lead) -> Lead:
    legacy_meta = _extract_booking_meta_from_message(lead.message or "")
    lead.display_booking_date = (
        lead.booking_date.strftime("%d/%m/%Y")
        if lead.booking_date
        else legacy_meta.get("appointment_date") or _tr("Chưa chọn", "Not selected")
    )
    raw_specialty = lead.booking_specialty or legacy_meta.get("specialty") or ""
    raw_service = lead.booking_service or legacy_meta.get("service_name") or ""
    raw_note = legacy_meta.get("note") or ""
    lead.display_booking_specialty = _translate_admin_text(raw_specialty, "Not selected")
    lead.display_booking_service = _translate_admin_text(raw_service, "Not selected")
    lead.display_note = _translate_admin_text(raw_note, "No additional notes.")
    lead.display_created_at = timezone.localtime(lead.created_at).strftime("%d/%m/%Y %H:%M")
    lead.display_ack_sent_at = (
        timezone.localtime(lead.booking_ack_sent_at).strftime("%d/%m/%Y %H:%M")
        if lead.booking_ack_sent_at
        else ""
    )
    lead.can_send_ack = bool((lead.email or "").strip())
    return lead


def _booking_queryset_with_filters(request):
    q = (request.GET.get("q") or "").strip()
    specialty = (request.GET.get("specialty") or "").strip()
    date_from_raw = (request.GET.get("date_from") or "").strip()
    date_to_raw = (request.GET.get("date_to") or "").strip()

    bookings_qs = Lead.objects.filter(page="booking").order_by("-created_at")
    if q:
        bookings_qs = bookings_qs.filter(
            Q(name__icontains=q)
            | Q(phone__icontains=q)
            | Q(email__icontains=q)
            | Q(message__icontains=q)
        )
    if specialty:
        bookings_qs = bookings_qs.filter(booking_specialty__iexact=specialty)

    warnings = []
    if date_from_raw:
        try:
            date_from = datetime.strptime(date_from_raw, "%Y-%m-%d").date()
            bookings_qs = bookings_qs.filter(booking_date__gte=date_from)
        except ValueError:
            warnings.append(
                _tr(
                    "NgÃ y báº¯t Ä‘áº§u khÃ´ng há»£p lá»‡. Vui lÃ²ng dÃ¹ng Ä‘á»‹nh dáº¡ng YYYY-MM-DD.",
                    "Invalid start date. Please use the YYYY-MM-DD format.",
                )
            )
    if date_to_raw:
        try:
            date_to = datetime.strptime(date_to_raw, "%Y-%m-%d").date()
            bookings_qs = bookings_qs.filter(booking_date__lte=date_to)
        except ValueError:
            warnings.append(
                _tr(
                    "NgÃ y káº¿t thÃºc khÃ´ng há»£p lá»‡. Vui lÃ²ng dÃ¹ng Ä‘á»‹nh dáº¡ng YYYY-MM-DD.",
                    "Invalid end date. Please use the YYYY-MM-DD format.",
                )
            )

    filters = {
        "q": q,
        "specialty": specialty,
        "date_from_raw": date_from_raw,
        "date_to_raw": date_to_raw,
    }
    return bookings_qs, filters, warnings


def _send_booking_confirmation_email(lead: Lead) -> tuple[bool, str]:
    to_email = (lead.email or "").strip()
    if not to_email:
        return False, _tr(
            "KhÃ¡ch hÃ ng chÆ°a cÃ³ email Ä‘á»ƒ gá»­i xÃ¡c nháº­n.",
            "The customer does not have an email address for confirmation.",
        )

    lead = _decorate_booking_lead(lead)
    if _lang_code() == "en":
        subject = "HandsViet booking request confirmation"
        body = (
            f"Hello {lead.name},\n\n"
            "HandsViet confirms that we have received your booking request.\n\n"
            "Appointment details:\n"
            f"- Preferred date: {lead.display_booking_date}\n"
            f"- Specialty: {lead.display_booking_specialty}\n"
            f"- Service: {lead.display_booking_service}\n"
            f"- Notes: {lead.display_note}\n"
            f"- Submitted at: {lead.display_created_at}\n\n"
            "Our care team will contact you to confirm the exact appointment time.\n\n"
            "Best regards,\n"
            "HandsViet."
        )
    else:
        subject = "HandsViet xÃ¡c nháº­n Ä‘Ã£ nháº­n lá»‹ch Ä‘áº·t khÃ¡m"
        body = (
            f"ChÃ o {lead.name},\n\n"
            "HandsViet xÃ¡c nháº­n Ä‘Ã£ nháº­n Ä‘Æ°á»£c lá»‹ch Ä‘áº·t khÃ¡m cá»§a báº¡n.\n\n"
            "ThÃ´ng tin lá»‹ch háº¹n:\n"
            f"- NgÃ y khÃ¡m mong muá»‘n: {lead.display_booking_date}\n"
            f"- ChuyÃªn khoa: {lead.display_booking_specialty}\n"
            f"- Dá»‹ch vá»¥: {lead.display_booking_service}\n"
            f"- Ghi chÃº: {lead.display_note}\n"
            f"- Thá»i gian gá»­i yÃªu cáº§u: {lead.display_created_at}\n\n"
            "Bá»™ pháº­n CSKH sáº½ chá»§ Ä‘á»™ng liÃªn há»‡ vá»›i báº¡n Ä‘á»ƒ xÃ¡c nháº­n khung giá» cá»¥ thá»ƒ.\n\n"
            "TrÃ¢n trá»ng,\n"
            "HandsViet."
        )

    try:
        send_mail(
            subject=subject,
            message=body,
            from_email=getattr(settings, "DEFAULT_FROM_EMAIL", ""),
            recipient_list=[to_email],
            fail_silently=False,
        )
        lead.booking_ack_sent_at = timezone.now()
        lead.save(update_fields=["booking_ack_sent_at"])
        return True, ""
    except Exception as exc:
        return False, str(exc)

@staff_required
def dashboard_home(request):
    User = get_user_model()
    today = timezone.localdate()
    news_today = NewsArticle.objects.filter(is_published=True, published_at__date=today).count()
    leads_today = Lead.objects.filter(created_at__date=today).count()

    on_duty_qs = User.objects.filter(Q(is_staff=True) | Q(is_superuser=True), is_active=True).order_by("-last_login", "username")
    on_duty_count = on_duty_qs.count()
    on_duty_badges = [_initials(user.get_full_name() or user.username) for user in on_duty_qs[:3]]
    on_duty_extra_count = max(on_duty_count - len(on_duty_badges), 0)

    events = []

    for article in NewsArticle.objects.filter(is_published=True).order_by("-published_at")[:6]:
        events.append(
            {
                "event_time": article.published_at,
                "title": _tr("Báº£n tin má»›i", "New article"),
                "description": _tr(f'ÄÃ£ Ä‘Äƒng bÃ i "{article.title}".', f'Published "{article.title}".'),
                "dot_class": "bg-teal-100",
            }
        )

    for lead in Lead.objects.order_by("-created_at")[:6]:
        lead_contact = lead.email or lead.phone or lead.name
        source_page = lead.page or "website"
        events.append(
            {
                "event_time": lead.created_at,
                "title": _tr("YÃªu cáº§u há»— trá»£ má»›i", "New support request"),
                "description": _tr(
                    f"{lead_contact} vá»«a gá»­i yÃªu cáº§u tá»« trang {source_page}.",
                    f"{lead_contact} submitted a request from the {source_page} page.",
                ),
                "dot_class": "bg-blue-100",
            }
        )

    for user_obj in User.objects.filter(is_staff=False, is_superuser=False).order_by("-date_joined")[:6]:
        user_contact = user_obj.email or user_obj.username
        events.append(
            {
                "event_time": user_obj.date_joined,
                "title": _tr("NgÆ°á»i dÃ¹ng má»›i", "New user"),
                "description": _tr(
                    f"{user_contact} vá»«a Ä‘Äƒng kÃ½ tÃ i khoáº£n.",
                    f"{user_contact} just created an account.",
                ),
                "dot_class": "bg-amber-100",
            }
        )

    recent_activities = sorted(events, key=lambda item: _event_sort_key(item.get("event_time")), reverse=True)[:6]
    for item in recent_activities:
        item["time_label"] = _relative_time_label(item.get("event_time"))

    context = {
        "total_users": User.objects.count(),
        "total_videos": Video.objects.count(),
        "total_news": NewsArticle.objects.count(),
        "total_therapies": Package.objects.filter(is_active=True).count(),
        "total_services": Service.objects.count(),
        "new_news_today": news_today,
        "new_leads_today": leads_today,
        "greeting_text": _greeting_by_local_time(),
        "on_duty_count": on_duty_count,
        "on_duty_badges": on_duty_badges,
        "on_duty_extra_count": on_duty_extra_count,
        "recent_activities": recent_activities,
    }
    return render(request, "dashboard/index.html", context)

@staff_required
def user_list(request):
    User = get_user_model()
    role_filter = request.GET.get("role")
    qs = User.objects.all()
    if role_filter == "staff":
        qs = qs.filter(is_staff=True)
    elif role_filter == "user":
        qs = qs.filter(is_staff=False, is_superuser=False)

    users = [
        SimpleNamespace(
            pk=u.pk,
            username=u.username,
            email=u.email,
            role="staff" if u.is_staff or u.is_superuser else "user",
            is_active=u.is_active,
            date_joined=u.date_joined,
        )
        for u in qs.order_by("-date_joined")
    ]
    return render(request, "dashboard/users/list.html", {"users": users, "current_role": role_filter})


@staff_required
def user_create(request):
    form = DashboardUserCreateForm(request.POST or None)
    if request.method == "POST" and form.is_valid():
        created_user = form.save()
        messages.success(
            request,
            _tr(f'ÄÃ£ táº¡o tÃ i khoáº£n "{created_user.username}".', f'Created account "{created_user.username}".'),
        )
        return redirect("dashboard:user_list")

    return render(
        request,
        "dashboard/users/form.html",
        {
            "form": form,
            "title": _tr("ThÃªm nhÃ¢n viÃªn", "Add staff member"),
            "button_text": _tr("Táº¡o tÃ i khoáº£n", "Create account"),
            "is_create": True,
        },
    )


@staff_required
def user_edit(request, pk):
    User = get_user_model()
    user_obj = get_object_or_404(User, pk=pk)
    form = DashboardUserUpdateForm(request.POST or None, instance=user_obj)

    if request.method == "POST" and form.is_valid():
        if request.user.pk == user_obj.pk:
            role = form.cleaned_data.get("role")
            is_active = form.cleaned_data.get("is_active")
            if role != "staff":
                form.add_error(
                    "role",
                    _tr(
                        "KhÃ´ng thá»ƒ háº¡ quyá»n chÃ­nh tÃ i khoáº£n Ä‘ang Ä‘Äƒng nháº­p.",
                        "You cannot downgrade the role of the account currently signed in.",
                    ),
                )
            if not is_active:
                form.add_error(
                    "is_active",
                    _tr(
                        "KhÃ´ng thá»ƒ khÃ³a chÃ­nh tÃ i khoáº£n Ä‘ang Ä‘Äƒng nháº­p.",
                        "You cannot deactivate the account currently signed in.",
                    ),
                )

        if not form.errors:
            form.save()
            messages.success(request, _tr("ÄÃ£ cáº­p nháº­t tÃ i khoáº£n.", "Account updated."))
            return redirect("dashboard:user_list")

    return render(
        request,
        "dashboard/users/form.html",
        {
            "form": form,
            "target_user": user_obj,
            "title": _tr(f"Chá»‰nh sá»­a: {user_obj.username}", f"Edit: {user_obj.username}"),
            "button_text": _tr("LÆ°u", "Save"),
            "is_create": False,
        },
    )


@staff_required
def user_delete(request, pk):
    User = get_user_model()
    user_obj = get_object_or_404(User, pk=pk)
    if request.method == "POST":
        if request.user.pk == user_obj.pk:
            messages.error(
                request,
                _tr(
                    "KhÃ´ng thá»ƒ xÃ³a chÃ­nh tÃ i khoáº£n Ä‘ang Ä‘Äƒng nháº­p.",
                    "You cannot delete the account currently signed in.",
                ),
            )
            return redirect("dashboard:user_list")
        username = user_obj.username
        user_obj.delete()
        messages.success(
            request,
            _tr(f'ÄÃ£ xÃ³a tÃ i khoáº£n "{username}".', f'Deleted account "{username}".'),
        )
        return redirect("dashboard:user_list")
    return render(request, "dashboard/users/confirm_delete.html", {"target_user": user_obj})

@staff_required
def category_list(request):
    sync_service_categories()
    auto_assign_service_categories()
    categories = list(
        ServiceCategory.objects.all().prefetch_related(
            Prefetch("service_set", queryset=Service.objects.select_related("category").order_by("order", "title"))
        )
    )
    for category in categories:
        _decorate_service_category(category)
        category.service_items = list(category.service_set.all()[:3])
        for service in category.service_items:
            service.display_title = _translate_admin_text(service.title, "Service")
        category.service_count = category.service_set.count()
    return render(request, "dashboard/categories/list.html", {"categories": categories})


@staff_required
def category_create(request):
    form = ServiceCategoryForm(request.POST or None)
    if request.method == "POST" and form.is_valid():
        form.save()
        messages.success(request, _tr("ÄÃ£ táº¡o chuyÃªn má»¥c.", "Category created."))
        return redirect("dashboard:category_list")
    return render(
        request,
        "dashboard/categories/form.html",
        {"form": form, "title": _tr("ThÃªm chuyÃªn má»¥c", "Add category"), "button_text": _tr("LÆ°u", "Save")},
    )


@staff_required
def category_edit(request, pk):
    sync_service_categories()
    category = get_object_or_404(ServiceCategory, pk=pk)
    form = ServiceCategoryForm(request.POST or None, instance=category)
    if request.method == "POST" and form.is_valid():
        form.save()
        messages.success(request, _tr("ÄÃ£ cáº­p nháº­t chuyÃªn má»¥c.", "Category updated."))
        return redirect("dashboard:category_list")
    return render(
        request,
        "dashboard/categories/form.html",
        {"form": form, "title": _tr("Chá»‰nh sá»­a chuyÃªn má»¥c", "Edit category"), "button_text": _tr("LÆ°u", "Save")},
    )


@staff_required
def category_delete(request, pk):
    sync_service_categories()
    category = get_object_or_404(ServiceCategory, pk=pk)
    _decorate_service_category(category)
    if request.method == "POST":
        category.delete()
        messages.success(request, _tr("ÄÃ£ xÃ³a chuyÃªn má»¥c.", "Category deleted."))
        return redirect("dashboard:category_list")
    return render(request, "dashboard/categories/confirm_delete.html", {"category": category})

@staff_required
def service_list(request):
    sync_service_categories()
    auto_assign_service_categories()
    category_filter = (request.GET.get("category") or "").strip()
    categories = list(ServiceCategory.objects.all())
    for category in categories:
        _decorate_service_category(category)

    services_qs = Service.objects.select_related("category").all()
    if category_filter.isdigit():
        services_qs = services_qs.filter(category_id=int(category_filter))

    services = list(services_qs)
    package_slugs = [_service_package_slug(service.slug) for service in services]
    sold_by_slug = dict(
        Purchase.objects.exclude(status="canceled")
        .filter(package__slug__in=package_slugs)
        .values("package__slug")
        .annotate(total=Count("id"))
        .values_list("package__slug", "total")
    )
    for service in services:
        service.sold_count = int(sold_by_slug.get(_service_package_slug(service.slug), 0))
        service.display_category_name = _decorate_service_category_name(service.category)
        service.display_title = _translate_admin_text(service.title, "Service")
        service.display_duration = _translate_admin_text(service.duration or "")
        service.display_featured_tag = _translate_admin_text(service.featured_tag or "Featured", "Featured")

    current_category = None
    if category_filter.isdigit():
        current_category = next((category for category in categories if str(category.id) == category_filter), None)
    return render(
        request,
        "dashboard/services/list.html",
        {
            "services": services,
            "categories": categories,
            "current_category": current_category,
            "current_category_id": category_filter,
        },
    )

@staff_required
def service_create(request):
    sync_service_categories()
    form = ServiceForm(request.POST or None, request.FILES or None)
    if request.method == "POST" and form.is_valid():
        form.save()
        messages.success(request, _tr("ÄÃ£ táº¡o dá»‹ch vá»¥.", "Service created."))
        return redirect("dashboard:service_list")
    categories = list(ServiceCategory.objects.all())
    return render(
        request,
        "dashboard/services/form.html",
        {
            "categories": categories,
            "form": form,
            "title": _tr("ThÃªm dá»‹ch vá»¥", "Add service"),
            "button_text": _tr("LÆ°u", "Save"),
        },
    )


@staff_required
def service_edit(request, pk):
    sync_service_categories()
    categories = list(ServiceCategory.objects.all())
    service = get_object_or_404(Service.objects.select_related("category"), pk=pk)
    form = ServiceForm(request.POST or None, request.FILES or None, instance=service)
    if request.method == "POST" and form.is_valid():
        form.save()
        messages.success(request, _tr("ÄÃ£ cáº­p nháº­t dá»‹ch vá»¥.", "Service updated."))
        return redirect("dashboard:service_list")
    return render(
        request,
        "dashboard/services/form.html",
        {
            "service": service,
            "categories": categories,
            "form": form,
            "title": _tr("Chá»‰nh sá»­a dá»‹ch vá»¥", "Edit service"),
            "button_text": _tr("LÆ°u", "Save"),
        },
    )


@staff_required
def service_delete(request, pk):
    service = get_object_or_404(Service, pk=pk)
    if request.method == "POST":
        service.delete()
        messages.success(request, _tr("ÄÃ£ xÃ³a dá»‹ch vá»¥.", "Service deleted."))
        return redirect("dashboard:service_list")
    return render(request, "dashboard/services/confirm_delete.html", {"service": service})

@staff_required
def booking_list(request):
    bookings_qs, filters, warnings = _booking_queryset_with_filters(request)
    page_number = request.GET.get("page")
    for warning in warnings:
        messages.warning(request, warning)

    page_obj = Paginator(bookings_qs, 20).get_page(page_number)
    bookings = list(page_obj.object_list)
    for index, lead in enumerate(bookings):
        bookings[index] = _decorate_booking_lead(lead)

    total_bookings = Lead.objects.filter(page="booking").count()
    today_bookings = Lead.objects.filter(page="booking", created_at__date=timezone.localdate()).count()
    specialty_values = list(
        Lead.objects.filter(page="booking")
        .exclude(booking_specialty="")
        .order_by()
        .values_list("booking_specialty", flat=True)
        .distinct()
    )
    specialty_options = [
        {"value": value, "label": _translate_admin_text(value, "Specialty")}
        for value in specialty_values
    ]
    latest_booking_id = int(bookings[0].id) if bookings else 0

    return render(
        request,
        "dashboard/bookings/list.html",
        {
            "bookings": bookings,
            "page_obj": page_obj,
            "total_bookings": total_bookings,
            "today_bookings": today_bookings,
            "specialty_options": specialty_options,
            "current_q": filters["q"],
            "current_specialty": filters["specialty"],
            "current_date_from": filters["date_from_raw"],
            "current_date_to": filters["date_to_raw"],
            "latest_booking_id": latest_booking_id,
            "realtime_enabled": True,
        },
    )

@staff_required
def booking_feed(request):
    bookings_qs, _, _ = _booking_queryset_with_filters(request)
    try:
        last_id = int(request.GET.get("last_id") or 0)
    except ValueError:
        last_id = 0

    new_rows_qs = bookings_qs.filter(id__gt=last_id).order_by("id")
    rows = []
    latest_id = last_id

    for lead in new_rows_qs:
        decorated = _decorate_booking_lead(lead)
        latest_id = max(latest_id, int(decorated.id))
        rows.append(
            {
                "id": decorated.id,
                "name": decorated.name,
                "phone": decorated.phone or "",
                "email": decorated.email or "",
                "booking_date": decorated.display_booking_date,
                "booking_specialty": decorated.display_booking_specialty,
                "booking_service": decorated.display_booking_service,
                "note": decorated.display_note,
                "created_at_text": decorated.display_created_at,
                "ack_sent_at": decorated.display_ack_sent_at,
                "can_send_ack": decorated.can_send_ack,
            }
        )

    return JsonResponse(
        {
            "ok": True,
            "latest_id": latest_id,
            "new_count": len(rows),
            "rows": rows,
            "total_bookings": Lead.objects.filter(page="booking").count(),
            "today_bookings": Lead.objects.filter(page="booking", created_at__date=timezone.localdate()).count(),
            "server_time": timezone.localtime().strftime("%d/%m/%Y %H:%M:%S"),
        }
    )


@staff_required
def booking_send_confirmation_email(request, pk):
    lead = get_object_or_404(Lead, pk=pk, page="booking")
    if request.method != "POST":
        return redirect("dashboard:booking_list")

    success, error_message = _send_booking_confirmation_email(lead)
    if success:
        messages.success(
            request,
            _tr(
                f"ÄÃ£ gá»­i email xÃ¡c nháº­n tá»›i {lead.email}.",
                f"Confirmation email sent to {lead.email}.",
            ),
        )
    else:
        messages.error(
            request,
            _tr(
                f"Gá»­i email tháº¥t báº¡i: {error_message}",
                f"Failed to send email: {error_message}",
            ),
        )

    redirect_url = (request.POST.get("next") or "").strip()
    if redirect_url and redirect_url.startswith("/handsviet_admin/"):
        return redirect(redirect_url)
    return redirect("dashboard:booking_list")

@staff_required
def video_list(request):
    sync_service_categories()
    access_filter = request.GET.get("access")
    videos_qs = Video.objects.select_related("category").all()
    if access_filter in {Video.ACCESS_FREE, Video.ACCESS_PAID}:
        videos_qs = videos_qs.filter(access=access_filter)
    videos = list(videos_qs.order_by("title"))
    for video in videos:
        video.display_category_name = _decorate_service_category_name(video.category)
        video.display_title = _translate_admin_text(video.title, "Exercise video")
    return render(
        request,
        "dashboard/videos/list.html",
        {
            "videos": videos,
            "current_access": access_filter or "",
            "total_videos": Video.objects.count(),
            "total_free": Video.objects.filter(access=Video.ACCESS_FREE).count(),
            "total_paid": Video.objects.filter(access=Video.ACCESS_PAID).count(),
        },
    )

@staff_required
def video_create(request):
    sync_service_categories()
    form = VideoForm(request.POST or None)
    if request.method == "POST" and form.is_valid():
        form.save()
        messages.success(request, _tr("ÄÃ£ táº¡o video bÃ i táº­p.", "Exercise video created."))
        return redirect("dashboard:video_list")
    return render(
        request,
        "dashboard/videos/form.html",
        {"form": form, "title": _tr("ThÃªm video", "Add video"), "button_text": _tr("LÆ°u", "Save")},
    )


@staff_required
def video_edit(request, pk):
    sync_service_categories()
    video = get_object_or_404(Video, pk=pk)
    form = VideoForm(request.POST or None, instance=video)
    if request.method == "POST" and form.is_valid():
        form.save()
        messages.success(request, _tr("ÄÃ£ cáº­p nháº­t video.", "Video updated."))
        return redirect("dashboard:video_list")
    return render(
        request,
        "dashboard/videos/form.html",
        {
            "form": form,
            "video": video,
            "title": _tr("Chá»‰nh sá»­a video", "Edit video"),
            "button_text": _tr("LÆ°u", "Save"),
        },
    )


@staff_required
def video_delete(request, pk):
    video = get_object_or_404(Video, pk=pk)
    if request.method == "POST":
        video.delete()
        messages.success(request, _tr("ÄÃ£ xÃ³a video.", "Video deleted."))
        return redirect("dashboard:video_list")
    return render(request, "dashboard/videos/confirm_delete.html", {"video": video})

@staff_required
def therapy_list(request):
    status_filter = request.GET.get("status")
    packages_qs = Package.objects.all()
    if status_filter == "active":
        packages_qs = packages_qs.filter(is_active=True)
    elif status_filter == "inactive":
        packages_qs = packages_qs.filter(is_active=False)
    packages = list(packages_qs.order_by("name"))
    return render(
        request,
        "dashboard/therapies/list.html",
        {
            "packages": packages,
            "current_status": status_filter or "",
            "total_packages": Package.objects.count(),
            "total_active": Package.objects.filter(is_active=True).count(),
            "total_inactive": Package.objects.filter(is_active=False).count(),
        },
    )


@staff_required
def therapy_create(request):
    form = PackageForm(request.POST or None)
    if request.method == "POST" and form.is_valid():
        form.save()
        messages.success(request, _tr("ÄÃ£ táº¡o gÃ³i liá»‡u phÃ¡p.", "Therapy package created."))
        return redirect("dashboard:therapy_list")
    return render(
        request,
        "dashboard/therapies/form.html",
        {"form": form, "title": _tr("ThÃªm liá»‡u phÃ¡p", "Add therapy package"), "button_text": _tr("LÆ°u", "Save")},
    )


@staff_required
def therapy_edit(request, pk):
    package = get_object_or_404(Package, pk=pk)
    form = PackageForm(request.POST or None, instance=package)
    if request.method == "POST" and form.is_valid():
        form.save()
        messages.success(request, _tr("ÄÃ£ cáº­p nháº­t gÃ³i liá»‡u phÃ¡p.", "Therapy package updated."))
        return redirect("dashboard:therapy_list")
    return render(
        request,
        "dashboard/therapies/form.html",
        {
            "form": form,
            "package": package,
            "title": _tr("Chá»‰nh sá»­a liá»‡u phÃ¡p", "Edit therapy package"),
            "button_text": _tr("LÆ°u", "Save"),
        },
    )


@staff_required
def therapy_delete(request, pk):
    package = get_object_or_404(Package, pk=pk)
    if request.method == "POST":
        package.delete()
        messages.success(request, _tr("ÄÃ£ xÃ³a gÃ³i liá»‡u phÃ¡p.", "Therapy package deleted."))
        return redirect("dashboard:therapy_list")
    return render(request, "dashboard/therapies/confirm_delete.html", {"package": package})

@staff_required
def news_list(request):
    sync_news_categories()
    category_slug = (request.GET.get("category") or "").strip()
    page_number = request.GET.get("page")
    articles_qs = NewsArticle.objects.select_related("category", "author").all().order_by("-published_at", "-id")
    if category_slug:
        articles_qs = articles_qs.filter(category__slug=category_slug)
    paginator = Paginator(articles_qs, 12)
    page_obj = paginator.get_page(page_number)
    categories = list(NewsCategory.objects.all().order_by("name"))
    for category in categories:
        _decorate_news_category(category)
    decorated_articles = [_decorate_news_article(article) for article in page_obj.object_list]
    return render(
        request,
        "dashboard/news/list.html",
        {
            "articles": decorated_articles,
            "page_obj": page_obj,
            "categories": categories,
            "current_category": category_slug,
        },
    )


@staff_required
def news_create(request):
    sync_news_categories()
    form = NewsArticleForm(request.POST or None, request.FILES or None)
    if request.method == "POST" and form.is_valid():
        form.save()
        messages.success(request, _tr("ÄÃ£ táº¡o bÃ i viáº¿t.", "Article created."))
        return redirect("dashboard:news_list")
    categories = list(NewsCategory.objects.all())
    return render(
        request,
        "dashboard/news/form.html",
        {
            "categories": categories,
            "form": form,
            "title": _tr("ThÃªm bÃ i viáº¿t", "Add article"),
            "button_text": _tr("LÆ°u", "Save"),
        },
    )


@staff_required
def news_edit(request, pk):
    sync_news_categories()
    categories = list(NewsCategory.objects.all())
    article = get_object_or_404(NewsArticle.objects.select_related("category"), pk=pk)
    form = NewsArticleForm(request.POST or None, request.FILES or None, instance=article)
    if request.method == "POST" and form.is_valid():
        form.save()
        messages.success(request, _tr("ÄÃ£ cáº­p nháº­t bÃ i viáº¿t.", "Article updated."))
        return redirect("dashboard:news_list")
    return render(
        request,
        "dashboard/news/form.html",
        {
            "article": article,
            "categories": categories,
            "form": form,
            "title": _tr("Chá»‰nh sá»­a bÃ i viáº¿t", "Edit article"),
            "button_text": _tr("LÆ°u", "Save"),
        },
    )


@staff_required
def news_delete(request, pk):
    article = get_object_or_404(NewsArticle, pk=pk)
    if request.method == "POST":
        article.delete()
        messages.success(request, _tr("ÄÃ£ xÃ³a bÃ i viáº¿t.", "Article deleted."))
        return redirect("dashboard:news_list")
    return render(request, "dashboard/news/confirm_delete.html", {"article": article})


@staff_required
def news_category_list(request):
    sync_news_categories()
    categories = list(NewsCategory.objects.all())
    for category in categories:
        _decorate_news_category(category)
    return render(request, "dashboard/news/category_list.html", {"categories": categories})


@staff_required
def news_category_create(request):
    sync_news_categories()
    form = NewsCategoryForm(request.POST or None)
    if request.method == "POST" and form.is_valid():
        form.save()
        messages.success(request, _tr("ÄÃ£ táº¡o chuyÃªn má»¥c tin.", "News category created."))
        return redirect("dashboard:news_category_list")
    return render(
        request,
        "dashboard/news/category_form.html",
        {"form": form, "title": _tr("ThÃªm chuyÃªn má»¥c", "Add category"), "button_text": _tr("LÆ°u", "Save")},
    )


@staff_required
def news_category_edit(request, pk):
    sync_news_categories()
    category = get_object_or_404(NewsCategory, pk=pk)
    form = NewsCategoryForm(request.POST or None, instance=category)
    if request.method == "POST" and form.is_valid():
        form.save()
        messages.success(request, _tr("ÄÃ£ cáº­p nháº­t chuyÃªn má»¥c tin.", "News category updated."))
        return redirect("dashboard:news_category_list")
    return render(
        request,
        "dashboard/news/category_form.html",
        {"form": form, "title": _tr("Chá»‰nh sá»­a chuyÃªn má»¥c", "Edit category"), "button_text": _tr("LÆ°u", "Save")},
    )


@staff_required
def news_category_delete(request, pk):
    sync_news_categories()
    category = get_object_or_404(NewsCategory, pk=pk)
    _decorate_news_category(category)
    if request.method == "POST":
        category.delete()
        messages.success(request, _tr("ÄÃ£ xÃ³a chuyÃªn má»¥c tin.", "News category deleted."))
        return redirect("dashboard:news_category_list")
    return render(request, "dashboard/news/category_confirm_delete.html", {"category": category})





