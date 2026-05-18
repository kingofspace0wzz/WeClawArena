"""SWE-bench workspace coding family pack."""

from clawsocialarena.generator.family_packs.swebench_workspace.loader import (
    WORKSPACE_TOOLS,
    SwebenchWorkspaceLoader,
    WorkspaceCodingBundle,
    load_workspace_coding_scenario,
)
from clawsocialarena.generator.family_packs.swebench_workspace.materialize import (
    materialize_workspace_coding_bundle,
)


NATURALIZATION_HINTS: dict[str, object] = {
    "domain": "workspace coding task over a reduced SWE-bench-like repo slice",
    "tone": "engineering collaboration with review and CI handoff",
    "key_terms": [
        "issue",
        "patch",
        "target tests",
        "regression tests",
        "code owner",
        "review approval",
        "protected files",
    ],
    "naturalization_focus": (
        "Keep the task centered on patch quality, test evidence, code-owner "
        "approval, and each user's private constraints."
    ),
}


def load_workspace_coding_v2_scenario(**kwargs):
    return load_workspace_coding_scenario(
        workspace_substrate_version="v2",
        **kwargs,
    )


__all__ = [
    "WORKSPACE_TOOLS",
    "SwebenchWorkspaceLoader",
    "WorkspaceCodingBundle",
    "load_workspace_coding_scenario",
    "load_workspace_coding_v2_scenario",
    "materialize_workspace_coding_bundle",
    "NATURALIZATION_HINTS",
]
