import re
from decimal import Decimal, ROUND_HALF_UP
from urllib.parse import parse_qs, urlparse

from django import forms
from django.contrib.auth import get_user_model
from django.utils.text import slugify
from django.utils.translation import get_language

from .models import Package, NewsArticle, NewsCategory, Service, ServiceCategory, Video
from .news_category_meta import get_news_category_label
from .service_category_meta import get_service_category_label

User = get_user_model()


def _lang_code() -> str:
    code = (get_language() or "en").lower()
    return "en" if code.startswith("en") else "vi"


def _tr(vi_text: str, en_text: str) -> str:
    return en_text if _lang_code() == "en" else vi_text


def _format_vnd(value) -> str:
    amount = Decimal(str(value)).quantize(Decimal("1"), rounding=ROUND_HALF_UP)
    return f"{int(amount):,}".replace(",", ".") + " VND"


def _unique_slug(model, slug_base, instance=None):
    """
    Generate a unique slug for the target model, adding a numeric suffix if needed.
    """
    slug = slug_base
    idx = 2
    qs = model.objects.filter(slug__iexact=slug)
    if instance and instance.pk:
        qs = qs.exclude(pk=instance.pk)
    while qs.exists():
        slug = f"{slug_base}-{idx}"
        qs = model.objects.filter(slug__iexact=slug)
        if instance and instance.pk:
            qs = qs.exclude(pk=instance.pk)
        idx += 1
    return slug


class StyledFormMixin:
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        for field in self.fields.values():
            if isinstance(field.widget, forms.CheckboxInput):
                field.widget.attrs["class"] = (
                    "h-5 w-5 rounded border-slate-300 text-teal-600 focus:ring-teal-500"
                )
            else:
                field.widget.attrs["class"] = (
                    "w-full px-4 py-3 rounded-xl border border-slate-200 "
                    "focus:outline-none focus:ring-2 focus:ring-teal-200 focus:border-teal-500"
                )

    def _set_field_copy(
        self,
        field_name,
        *,
        vi_label=None,
        en_label=None,
        vi_help=None,
        en_help=None,
        vi_placeholder=None,
        en_placeholder=None,
    ):
        field = self.fields.get(field_name)
        if not field:
            return
        if vi_label is not None and en_label is not None:
            field.label = _tr(vi_label, en_label)
        if vi_help is not None and en_help is not None:
            field.help_text = _tr(vi_help, en_help)
        if vi_placeholder is not None and en_placeholder is not None:
            field.widget.attrs["placeholder"] = _tr(vi_placeholder, en_placeholder)

    def _set_choice_labels(self, field_name, vi_en_pairs):
        field = self.fields.get(field_name)
        if not field:
            return
        field.choices = [(value, _tr(vi_label, en_label)) for value, vi_label, en_label in vi_en_pairs]


class DashboardUserCreateForm(StyledFormMixin, forms.Form):
    ROLE_CHOICES = (
        ("staff", "Nhân viên", "Staff"),
        ("user", "Người dùng", "User"),
    )

    username = forms.CharField(max_length=150, label="Username")
    first_name = forms.CharField(max_length=150, required=False, label="First name")
    last_name = forms.CharField(max_length=150, required=False, label="Last name")
    email = forms.EmailField(required=False, label="Email")
    role = forms.ChoiceField(choices=[(value, en) for value, _, en in ROLE_CHOICES], initial="staff", label="Role")
    password1 = forms.CharField(label="Password", widget=forms.PasswordInput())
    password2 = forms.CharField(label="Confirm password", widget=forms.PasswordInput())
    is_active = forms.BooleanField(required=False, initial=True, label="Active")

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self._set_choice_labels("role", self.ROLE_CHOICES)
        self._set_field_copy("username", vi_label="Tên đăng nhập", en_label="Username")
        self._set_field_copy("first_name", vi_label="Họ", en_label="First name")
        self._set_field_copy("last_name", vi_label="Tên", en_label="Last name")
        self._set_field_copy("email", vi_label="Email", en_label="Email")
        self._set_field_copy("role", vi_label="Vai trò", en_label="Role")
        self._set_field_copy("password1", vi_label="Mật khẩu", en_label="Password")
        self._set_field_copy("password2", vi_label="Xác nhận mật khẩu", en_label="Confirm password")
        self._set_field_copy("is_active", vi_label="Hoạt động", en_label="Active")

    def clean_username(self):
        username = (self.cleaned_data.get("username") or "").strip()
        if not username:
            raise forms.ValidationError(_tr("Vui lòng nhập tên đăng nhập.", "Please enter a username."))
        if User.objects.filter(username__iexact=username).exists():
            raise forms.ValidationError(_tr("Tên đăng nhập đã tồn tại.", "This username already exists."))
        return username

    def clean(self):
        cleaned_data = super().clean()
        password1 = cleaned_data.get("password1")
        password2 = cleaned_data.get("password2")
        if password1 and password2 and password1 != password2:
            self.add_error("password2", _tr("Mật khẩu xác nhận không khớp.", "Password confirmation does not match."))
        return cleaned_data

    def save(self):
        username = self.cleaned_data["username"]
        email = (self.cleaned_data.get("email") or "").strip()
        role = self.cleaned_data.get("role") or "staff"
        user = User.objects.create_user(
            username=username,
            email=email,
            password=self.cleaned_data["password1"],
        )
        user.first_name = self.cleaned_data.get("first_name", "")
        user.last_name = self.cleaned_data.get("last_name", "")
        user.is_active = bool(self.cleaned_data.get("is_active"))
        user.is_staff = role == "staff"
        user.save()
        return user


