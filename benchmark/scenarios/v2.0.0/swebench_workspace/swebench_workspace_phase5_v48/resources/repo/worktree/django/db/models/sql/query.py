# Reduced source stub for django/db/models/sql/query.py.
# Reconstructed from the SWE-bench gold patch context.


def clone(self):
            obj.annotation_select_mask = None
        else:
            obj.annotation_select_mask = self.annotation_select_mask.copy()
        # _annotation_select_cache cannot be copied, as doing so breaks the
        # (necessary) state in which both annotations and
        # _annotation_select_cache point to the same underlying objects.

def split_exclude(self, filter_expr, can_reuse, names_with_path):

    def set_empty(self):
        self.where.add(NothingNode(), AND)

    def is_empty(self):
        return any(isinstance(c, NothingNode) for c in self.where.children)
