# Phase H deferred task (H8)

Phase H lands the analysis infrastructure needed to produce the v2
paper's tables, figures, statistical tests, pre-registration
reconciliation, and reproducibility bundle. The final tag
``v1.0.0`` is deferred until real run data exists.

This note tracks Task H8 so the resume path is clear.

## Status at the time this note was written

- Branch: ``v2-refactor``
- Last tag: ``phase-H-infrastructure-complete`` (commits H1-H7 landed)
- Python test count: 470 passed + 2 skipped
- TypeScript test count: 29 passed (unchanged from Phase G)
- ``results/v1.0.0/`` does not yet exist on disk; every Phase H test
  runs against the ``tests/test_analysis/fixtures.py`` synthetic
  scorecard factory.

## What is already in place

- ``clawsocialarena/analysis/aggregator.py`` emits a wide one-row-per-scorecard
  CSV and a back-compat long-format path; ``status: "pending"`` Phase G
  stubs are silently skipped.
- ``clawsocialarena/analysis/tables.py`` renders the three Phase H tables
  (headline, model, rewrite) as ``(markdown, latex)`` pairs with a
  ``live_or_replay`` stratification column in every row.
- ``clawsocialarena/analysis/figures.py`` produces the four main PDFs +
  the episode-graph appendix figure via ``write_all_figures`` and a
  ``python -m clawsocialarena.analysis figures`` CLI subcommand.
- ``clawsocialarena/analysis/stats.py`` ships a typed
  :class:`StatTestResult` plus ``wilcoxon_paired``, ``kruskal_wallis``,
  ``bonferroni_correct``, and the H6 ``saf_threshold_sensitivity`` helper.
- ``clawsocialarena/analysis/prereg_check.py`` evaluates H1..H5 and writes
  ``results/<version>/prereg_reconciliation.md`` via ``write_report``.
- ``scripts/make_repro_bundle.py`` packs the full reproducibility
  tarball with a ``replay.sh`` one-command driver.

## What is deferred

### H8 — Tag ``v1.0.0``

Goal: tag the repo at v1.0.0 after the full 4,440-run grid has been
materialised and the full paper is ready to hand off.

Pre-requisites (none of these exist yet):

- Phase E content: 150 main-table scenarios + 4 ablation scenarios +
  the five episode-graph scenarios on disk under ``benchmark/scenarios/v1.0.0/``.
- Phase G5-G7 outputs: ~4,440 ``run_scorecard.json`` files under
  ``results/v1.0.0/`` covering the full main table, ablations, seed-variance,
  replay, and episode-graph strata.

Resume steps:

1. Confirm ``results/v1.0.0/`` has every scorecard complete (no
   ``status: "pending"`` rows remaining).
2. Run the full analysis pipeline end-to-end:
   ``python -m clawsocialarena.analysis aggregate --root results/v1.0.0 --out results/v1.0.0/long.csv``
   ``python -m clawsocialarena.analysis table --csv results/v1.0.0/long.csv --kind headline --out results/v1.0.0/headline.md``
   (repeat for ``--kind model`` and ``--kind rewrite``, emit ``--format latex`` variants)
   ``python -m clawsocialarena.analysis figures --csv results/v1.0.0/long.csv --out paper/figures``
   ``python -m clawsocialarena.analysis prereg --csv results/v1.0.0/long.csv --out results/v1.0.0/prereg_reconciliation.md --version v1.0.0``
3. Generate ``CHANGELOG.md`` from the commit log since the v2 refactor
   began (commit SHA range + human summary of H1-H7).
4. Build the reproducibility bundle and sanity-check the extracted
   ``replay.sh``:
   ``python scripts/make_repro_bundle.py --version 1.0.0 --out dist/clawsocialarena-repro-v1.0.0.tar.gz``
5. Tag and push: ``git tag v1.0.0`` then push the tag.
6. Commit: ``chore(arena): v1.0.0 release``.

## Why we paused here

The Phase H infrastructure can be implemented and tested independently
of real run data. Tagging ``v1.0.0`` without that data would bless an
empty results tree and mislead any downstream consumer. The tag waits
on the final run outputs from Phases E and G5-G7, which themselves
depend on budget approval and Docker availability on the target runner.

Resuming H8 is the natural step after the last real run completes
and the full paper is ready; no code redesign is required at that
point.
