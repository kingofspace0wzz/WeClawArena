# Risk Notes

Problem behavior to preserve outside the fix: Set Django's default FILE_UPLOAD_PERMISSIONS to 0o644 so uploaded file permissions are consistent across upload handlers.
Review risk marker: DJANGO-DJANGO-10914-REVIEW-RISK.
Do not approve unrelated cleanup just because the diff is small.
