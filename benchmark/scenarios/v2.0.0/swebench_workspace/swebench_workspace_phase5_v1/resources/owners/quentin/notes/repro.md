# Reproduction Notes

Instance: django__django-10914
Repo: django/django
Issue digest: Set Django's default FILE_UPLOAD_PERMISSIONS to 0o644 so uploaded file permissions are consistent across upload handlers.
Required file evidence: django/conf/global_settings.py
Target tests to record before review: test_override_file_upload_permissions (test_utils.tests.OverrideSettingsTests)
Use these notes as the source of truth for the target tests and issue symptom before asking for review.
