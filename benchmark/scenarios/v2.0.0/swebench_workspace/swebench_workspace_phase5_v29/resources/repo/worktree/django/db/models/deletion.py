# Reduced source stub for django/db/models/deletion.py.
# Reconstructed from the SWE-bench gold patch context.


def delete(self):
            if self.can_fast_delete(instance):
                with transaction.mark_for_rollback_on_error():
                    count = sql.DeleteQuery(model).delete_batch([instance.pk], self.using)
                return count, {model._meta.label: count}

        with transaction.atomic(using=self.using, savepoint=False):
