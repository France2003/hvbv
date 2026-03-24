from django.conf import settings
from django.core.management.base import BaseCommand
from django.core.mail import send_mail
from django.utils import timezone

from hansviet_admin.models import Purchase


def _parse_recipients(value) -> list[str]:
    if isinstance(value, str):
        candidates = [item.strip() for item in value.split(",")]
    elif isinstance(value, (list, tuple, set)):
        candidates = [str(item).strip() for item in value]
    else:
        candidates = [str(value).strip()] if value else []
    return [email for email in candidates if email]


def _normalize_days(values) -> list[int]:
    out = []
    for value in values:
        try:
            day = int(value)
        except (TypeError, ValueError):
            continue
        if day <= 0:
            continue
        if day not in out:
            out.append(day)
    return sorted(out, reverse=True)


def _parse_days_setting(value) -> list[int]:
    if isinstance(value, (list, tuple, set)):
        return _normalize_days(value)
    raw = str(value or "").strip()
    if not raw:
        return []
    return _normalize_days(part.strip() for part in raw.split(","))


class Command(BaseCommand):
    help = "Send email reminders for packages that will expire in configured days (e.g. 3 and 2 days)."

    def add_arguments(self, parser):
        parser.add_argument(
            "--days",
            action="append",
            type=int,
            dest="days_list",
            help="Reminder window in days. Repeat to pass multiple values, e.g. --days 3 --days 2.",
        )
        parser.add_argument("--dry-run", action="store_true", help="Preview only, do not send emails or update DB.")

    def handle(self, *args, **options):
        now = timezone.now()
        today = timezone.localdate()

        cli_days = options.get("days_list") or []
        if cli_days:
            reminder_days = _normalize_days(cli_days)
        else:
            reminder_days = _parse_days_setting(getattr(settings, "PACKAGE_EXPIRY_REMINDER_DAYS", "3"))
        if not reminder_days:
            reminder_days = [3]
        reminder_days_set = set(reminder_days)

        dry_run = bool(options.get("dry_run"))

        qs = (
            Purchase.objects.select_related("user", "package")
            .filter(status="active", expires_at__gt=now)
            .order_by("expires_at")
        )

        contact_recipients = _parse_recipients(getattr(settings, "EXPIRY_REMINDER_CONTACT_EMAIL", ""))
        sent_count = 0
        skipped_count = 0
        failed_count = 0

        for purchase in qs:
            days_left = (timezone.localtime(purchase.expires_at).date() - today).days
            if days_left not in reminder_days_set:
                skipped_count += 1
                continue

            sent_days_raw = purchase.expiry_reminder_days_sent
            if not isinstance(sent_days_raw, list):
                sent_days_raw = []
            sent_days = set()
            for item in sent_days_raw:
                try:
                    sent_days.add(int(item))
                except (TypeError, ValueError):
                    continue
            if days_left in sent_days:
                skipped_count += 1
                continue

            user_email = (purchase.user.email or "").strip()
            if not user_email:
                skipped_count += 1
                self.stdout.write(
                    self.style.WARNING(
                        f"Skip purchase #{purchase.pk}: user '{purchase.user}' has no email."
                    )
                )
                continue

            expires_at_text = timezone.localtime(purchase.expires_at).strftime("%d/%m/%Y %H:%M")
            subject = f"[HandsViet] Gói '{purchase.package.name}' sẽ hết hạn sau {days_left} ngày"
            message = (
                f"Xin chào {purchase.user.get_full_name() or purchase.user.username},\n\n"
                f"Gói tập '{purchase.package.name}' của bạn sẽ hết hạn vào {expires_at_text}.\n"
                f"Thời gian còn lại: {days_left} ngày.\n\n"
                "Bạn vui lòng gia hạn gói để không bị gián đoạn quyền truy cập bài tập.\n\n"
                "Trân trọng,\n"
                "HandsViet."
            )

            internal_subject = f"[Expiry Reminder] {purchase.package.name} - {purchase.user.username}"
            internal_message = (
                "Hệ thống vừa gửi email nhắc hết hạn gói tập.\n\n"
                f"- User: {purchase.user.username}\n"
                f"- Email: {user_email}\n"
                f"- Gói: {purchase.package.name}\n"
                f"- Hết hạn: {expires_at_text}\n"
                f"- Days left: {days_left}\n"
            )

            if dry_run:
                sent_count += 1
                self.stdout.write(
                    f"[DRY-RUN] Would send {days_left}-day reminder for purchase #{purchase.pk} to {user_email}."
                )
                continue

            try:
                send_mail(
                    subject=subject,
                    message=message,
                    from_email=getattr(settings, "DEFAULT_FROM_EMAIL", ""),
                    recipient_list=[user_email],
                    fail_silently=False,
                )
                if contact_recipients:
                    send_mail(
                        subject=internal_subject,
                        message=internal_message,
                        from_email=getattr(settings, "DEFAULT_FROM_EMAIL", ""),
                        recipient_list=contact_recipients,
                        fail_silently=False,
                    )

                sent_days.add(days_left)
                purchase.expiry_reminder_days_sent = sorted(sent_days, reverse=True)
                update_fields = ["expiry_reminder_days_sent"]
                if days_left == 3 and not purchase.expiry_reminder_3d_sent_at:
                    purchase.expiry_reminder_3d_sent_at = timezone.now()
                    update_fields.append("expiry_reminder_3d_sent_at")
                purchase.save(update_fields=update_fields)
                sent_count += 1
            except Exception as exc:
                failed_count += 1
                self.stdout.write(
                    self.style.ERROR(
                        f"Failed sending reminder for purchase #{purchase.pk} ({user_email}): {exc}"
                    )
                )

        self.stdout.write(
            self.style.SUCCESS(
                f"Done. sent={sent_count}, skipped={skipped_count}, failed={failed_count}, "
                f"days={reminder_days}, dry_run={dry_run}"
            )
        )
