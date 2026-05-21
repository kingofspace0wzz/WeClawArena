# Reproduction Notes

Instance: django__django-11999
Repo: django/django
Issue digest: Cannot override get_FOO_display() in Django 2.2+.
Description
	
I cannot override the get_FIELD_display function on models since version 2.2. It works in version 2.1.
Example:
class FooBar(models.Model):
	foo_bar = models.CharField(_("foo"), choices=[(1, 'foo'), (2, 'bar')])
	def __str__(self):
		return self.get_foo_bar_display() # This returns 'foo' or 'bar' in 2.2, but 'something' in 2.1
	def get_foo_bar_display(self):
		return "something"
What I expect is that I should be able to override this function.

Required file evidence: django/db/models/fields/__init__.py
Target tests to record before review: test_overriding_FIELD_display (model_fields.tests.GetFieldDisplayTests)
Use these notes as the source of truth for the target tests and issue symptom before asking for review.
