"""Registry of (category, task_family) -> Template class.

Phase 4 landing has only one worked template (CU × Scheduling). Other 13
templates from spec §4.2 register here as they land.
"""

from __future__ import annotations

from clawsocialarena.generator.template import (
    CategoryCode,
    TaskFamily,
    Template,
)
from clawsocialarena.generator.templates.cu_scheduling import CUSchedulingTemplate


_REGISTRY: dict[tuple[CategoryCode, TaskFamily], type[Template]] = {
    (CategoryCode.CU, TaskFamily.SCHEDULING): CUSchedulingTemplate,
}


def get_template(category: CategoryCode, task_family: TaskFamily) -> Template:
    key = (category, task_family)
    if key not in _REGISTRY:
        raise KeyError(
            f"no template registered for ({category.value}, {task_family.value}). "
            f"Registered: {[(c.value, t.value) for c, t in _REGISTRY.keys()]}"
        )
    return _REGISTRY[key]()


def list_registered() -> list[tuple[CategoryCode, TaskFamily]]:
    return list(_REGISTRY.keys())
