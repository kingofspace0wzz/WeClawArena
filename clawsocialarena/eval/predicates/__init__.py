"""Predicate registry root for the family-pack-aware evaluator.

See ``docs/superpowers/specs/2026-05-09-clawsocialarena-v2-task-contract-design.md``
section 3 for the predicate signature contract. Each subdirectory
under ``predicates/`` contributes a Python module registering callables
under names referenced by ``scenario.gt.json`` ``evaluation_criteria``.
"""
