from django.contrib.auth import get_user_model
from django.db import models
from django.utils import timezone


class ServiceCategory(models.Model):
    name = models.CharField(max_length=255)
    slug = models.SlugField(unique=True)
    description = models.TextField(blank=True)
    icon_svg = models.TextField(blank=True)
    order = models.PositiveIntegerField(default=0)

    class Meta:
        ordering = ["order", "name"]
        verbose_name = "Service Category"
        verbose_name_plural = "Service Categories"

    def __str__(self):
        return self.name


class Service(models.Model):
    category = models.ForeignKey(ServiceCategory, on_delete=models.SET_NULL, null=True, blank=True)
    title = models.CharField(max_length=255)
    slug = models.SlugField(unique=True)
    summary = models.TextField(blank=True)
    price_text = models.CharField(max_length=255, blank=True)
    duration = models.CharField(max_length=255, blank=True)
    featured_tag = models.CharField(max_length=100, blank=True)
    is_featured = models.BooleanField(default=False)
    order = models.PositiveIntegerField(default=0)
    thumbnail = models.FileField(upload_to="services/", blank=True, null=True)

    class Meta:
        ordering = ["order", "title"]
        verbose_name = "Service"
        verbose_name_plural = "Services"

    def __str__(self):
        return self.title

    def get_absolute_url(self):
        return f"/services/{self.slug}/"


class NewsCategory(models.Model):
    name = models.CharField(max_length=255)
    slug = models.SlugField(unique=True)

    class Meta:
        verbose_name = "News Category"
        verbose_name_plural = "News Categories"
        ordering = ["name"]

    def __str__(self):
        return self.name


class NewsArticle(models.Model):
    category = models.ForeignKey(NewsCategory, on_delete=models.SET_NULL, null=True, blank=True)
    title = models.CharField(max_length=255)
    title_en = models.CharField(max_length=255, blank=True, default="")
    slug = models.SlugField(unique=True)
    summary = models.TextField(blank=True)
    summary_en = models.TextField(blank=True, default="")
    content = models.TextField(blank=True)
    content_en = models.TextField(blank=True, default="")
    thumbnail = models.FileField(upload_to="news/", blank=True, null=True)
    author = models.ForeignKey(get_user_model(), on_delete=models.SET_NULL, null=True, blank=True)
    published_at = models.DateTimeField(auto_now_add=True)
    view_count = models.PositiveIntegerField(default=0)
    is_published = models.BooleanField(default=False)
    source_url = models.URLField(blank=True)
    source_name = models.CharField(max_length=255, blank=True)
    ai_source = models.CharField(max_length=100, blank=True)
    is_auto_generated = models.BooleanField(default=False)
    needs_review = models.BooleanField(default=True)

    class Meta:
        ordering = ["-published_at"]
        verbose_name = "News Article"
        verbose_name_plural = "News Articles"

    def __str__(self):
        return self.title


class Lead(models.Model):
    """Lưu đăng ký tư vấn / liên hệ nhanh từ website marketing."""

    name = models.CharField(max_length=255)
    phone = models.CharField(max_length=50, blank=True)
    email = models.EmailField(blank=True)
    message = models.TextField(blank=True)
    page = models.CharField(max_length=255, blank=True)
    booking_date = models.DateField(null=True, blank=True)
    booking_specialty = models.CharField(max_length=255, blank=True)
    booking_service = models.CharField(max_length=255, blank=True)
    booking_ack_sent_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-created_at"]
        verbose_name = "Lead"
        verbose_name_plural = "Leads"

    def __str__(self):
        return f"{self.name} - {self.phone or self.email}"


class Package(models.Model):
    name = models.CharField(max_length=255)
    slug = models.SlugField(unique=True)
    description = models.TextField(blank=True)
    duration_days = models.PositiveIntegerField()
    price = models.DecimalField(max_digits=12, decimal_places=2)
    is_active = models.BooleanField(default=True)

    class Meta:
        verbose_name = "Package"
        verbose_name_plural = "Packages"
        ordering = ["name"]

    def __str__(self):
        return self.name


class Purchase(models.Model):
    user = models.ForeignKey(get_user_model(), on_delete=models.CASCADE)
    package = models.ForeignKey(Package, on_delete=models.CASCADE)
    started_at = models.DateTimeField(auto_now_add=True)
    expires_at = models.DateTimeField()
    status = models.CharField(max_length=20, default="active")  # active/expired/canceled
    payment_ref = models.CharField(max_length=100, blank=True)
    expiry_reminder_3d_sent_at = models.DateTimeField(null=True, blank=True)
    expiry_reminder_days_sent = models.JSONField(default=list, blank=True)

    class Meta:
        verbose_name = "Purchase"
        verbose_name_plural = "Purchases"
        ordering = ["-started_at"]

    def __str__(self):
        return f"{self.user} - {self.package}"


