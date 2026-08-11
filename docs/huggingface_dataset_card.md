---
pretty_name: WeClawArena
license: cc-by-nc-4.0
language:
  - en
task_categories:
  - text-generation
tags:
  - agents
  - multi-agent
  - tool-use
  - safety
  - benchmark
size_categories:
  - n<1K
---

# WeClawArena

WeClawArena is an auditable benchmark and runtime sandbox for cross-user agent collaboration over personal workspaces. Version 2.0.0 contains 124 base tasks across six domains and expands them into 620 matched scenario variants.

## Dataset Summary

Each base task has one `no_attacker` control and four attack variants: `collaboration`, `security`, `privacy`, and `governance`. The public release contains finalized scenario bundles and a manifest. It does not contain model runtime records, private pilot traces, or full paper execution logs.

| Domain | Base tasks | Variants |
|---|---:|---:|
| Bargaining | 24 | 120 |
| Bidding | 12 | 60 |
| Travel | 20 | 100 |
| SWE-Workspace | 50 | 250 |
| Clinical | 10 | 50 |
| Trading | 8 | 40 |
| **Total** | **124** | **620** |

## Files

The canonical manifest is `benchmark/scenarios/v2.0.0/manifest.json`. A manifest row names the base bundle shared by its five matched variants. Each bundle contains the scenario, ground-truth evaluation contract, personas, tool declarations, owned resources, and Docker Compose configuration.

See `docs/benchmark_dataset_guide.md` in the GitHub repository for the field and directory reference.

## Intended Uses

- Evaluate multi-agent task utility under benign and adversarial conditions.
- Study collaboration, security, privacy, and governance failures separately.
- Inspect owner-scoped resources, authority paths, tool use, and final-state evidence.
- Develop evaluators and defenses for cross-user agent systems.

The clinical scenarios are synthetic benchmark cases and are not medical advice. The trading scenarios are synthetic benchmark cases and are not investment advice.

## Limitations

The release is an evaluation dataset, not a representative sample of deployed agent traffic. It covers six task domains and a fixed set of attack families. Results depend on the selected model, runtime settings, tool implementation, and evaluator configuration. Runtime records used for the paper are outside this dataset release.

## Licensing

The dataset is licensed under [CC BY-NC 4.0](https://creativecommons.org/licenses/by-nc/4.0/). Repository code is licensed under Apache-2.0. See `THIRD_PARTY_NOTICES.md` for TravelBench, SWE-bench, and upstream repository notices.

## Citation

```bibtex
@article{wang2026weclawarena,
  title={WeClawArena: An Auditable Sandbox and Benchmark for Cross-User Agents Collaboration and Security in Human-Centered Agent Networks},
  author={Wang, Prince Zizhuang and Yuan, Aojie and Zhang, Haiyue and Hu, Xiyang and Zhao, Yue and Jiang, Shuli},
  journal={arXiv preprint arXiv:2608.03499},
  year={2026}
}
```

Paper: https://arxiv.org/abs/2608.03499

Code: https://github.com/kingofspace0wzz/WeClawArena
