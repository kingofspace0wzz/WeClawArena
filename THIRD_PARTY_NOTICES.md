# Third-Party Notices

WeClawArena v2.0.0 includes adapted task inputs from the sources below. These notices supplement the repository licenses and do not replace the original terms.

## TravelBench

The `benchmark/scenarios/v2.0.0/travel/` domain uses adapted hotel-booking facts and travel-task seeds from [TravelBench](https://github.com/small-xiangcheng/TravelBench).

- Dataset license: [CC BY-NC 4.0](https://creativecommons.org/licenses/by-nc/4.0/)
- TravelBench code license: MIT
- WeClawArena mapping: source facts were converted into multi-owner workspaces, collaboration roles, tools, policies, task predicates, and matched attack variants.

Citation:

```bibtex
@article{cheng2025travelbench,
  title={TravelBench: A Real-World Benchmark for Multi-Turn and Tool-Augmented Travel Planning},
  author={Cheng, Xiang and Hu, Yulan and Zhang, Xiangwen and Xu, Lu and Pan, Zheng and Li, Xin and Liu, Yong},
  journal={arXiv preprint arXiv:2512.22673},
  year={2025}
}
```

## SWE-bench

The `benchmark/scenarios/v2.0.0/swebench_workspace/` domain uses selected issue records from [SWE-bench Lite](https://github.com/SWE-bench/SWE-bench) and reduced source fixtures tied to the named upstream repositories and commits.

- SWE-bench repository license: MIT
- WeClawArena mapping: issue tasks were converted into multi-owner software workspaces with implementer, reviewer, code-owner, and CI roles, plus task and attack variants.
- Upstream repository notice: issue text and reduced source material may also be subject to the licenses of the original projects named in each bundle's metadata.

Citation:

```bibtex
@inproceedings{jimenez2024swebench,
  title={SWE-bench: Can Language Models Resolve Real-World GitHub Issues?},
  author={Jimenez, Carlos E. and Yang, John and Wettig, Alexander and Yao, Shunyu and Pei, Kexin and Press, Ofir and Narasimhan, Karthik},
  booktitle={International Conference on Learning Representations},
  year={2024}
}
```