class DashboardUserUpdateForm(StyledFormMixin, forms.ModelForm):
    ROLE_CHOICES = (
        ("staff", "Nhân viên", "Staff"),
        ("user", "Người dùng", "User"),
    )
    role = forms.ChoiceField(choices=[(value, en) for value, _, en in ROLE_CHOICES], label="Role")

    class Meta:
        model = User
        fields = ["first_name", "last_name", "email", "role", "is_active"]

    def __init__(self, *args, **kwargs):
        instance = kwargs.get("instance")
        super().__init__(*args, **kwargs)
        self._set_choice_labels("role", self.ROLE_CHOICES)
        self._set_field_copy("first_name", vi_label="Họ", en_label="First name")
        self._set_field_copy("last_name", vi_label="Tên", en_label="Last name")
        self._set_field_copy("email", vi_label="Email", en_label="Email")
        self._set_field_copy("role", vi_label="Vai trò", en_label="Role")
        self._set_field_copy("is_active", vi_label="Hoạt động", en_label="Active")
        if instance:
            self.fields["role"].initial = "staff" if instance.is_staff or instance.is_superuser else "user"
            if instance.is_superuser:
                self.fields["role"].disabled = True
                self.fields["role"].help_text = _tr(
                    "Tài khoản superuser luôn thuộc nhóm quản trị.",
                    "A superuser account always remains in the admin group.",
                )

    def save(self, commit=True):
        user = super().save(commit=False)
        if not user.is_superuser:
            user.is_staff = self.cleaned_data.get("role") == "staff"
        if commit:
            user.save()
        return user