class Video(models.Model):
    ACCESS_FREE = "free"
    ACCESS_PAID = "paid"
    ACCESS_CHOICES = [(ACCESS_FREE, "Free"), (ACCESS_PAID, "Paid")]

    PROVIDER_YT = "youtube"
    PROVIDER_VI = "vimeo"
    PROVIDER_CHOICES = [(PROVIDER_YT, "YouTube"), (PROVIDER_VI, "Vimeo")]

    title = models.CharField(max_length=255)
    slug = models.SlugField(unique=True)
    provider = models.CharField(max_length=20, choices=PROVIDER_CHOICES)
    provider_id = models.CharField(max_length=255)
    access = models.CharField(max_length=10, choices=ACCESS_CHOICES, default=ACCESS_FREE)
    duration = models.CharField(max_length=50, blank=True)
    category = models.ForeignKey(ServiceCategory, null=True, blank=True, on_delete=models.SET_NULL)
    is_active = models.BooleanField(default=True)

    class Meta:
        verbose_name = "Video"
        verbose_name_plural = "Videos"
        ordering = ["title"]

    def __str__(self):
        return self.title


class SessionSchedule(models.Model):
    user = models.ForeignKey(get_user_model(), on_delete=models.CASCADE)
    package = models.ForeignKey(Package, null=True, blank=True, on_delete=models.SET_NULL)
    title = models.CharField(max_length=255)
    start_at = models.DateTimeField()
    end_at = models.DateTimeField()
    is_zoom = models.BooleanField(default=False)
    zoom_join_url = models.URLField(blank=True)
    zoom_meeting_id = models.CharField(max_length=100, blank=True)

    class Meta:
        verbose_name = "Session Schedule"
        verbose_name_plural = "Session Schedules"
        ordering = ["-start_at"]

    def __str__(self):
        return f"{self.title} - {self.start_at}"


class PatientProfile(models.Model):
    user = models.OneToOneField(get_user_model(), on_delete=models.CASCADE)
    condition = models.TextField(blank=True)
    notes = models.TextField(blank=True)

    class Meta:
        verbose_name = "Patient Profile"
        verbose_name_plural = "Patient Profiles"

    def __str__(self):
        return f"Hồ sơ {self.user}"


class ProgressNote(models.Model):
    profile = models.ForeignKey(PatientProfile, on_delete=models.CASCADE)
    recorded_at = models.DateTimeField(auto_now_add=True)
    summary = models.TextField()
    score = models.IntegerField(null=True, blank=True)  # thang điểm tiến trình

    class Meta:
        verbose_name = "Progress Note"
        verbose_name_plural = "Progress Notes"
        ordering = ["-recorded_at"]

    def __str__(self):
        return f"Note {self.recorded_at}"


class ExerciseProfile(models.Model):
    user = models.OneToOneField(get_user_model(), on_delete=models.CASCADE)
    goals = models.TextField(blank=True)
    contraindications = models.TextField(blank=True)
    current_level = models.CharField(max_length=100, blank=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = "Exercise Profile"
        verbose_name_plural = "Exercise Profiles"

    def __str__(self):
        return f"Exercise Profile {self.user}"


class ExerciseLog(models.Model):
    user = models.ForeignKey(get_user_model(), on_delete=models.CASCADE)
    exercise_name = models.CharField(max_length=255)
    category = models.CharField(max_length=255, blank=True)
    duration_minutes = models.PositiveIntegerField(default=0)
    pain_score = models.PositiveSmallIntegerField(default=0)
    notes = models.TextField(blank=True)
    trained_at = models.DateTimeField(default=timezone.now)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        verbose_name = "Exercise Log"
        verbose_name_plural = "Exercise Logs"
        ordering = ["-trained_at", "-created_at"]

    def __str__(self):
        return f"{self.user} - {self.exercise_name}"


class Transaction(models.Model):
    user = models.ForeignKey(get_user_model(), on_delete=models.CASCADE, null=True, blank=True)
    package = models.ForeignKey(Package, on_delete=models.SET_NULL, null=True, blank=True)
    amount = models.DecimalField(max_digits=12, decimal_places=2)
    status = models.CharField(max_length=20, default="pending")  # pending/success/failed
    txn_ref = models.CharField(max_length=64, unique=True)
    raw_params = models.JSONField(default=dict)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        verbose_name = "Transaction"
        verbose_name_plural = "Transactions"
        ordering = ["-created_at"]

    def __str__(self):
        return f"{self.txn_ref} - {self.status}"
