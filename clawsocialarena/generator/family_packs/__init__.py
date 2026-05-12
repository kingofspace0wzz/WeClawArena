"""Family-pack registry root.

Each subdirectory under ``family_packs/`` is one family-pack loader,
matching one ``family_id`` declared in the family-pack design spec
(docs/superpowers/specs/2026-05-09-clawsocialarena-v2-family-pack-design.md).
A loader knows how to convert an external benchmark's task fixtures
into a v2 ``Scenario`` populated with ``coordination_mode`` and
``agent_graph``.
"""