class ServiceCategoryForm(StyledFormMixin, forms.ModelForm):
    class Meta:
        model = ServiceCategory
        fields = ["name", "slug", "description", "icon_svg", "order"]
        widgets = {
            "description": forms.Textarea(attrs={"rows": 4}),
            "icon_svg": forms.Textarea(attrs={"rows": 5}),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self._set_field_copy("name", vi_label="Tên chuyên mục", en_label="Category name")
        self._set_field_copy("slug", vi_label="Slug (URL)", en_label="Slug (URL)")
        self._set_field_copy("description", vi_label="Mô tả", en_label="Description")
        self._set_field_copy("icon_svg", vi_label="Mã SVG icon", en_label="SVG icon code")
        self._set_field_copy("order", vi_label="Thứ tự", en_label="Sort order")
        self._set_field_copy(
            "name",
            vi_placeholder="Ví dụ: Phục hồi vận động",
            en_placeholder="Example: Mobility rehabilitation",
        )
        self._set_field_copy(
            "slug",
            vi_placeholder="tu-dong-tao-neu-de-trong",
            en_placeholder="auto-generated-if-empty",
        )
        self._set_field_copy(
            "description",
            vi_placeholder="Mô tả ngắn cho chuyên mục",
            en_placeholder="Short description for this category",
        )
        self._set_field_copy(
            "icon_svg",
            vi_placeholder="<svg>...</svg>",
            en_placeholder="<svg>...</svg>",
        )

    def clean_slug(self):
        name = self.cleaned_data.get("name", "")
        slug = self.cleaned_data.get("slug") or slugify(name, allow_unicode=False)
        slug = slugify(slug, allow_unicode=False)
        if not slug:
            raise forms.ValidationError(
                _tr(
                    "Slug không hợp lệ; vui lòng dùng chữ, số, dấu '-' hoặc '_'.",
                    "Invalid slug. Use letters, numbers, '-' or '_'.",
                )
            )
        return _unique_slug(ServiceCategory, slug, self.instance)


class ServiceForm(StyledFormMixin, forms.ModelForm):
    CYCLE_UNIT_CHOICES = (
        ("week", "Tuần", "Week"),
        ("month", "Tháng", "Month"),
        ("year", "Năm", "Year"),
    )
    CYCLE_UNIT_LABELS = {
        "vi": {"week": "tuần", "month": "tháng", "year": "năm"},
        "en": {"week": "week", "month": "month", "year": "year"},
    }

    slug = forms.CharField(required=False, label="Slug (URL)")
    cycle_unit = forms.ChoiceField(
        choices=[(value, en) for value, _, en in CYCLE_UNIT_CHOICES],
        initial="month",
        label="Billing cycle",
    )
    cycle_count = forms.IntegerField(
        min_value=1,
        initial=1,
        label="Cycle count",
        widget=forms.NumberInput(attrs={"min": "1", "step": "1", "inputmode": "numeric"}),
    )
    unit_price = forms.DecimalField(
        min_value=0,
        decimal_places=0,
        max_digits=12,
        initial=0,
        label="Unit price / cycle (VND)",
        widget=forms.NumberInput(attrs={"min": "0", "step": "1000", "inputmode": "numeric"}),
    )
    total_price_preview = forms.CharField(
        required=False,
        label="Total service price",
        widget=forms.TextInput(attrs={"readonly": "readonly"}),
    )

    class Meta:
        model = Service
        fields = [
            "title",
            "slug",
            "category",
            "summary",
            "price_text",
            "duration",
            "featured_tag",
            "is_featured",
            "order",
            "thumbnail",
        ]
        widgets = {
            "summary": forms.Textarea(attrs={"rows": 4}),
            "price_text": forms.HiddenInput(),
            "duration": forms.HiddenInput(),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self._set_choice_labels("cycle_unit", self.CYCLE_UNIT_CHOICES)
        self.fields["price_text"].required = False
        self.fields["duration"].required = False
        self.fields["category"].label_from_instance = lambda obj: get_service_category_label(obj.slug, _lang_code())

        self._set_field_copy("title", vi_label="Tiêu đề dịch vụ", en_label="Service title")
        self._set_field_copy("slug", vi_label="Slug (URL)", en_label="Slug (URL)")
        self._set_field_copy("category", vi_label="Chuyên mục", en_label="Category")
        self._set_field_copy("summary", vi_label="Mô tả ngắn", en_label="Short summary")
        self._set_field_copy("featured_tag", vi_label="Tag nổi bật", en_label="Featured tag")
        self._set_field_copy("is_featured", vi_label="Dịch vụ nổi bật", en_label="Featured service")
        self._set_field_copy("order", vi_label="Thứ tự", en_label="Sort order")
        self._set_field_copy("thumbnail", vi_label="Ảnh đại diện", en_label="Thumbnail")
        self._set_field_copy("cycle_unit", vi_label="Chu kỳ", en_label="Billing cycle")
        self._set_field_copy("cycle_count", vi_label="Số chu kỳ", en_label="Cycle count")
        self._set_field_copy("unit_price", vi_label="Đơn giá / chu kỳ (VND)", en_label="Unit price / cycle (VND)")
        self._set_field_copy("total_price_preview", vi_label="Tổng giá dịch vụ", en_label="Total service price")

        self._set_field_copy(
            "title",
            vi_placeholder="Ví dụ: Gói phục hồi chuyên sâu",
            en_placeholder="Example: Advanced rehabilitation package",
        )
        self._set_field_copy(
            "slug",
            vi_placeholder="tu-dong-tao-neu-de-trong",
            en_placeholder="auto-generated-if-empty",
        )
        self._set_field_copy(
            "summary",
            vi_placeholder="Mô tả ngắn gọn về dịch vụ",
            en_placeholder="Short summary about this service",
        )
        self._set_field_copy(
            "featured_tag",
            vi_placeholder="Ví dụ: HOT",
            en_placeholder="Example: HOT",
        )
        self._set_field_copy(
            "total_price_preview",
            vi_placeholder="Tự động tính",
            en_placeholder="Calculated automatically",
        )

        if self.instance and self.instance.pk:
            cycle_unit, cycle_count = self._extract_cycle(self.instance.duration or "")
            total_price = self._extract_amount(self.instance.price_text or "")

            self.fields["cycle_unit"].initial = cycle_unit
            self.fields["cycle_count"].initial = cycle_count
            self.initial["duration"] = self.instance.duration or ""
            self.initial["price_text"] = self.instance.price_text or ""

            if total_price is not None:
                unit_price = (total_price / Decimal(cycle_count)).quantize(Decimal("1"), rounding=ROUND_HALF_UP)
                self.fields["unit_price"].initial = unit_price
                self.fields["total_price_preview"].initial = _format_vnd(total_price)

    def clean_slug(self):
        title = self.cleaned_data.get("title", "")
        slug = self.cleaned_data.get("slug") or slugify(title, allow_unicode=False)
        slug = slugify(slug, allow_unicode=False)
        if not slug:
            raise forms.ValidationError(
                _tr(
                    "Slug không hợp lệ; vui lòng dùng chữ, số, dấu '-' hoặc '_'.",
                    "Invalid slug. Use letters, numbers, '-' or '_'.",
                )
            )
        return _unique_slug(Service, slug, self.instance)

    @staticmethod
    def _extract_cycle(duration_text: str) -> tuple[str, int]:
        text = (duration_text or "").lower()
        count_match = re.search(r"(\d+)", text)
        count = int(count_match.group(1)) if count_match else 1
        if "tuần" in text or "week" in text:
            unit = "week"
        elif "năm" in text or "year" in text:
            unit = "year"
        else:
            unit = "month"
        return unit, max(1, count)

    @staticmethod
    def _extract_amount(price_text: str) -> Decimal | None:
        digits = re.sub(r"[^\d]", "", price_text or "")
        if not digits:
            return None
        return Decimal(digits)

    def clean(self):
        cleaned = super().clean()
        unit = cleaned.get("cycle_unit")
        cycle_count = cleaned.get("cycle_count")
        unit_price = cleaned.get("unit_price")

        if not unit or not cycle_count or unit_price is None:
            return cleaned

        total_price = (Decimal(unit_price) * Decimal(cycle_count)).quantize(Decimal("1"), rounding=ROUND_HALF_UP)
        duration_label = self.CYCLE_UNIT_LABELS[_lang_code()].get(unit, _tr("tháng", "month"))

        cleaned["duration"] = f"{int(cycle_count)} {duration_label}"
        cleaned["price_text"] = _format_vnd(total_price)
        cleaned["total_price_preview"] = _format_vnd(total_price)
        return cleaned

    def save(self, commit=True):
        instance = super().save(commit=False)
        instance.duration = self.cleaned_data.get("duration", instance.duration)
        instance.price_text = self.cleaned_data.get("price_text", instance.price_text)
        if commit:
            instance.save()
            self.save_m2m()
        return instance


class NewsCategoryForm(StyledFormMixin, forms.ModelForm):
    class Meta:
        model = NewsCategory
        fields = ["name", "slug"]

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self._set_field_copy("name", vi_label="Tên chuyên mục", en_label="Category name")
        self._set_field_copy("slug", vi_label="Slug (URL)", en_label="Slug (URL)")
        self._set_field_copy(
            "name",
            vi_placeholder="Ví dụ: Tin y khoa",
            en_placeholder="Example: Medical updates",
        )
        self._set_field_copy(
            "slug",
            vi_placeholder="tu-dong-tao-neu-de-trong",
            en_placeholder="auto-generated-if-empty",
        )

    def clean_slug(self):
        name = self.cleaned_data.get("name", "")
        slug = self.cleaned_data.get("slug") or slugify(name, allow_unicode=False)
        slug = slugify(slug, allow_unicode=False)
        if not slug:
            raise forms.ValidationError(
                _tr(
                    "Slug không hợp lệ; vui lòng dùng chữ, số, dấu '-' hoặc '_'.",
                    "Invalid slug. Use letters, numbers, '-' or '_'.",
                )
            )
        return _unique_slug(NewsCategory, slug, self.instance)


class NewsArticleForm(StyledFormMixin, forms.ModelForm):
    class Meta:
        model = NewsArticle
        fields = [
            "title",
            "slug",
            "category",
            "summary",
            "content",
            "thumbnail",
            "is_published",
        ]
        widgets = {
            "summary": forms.Textarea(attrs={"rows": 3}),
            "content": forms.Textarea(attrs={"rows": 10, "class": "ckeditor"}),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["category"].label_from_instance = lambda obj: (
            get_news_category_label(obj.slug, _lang_code()) or obj.name
        )
        self._set_field_copy("title", vi_label="Tiêu đề bài viết", en_label="Article title")
        self._set_field_copy("slug", vi_label="Slug (URL)", en_label="Slug (URL)")
        self._set_field_copy("category", vi_label="Chuyên mục", en_label="Category")
        self._set_field_copy("summary", vi_label="Mô tả tóm tắt", en_label="Summary")
        self._set_field_copy("content", vi_label="Nội dung bài viết", en_label="Article content")
        self._set_field_copy("thumbnail", vi_label="Ảnh bài viết", en_label="Article image")
        self._set_field_copy("is_published", vi_label="Đăng bài", en_label="Publish article")
        self._set_field_copy(
            "title",
            vi_placeholder="Ví dụ: Cập nhật điều trị phục hồi",
            en_placeholder="Example: Rehabilitation treatment update",
        )
        self._set_field_copy(
            "slug",
            vi_placeholder="tu-dong-tao-neu-de-trong",
            en_placeholder="auto-generated-if-empty",
        )
        self._set_field_copy(
            "summary",
            vi_placeholder="Tóm tắt ngắn cho bài viết",
            en_placeholder="Short summary for this article",
        )
        self._set_field_copy(
            "content",
            vi_placeholder="Nhập nội dung HTML của bài viết",
            en_placeholder="Enter the HTML content for this article",
        )

    def clean_slug(self):
        title = self.cleaned_data.get("title", "")
        slug = self.cleaned_data.get("slug") or slugify(title, allow_unicode=False)
        slug = slugify(slug, allow_unicode=False)
        if not slug:
            raise forms.ValidationError(
                _tr(
                    "Slug không hợp lệ; vui lòng dùng chữ, số, dấu '-' hoặc '_'.",
                    "Invalid slug. Use letters, numbers, '-' or '_'.",
                )
            )
        return _unique_slug(NewsArticle, slug, self.instance)


class VideoForm(StyledFormMixin, forms.ModelForm):
    slug = forms.CharField(required=False)

    class Meta:
        model = Video
        fields = [
            "title",
            "slug",
            "provider",
            "provider_id",
            "access",
            "duration",
            "category",
            "is_active",
        ]

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["category"].label_from_instance = lambda obj: get_service_category_label(obj.slug, _lang_code())
        self._set_field_copy("title", vi_label="Tên video", en_label="Video title")
        self._set_field_copy("slug", vi_label="Đường dẫn (slug)", en_label="Slug")
        self._set_field_copy("provider", vi_label="Nền tảng", en_label="Provider")
        self._set_field_copy("provider_id", vi_label="Mã video", en_label="Video ID")
        self._set_field_copy("access", vi_label="Quyền truy cập", en_label="Access")
        self._set_field_copy("duration", vi_label="Thời lượng", en_label="Duration")
        self._set_field_copy("category", vi_label="Danh mục", en_label="Category")
        self._set_field_copy("is_active", vi_label="Đang hoạt động", en_label="Active")
        self._set_field_copy(
            "provider_id",
            vi_help="Dán ID hoặc full URL YouTube/Vimeo, hệ thống sẽ tự nhận diện.",
            en_help="Paste the ID or full YouTube/Vimeo URL. The system will detect it automatically.",
        )
        self._set_field_copy(
            "is_active",
            vi_help="Bật để hiển thị video ngoài website.",
            en_help="Enable to show this video on the public website.",
        )
        self._set_field_copy(
            "title",
            vi_placeholder="Ví dụ: Bài tập khởi động vai",
            en_placeholder="Example: Shoulder warm-up exercise",
        )
        self._set_field_copy(
            "slug",
            vi_placeholder="tu-dong-tao-neu-de-trong",
            en_placeholder="auto-generated-if-empty",
        )
        self._set_field_copy(
            "provider_id",
            vi_placeholder="YouTube ID hoặc URL",
            en_placeholder="YouTube ID or URL",
        )
        self._set_field_copy(
            "duration",
            vi_placeholder="Ví dụ: 15 phút",
            en_placeholder="Example: 15 minutes",
        )

    def clean_slug(self):
        title = self.cleaned_data.get("title", "")
        slug = self.cleaned_data.get("slug") or slugify(title, allow_unicode=False)
        slug = slugify(slug, allow_unicode=False)
        if not slug:
            raise forms.ValidationError(
                _tr(
                    "Slug không hợp lệ; vui lòng dùng chữ, số, dấu '-' hoặc '_'.",
                    "Invalid slug. Use letters, numbers, '-' or '_'.",
                )
            )
        return _unique_slug(Video, slug, self.instance)

    def clean_provider_id(self):
        raw = (self.cleaned_data.get("provider_id") or "").strip()
        provider = self.cleaned_data.get("provider")
        if not raw:
            raise forms.ValidationError(_tr("Vui lòng nhập mã video hoặc URL.", "Please enter a video ID or URL."))

        if provider == Video.PROVIDER_YT:
            return self._extract_youtube_id(raw)
        if provider == Video.PROVIDER_VI:
            return self._extract_vimeo_id(raw)
        return raw

    def _extract_youtube_id(self, value):
        if "://" not in value:
            return value

        parsed = urlparse(value)
        host = (parsed.netloc or "").lower().replace("www.", "")
        path = parsed.path.strip("/")

        if host == "youtu.be" and path:
            return path.split("/")[0]
        if host in {"youtube.com", "m.youtube.com"}:
            if path == "watch":
                vid = parse_qs(parsed.query).get("v", [None])[0]
                if vid:
                    return vid
            if path.startswith("embed/") or path.startswith("shorts/"):
                return path.split("/", 1)[1].split("/")[0]

        raise forms.ValidationError(_tr("URL YouTube không hợp lệ.", "Invalid YouTube URL."))

    def _extract_vimeo_id(self, value):
        if "://" not in value:
            return value
        parsed = urlparse(value)
        host = (parsed.netloc or "").lower().replace("www.", "")
        path = parsed.path.strip("/")
        if host == "vimeo.com" and path:
            return path.split("/")[0]
        if host == "player.vimeo.com" and path.startswith("video/"):
            return path.split("/", 1)[1].split("/")[0]
        raise forms.ValidationError(_tr("URL Vimeo không hợp lệ.", "Invalid Vimeo URL."))


class PackageForm(StyledFormMixin, forms.ModelForm):
    class Meta:
        model = Package
        fields = ["name", "slug", "description", "duration_days", "price", "is_active"]
        widgets = {
            "description": forms.Textarea(attrs={"rows": 4}),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self._set_field_copy("name", vi_label="Tên gói liệu pháp", en_label="Package name")
        self._set_field_copy("slug", vi_label="Đường dẫn (slug)", en_label="Slug")
        self._set_field_copy("description", vi_label="Mô tả", en_label="Description")
        self._set_field_copy("duration_days", vi_label="Thời lượng (ngày)", en_label="Duration (days)")
        self._set_field_copy("price", vi_label="Giá", en_label="Price")
        self._set_field_copy("is_active", vi_label="Đang hoạt động", en_label="Active")
        self._set_field_copy(
            "is_active",
            vi_help="Bật để cho phép người dùng mua gói này.",
            en_help="Enable to allow users to purchase this package.",
        )
        self._set_field_copy(
            "name",
            vi_placeholder="Ví dụ: Gói 12 buổi",
            en_placeholder="Example: 12-session package",
        )
        self._set_field_copy(
            "slug",
            vi_placeholder="tu-dong-tao-neu-de-trong",
            en_placeholder="auto-generated-if-empty",
        )
        self._set_field_copy(
            "description",
            vi_placeholder="Mô tả ngắn cho gói liệu pháp",
            en_placeholder="Short description for this package",
        )

    def clean_slug(self):
        name = self.cleaned_data.get("name", "")
        slug = self.cleaned_data.get("slug") or slugify(name, allow_unicode=False)
        slug = slugify(slug, allow_unicode=False)
        if not slug:
            raise forms.ValidationError(
                _tr(
                    "Slug không hợp lệ; vui lòng dùng chữ, số, dấu '-' hoặc '_'.",
                    "Invalid slug. Use letters, numbers, '-' or '_'.",
                )
            )
        return _unique_slug(Package, slug, self.instance)
