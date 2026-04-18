"""Experiment configuration and cost tracking for the batch runner.

This subpackage holds the Phase G grid-config schema
(:mod:`clawsocialarena.experiments.grid_config`) and the provider
rate table used by :mod:`scripts.run_grid` to compute per-row dollar
cost estimates. The modules here do not touch the gateway or eval
pipeline directly; they are pure config/data plumbing so the batch
runner and downstream analysis can share a single source of truth.
"""
