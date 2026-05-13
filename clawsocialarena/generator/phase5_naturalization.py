"""Adapter that wraps :func:`run_naturalization` for the publish script.

:class:`Phase5NaturalizationClient` satisfies the
``NaturalizationClient`` Protocol defined in
``scripts/publish_phase5_scenarios.py``:

    class NaturalizationClient(Protocol):
        def naturalize(self, *, base_dir: Path) -> dict[str, Any]: ...

Responsibilities:

1. Read ``scenario.json``, ``scenario.gt.json``, and
   ``family_pack_context.json`` from ``base_dir``.
2. Extract ``family_id``, ``scenario_id``, and ``cell_id`` from those
   files (``family_id`` may live in ``scenario.json`` directly or in
   ``scenario.gt.json``'s ``construction_manifest`` block).
3. Call :func:`build_family_pack_skeleton` to assemble the
   naturalization input payload.
4. Call :func:`run_naturalization` with the skeleton payload.
5. Convert the returned :class:`NaturalizationPatch` into the dict
   shape expected by the publish script.

The returned dict shape:

    {
        "naturalization_status": "ok",
        "personas": {
            "<agent_id>": {"system_md": "<persona note text>", "tools_json": {}}
        },
        "rendered_scenario_overrides": {"opening_message": "<...>"},
        "tokens_used": {"prompt": <int>, "completion": <int>},
    }

``personas`` is built from ``patch.scenario_patch.persona_notes``
(a ``dict[str, str]`` of agent_id -> plain text note).  The note
becomes ``system_md``; ``tools_json`` defaults to ``{}``.

``rendered_scenario_overrides`` carries the naturalized
``opening_message`` so the publish script can merge it into
``scenario.json``.

``tokens_used`` maps ``input_tokens`` to ``"prompt"`` and
``output_tokens`` to ``"completion"`` for compatibility with the
publish script's ``PublishOutcome.tokens_used`` accumulator.
"""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from clawsocialarena.generator.family_pack_skeleton import build_family_pack_skeleton
from clawsocialarena.generator.naturalization import (
    NaturalizationPatch,
    run_naturalization,
)
from clawsocialarena.llm.openai_client import JsonClient, OpenAIResponsesJsonClient


def _read_json(path: Path) -> dict[str, Any]:
    if not path.is_file():
        return {}
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return {}
    return data if isinstance(data, dict) else {}


def _extract_family_id(
    scenario: dict[str, Any],
    gt: dict[str, Any],
) -> str:
    """Return family_id from the bundle files.

    Preferred source: ``scenario.json``'s top-level ``family_id``.
    Fallback: ``scenario.gt.json``'s ``construction_manifest.family_id``
    (the T5 fix location).
    """
    fid = scenario.get("family_id")
    if isinstance(fid, str) and fid.strip():
        return fid.strip()
    construction = gt.get("construction_manifest")
    if isinstance(construction, dict):
        fid = construction.get("family_id")
        if isinstance(fid, str) and fid.strip():
            return fid.strip()
    raise ValueError(
        "family_id not found in scenario.json or "
        "scenario.gt.json construction_manifest"
    )


def _patch_to_publish_dict(patch: NaturalizationPatch) -> dict[str, Any]:
    """Convert a NaturalizationPatch into the publish-script dict shape."""
    persona_notes: dict[str, str] = dict(patch.scenario_patch.persona_notes or {})
    personas: dict[str, dict[str, Any]] = {
        agent_id: {"system_md": note, "tools_json": {}}
        for agent_id, note in persona_notes.items()
    }
    usage = patch.usage
    tokens_used = {
        "prompt": usage.input_tokens + usage.cached_input_tokens,
        "completion": usage.output_tokens,
    }
    rendered_scenario_overrides: dict[str, Any] = {}
    opening = patch.scenario_patch.opening_message
    if opening:
        rendered_scenario_overrides["opening_message"] = opening
    return {
        "naturalization_status": "ok",
        "personas": personas,
        "rendered_scenario_overrides": rendered_scenario_overrides,
        "tokens_used": tokens_used,
    }


class Phase5NaturalizationClient:
    """Adapter that wires :func:`run_naturalization` to the publish script.

    Parameters
    ----------
    model:
        Model identifier passed through to :func:`run_naturalization`.
    client:
        Optional :class:`JsonClient` instance. Defaults to
        :class:`OpenAIResponsesJsonClient` on first call.
    """

    def __init__(
        self,
        *,
        model: str,
        client: JsonClient | None = None,
    ) -> None:
        self.model = model
        self._client = client

    def _resolve_client(self) -> JsonClient:
        if self._client is None:
            self._client = OpenAIResponsesJsonClient()
        return self._client

    def naturalize(self, *, base_dir: Path) -> dict[str, Any]:
        """Naturalize a pre-built base bundle directory.

        Reads ``scenario.json``, ``scenario.gt.json``, and
        ``family_pack_context.json`` from ``base_dir``, builds the
        skeleton payload, calls ``run_naturalization``, and converts
        the result into the publish-script dict shape.

        Parameters
        ----------
        base_dir:
            Path to the pre-naturalization base directory (the same
            directory the publish script passes after copying scaffold
            files into the store).

        Returns
        -------
        dict
            Keys: ``naturalization_status``, ``personas``,
            ``rendered_scenario_overrides``, ``tokens_used``.

        Raises
        ------
        ValueError
            If ``family_id`` cannot be determined from the bundle files.
        NaturalizationValidationError
            Propagated from :func:`run_naturalization` when the LLM
            response fails quality checks.
        """
        base_path = Path(base_dir)
        scenario = _read_json(base_path / "scenario.json")
        gt = _read_json(base_path / "scenario.gt.json")

        family_id = _extract_family_id(scenario, gt)
        scenario_id = str(
            scenario.get("scenario_id") or base_path.name
        )
        cell_id: str | None = scenario.get("cell_id") or None

        skeleton = build_family_pack_skeleton(
            family_id=family_id,
            bundle_dir=base_path,
            cell_id=cell_id,
            index_row={
                "family_id": family_id,
                "scenario_id": scenario_id,
                "cell_id": cell_id,
            },
        )

        naturalized_scenario_id = str(
            skeleton.payload.get("scenario", {}).get("scenario_id") or scenario_id
        )
        patch: NaturalizationPatch = run_naturalization(
            client=self._resolve_client(),
            scenario_id=naturalized_scenario_id,
            skeleton_payload=skeleton.payload,
            model=self.model,
        )

        return _patch_to_publish_dict(patch)
