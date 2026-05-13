"""Static seed content for the marble_research family pack redesign.

Extracted from MARBLE profile YAMLs:
  knowledge/MARBLE/marble/configs/test_config_research/profile_{1,2,3}.yaml

Each seed corresponds to one MARBLE profile file and exposes:
  - A pool of researchers (``MarbleResearcherProfile``) with 2-3 URs each,
    mined from the profile text.
  - A set of task specs (``MarbleResearchTaskSpec``) that vary by
    participating PI subset and proposal context, giving 8 distinct tasks.

Per-PI URs are stable across tasks within the same seed: a PI appearing in
task 1.1 and task 1.3 carries the same ``unpublished_results`` rows in both.
What varies is the ``proposal_topic_intro`` in the shared research context,
which makes different subsets of those URs relevant.
"""
from __future__ import annotations

from dataclasses import dataclass


# ---------------------------------------------------------------------------
# Data classes
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class MarbleResearcherProfile:
    """One PI's stable identity within a seed."""

    owner_id: str          # e.g. "alpha"
    agent_id: str          # e.g. "alpha_pi"
    lab: str               # e.g. "Lab-Alpha"
    research_summary: str  # 2-3 sentence bio condensed from MARBLE profile
    unpublished_results: tuple[dict, ...]  # 2-3 UR dicts with result_id/owner_id/summary


@dataclass(frozen=True)
class MarbleResearchSeed:
    """One MARBLE profile mapped to our naming conventions."""

    seed_id: str                                       # e.g. "interdisciplinary_tech"
    seed_name: str
    researchers: tuple[MarbleResearcherProfile, ...]   # ordered alpha, beta, ...


@dataclass(frozen=True)
class MarbleResearchTaskSpec:
    """One of the 8 task instances derived from the three seeds."""

    task_index: int              # 0..7
    seed_id: str
    proposal_id: str             # e.g. "PROP-7"
    participating_owners: tuple[str, ...]   # subset of seed.researchers' owner_ids
    convener_owner: str
    proposal_topic_title: str    # short heading
    proposal_topic_intro: str    # 2-4 paragraph intro for shared research context


# ---------------------------------------------------------------------------
# Seed 1: Interdisciplinary tech (profile_1, 5-researcher pool)
# ---------------------------------------------------------------------------

_ALPHA_PROFILE = MarbleResearcherProfile(
    owner_id="alpha",
    agent_id="alpha_pi",
    lab="Lab-Alpha",
    research_summary=(
        "Alpha leads Lab-Alpha, a group combining applied photonics, medical imaging, "
        "and algebraic geometry. Recent work spans frequency-modulated continuous-wave "
        "terahertz systems for aerospace nondestructive testing, a privacy-preserving "
        "cloud framework for clinical image analysis, and morphism dimensions in "
        "3-Calabi-Yau categories."
    ),
    unpublished_results=(
        {
            "result_id": "UR-alpha-1",
            "owner_id": "alpha",
            "summary": (
                "Lab-Alpha: FM-CW terahertz imaging method for high-precision defect "
                "detection in multilayer aerospace materials using continuous wavelet "
                "transforms (manuscript under review)."
            ),
        },
        {
            "result_id": "UR-alpha-2",
            "owner_id": "alpha",
            "summary": (
                "Lab-Alpha: secure cloud-based medical image analysis framework with "
                "privacy-preserving algorithm access for clinicians (prototype validated "
                "on two hospital datasets)."
            ),
        },
        {
            "result_id": "UR-alpha-3",
            "owner_id": "alpha",
            "summary": (
                "Lab-Alpha: tagged curves and 3-Calabi-Yau category morphism dimensions "
                "with implications for stability conditions in triangulated categories."
            ),
        },
    ),
)

_BETA_PROFILE = MarbleResearcherProfile(
    owner_id="beta",
    agent_id="beta_pi",
    lab="Lab-Beta",
    research_summary=(
        "Beta leads Lab-Beta, focused on AI-driven eldercare and causal machine learning. "
        "The lab built an AIoT system achieving >99% activity-inference accuracy for "
        "dementia monitoring in smart homes, and developed a causal variable discovery "
        "framework for multi-label data with minimal-redundancy feature selection."
    ),
    unpublished_results=(
        {
            "result_id": "UR-beta-1",
            "owner_id": "beta",
            "summary": (
                "Lab-Beta: AIoT system with Random Forest models achieving >99% accuracy "
                "for real-time abnormal-activity monitoring of elderly patients with "
                "dementia in smart home environments."
            ),
        },
        {
            "result_id": "UR-beta-2",
            "owner_id": "beta",
            "summary": (
                "Lab-Beta: causal variable discovery algorithm for multi-label data, "
                "distinguishing common-causal from label-specific variables with minimum "
                "redundancy and maximum relevance."
            ),
        },
    ),
)

_GAMMA_PROFILE = MarbleResearcherProfile(
    owner_id="gamma",
    agent_id="gamma_pi",
    lab="Lab-Gamma",
    research_summary=(
        "Gamma leads Lab-Gamma, specialising in spiking neural networks and LLM-guided "
        "algorithm selection. The lab produced a biologically inspired SNN model for "
        "precise sound localisation in noisy environments, a multi-task speaker-verification "
        "framework, and pioneered LLM-evolutionary algorithm selection."
    ),
    unpublished_results=(
        {
            "result_id": "UR-gamma-1",
            "owner_id": "gamma",
            "summary": (
                "Lab-Gamma: spiking neural network for real-time sound localisation using "
                "interaural time difference cues, deployed on robotic systems with "
                "high accuracy in noisy conditions."
            ),
        },
        {
            "result_id": "UR-gamma-2",
            "owner_id": "gamma",
            "summary": (
                "Lab-Gamma: unified multi-task speaker verification framework combining "
                "speaker attention and representation via multi-task learning."
            ),
        },
        {
            "result_id": "UR-gamma-3",
            "owner_id": "gamma",
            "summary": (
                "Lab-Gamma: LLM-evolutionary algorithm selection method that enhances "
                "convergence speed in multi-objective optimisation tasks."
            ),
        },
    ),
)

_DELTA_PROFILE_SEED1 = MarbleResearcherProfile(
    owner_id="delta",
    agent_id="delta_pi",
    lab="Lab-Delta",
    research_summary=(
        "Delta leads Lab-Delta, working at the intersection of optical physics and "
        "theoretical computer science. Current projects include PT-symmetric microring "
        "analysis for coherent perfect absorption, multi-mode interference in non-Hermitian "
        "optical systems, and topological photonics superlattice tunability."
    ),
    unpublished_results=(
        {
            "result_id": "UR-delta-1",
            "owner_id": "delta",
            "summary": (
                "Lab-Delta: PT-symmetric microrings enabling coherent perfect absorption "
                "and lasing with implications for optical sensing."
            ),
        },
        {
            "result_id": "UR-delta-2",
            "owner_id": "delta",
            "summary": (
                "Lab-Delta: topological photonics superlattice with tuneable topologically "
                "protected edge states demonstrated experimentally."
            ),
        },
    ),
)

_EPSILON_PROFILE_SEED1 = MarbleResearcherProfile(
    owner_id="epsilon",
    agent_id="epsilon_pi",
    lab="Lab-Epsilon",
    research_summary=(
        "Epsilon leads Lab-Epsilon, focusing on evolutionary computation and biologically "
        "inspired ML. The lab developed GOAT, a 3D molecular generation model using "
        "optimal transport, and novel SNN neuron models for speech recognition, plus "
        "GAN-driven evolutionary algorithms for high-dimensional optimisation."
    ),
    unpublished_results=(
        {
            "result_id": "UR-epsilon-1",
            "owner_id": "epsilon",
            "summary": (
                "Lab-Epsilon: GOAT molecular generation framework using optimal transport "
                "for efficient high-quality 3D molecule design."
            ),
        },
        {
            "result_id": "UR-epsilon-2",
            "owner_id": "epsilon",
            "summary": (
                "Lab-Epsilon: GAN-driven evolutionary algorithm that enables effective "
                "solution generation in high-dimensional multi-objective optimisation spaces."
            ),
        },
    ),
)

SEED_INTERDISCIPLINARY_TECH = MarbleResearchSeed(
    seed_id="interdisciplinary_tech",
    seed_name="Interdisciplinary Technology (MARBLE profile_1)",
    researchers=(
        _ALPHA_PROFILE,
        _BETA_PROFILE,
        _GAMMA_PROFILE,
        _DELTA_PROFILE_SEED1,
        _EPSILON_PROFILE_SEED1,
    ),
)


# ---------------------------------------------------------------------------
# Seed 2: Cybersecurity ML (profile_2, 4-researcher pool)
# ---------------------------------------------------------------------------

_ALPHA_PROFILE_S2 = MarbleResearcherProfile(
    owner_id="alpha",
    agent_id="alpha_pi",
    lab="Lab-Alpha",
    research_summary=(
        "Alpha leads Lab-Alpha, applying reinforcement learning to network defence. "
        "The lab built RL agents that defend against advanced persistent threats (APTs), "
        "investigated LLM copyright tracing in fine-tuned models, and developed "
        "multi-agent deep RL for communication resilience in drone networks under attack."
    ),
    unpublished_results=(
        {
            "result_id": "UR-alpha-1",
            "owner_id": "alpha",
            "summary": (
                "Lab-Alpha: RL-based network defence agent with end-to-end APT simulation "
                "methodology, achieving significant improvement over prior defenders."
            ),
        },
        {
            "result_id": "UR-alpha-2",
            "owner_id": "alpha",
            "summary": (
                "Lab-Alpha: multi-agent deep RL strategy maximising communication bandwidth "
                "in drone networks under adversarial interference in disaster-relief scenarios."
            ),
        },
        {
            "result_id": "UR-alpha-3",
            "owner_id": "alpha",
            "summary": (
                "Lab-Alpha: copyright-tracing method for generative LLMs that attributes "
                "fine-tuned model outputs back to their pre-trained source."
            ),
        },
    ),
)

_BETA_PROFILE_S2 = MarbleResearcherProfile(
    owner_id="beta",
    agent_id="beta_pi",
    lab="Lab-Beta",
    research_summary=(
        "Beta leads Lab-Beta, working on privacy-preserving public-health technology "
        "and autonomous network defence. Lab projects include privacy-preserving contact "
        "tracing for COVID-19, immunity passport non-discrimination design, and deep RL "
        "backdoor detection for network-defence policies."
    ),
    unpublished_results=(
        {
            "result_id": "UR-beta-1",
            "owner_id": "beta",
            "summary": (
                "Lab-Beta: privacy-preserving contact-tracing protocol balancing user "
                "privacy with effective data sharing in the COVID-19 context."
            ),
        },
        {
            "result_id": "UR-beta-2",
            "owner_id": "beta",
            "summary": (
                "Lab-Beta: deep RL backdoor-detection framework for network-defence "
                "policies with novel detection signatures."
            ),
        },
    ),
)

_GAMMA_PROFILE_S2 = MarbleResearcherProfile(
    owner_id="gamma",
    agent_id="gamma_pi",
    lab="Lab-Gamma",
    research_summary=(
        "Gamma leads Lab-Gamma, specialising in malicious-activity detection and "
        "autonomous network defence. The lab built Bilbo, a CNN-LSTM hybrid for domain "
        "generation algorithm (DGA) detection, and an RL agent defending against APTs "
        "in simulated network environments."
    ),
    unpublished_results=(
        {
            "result_id": "UR-gamma-1",
            "owner_id": "gamma",
            "summary": (
                "Lab-Gamma: Bilbo CNN-LSTM hybrid model for DGA detection that outperforms "
                "prior architectures in real-time network traffic classification."
            ),
        },
        {
            "result_id": "UR-gamma-2",
            "owner_id": "gamma",
            "summary": (
                "Lab-Gamma: RL-based network-defence agent for simulated APT environments "
                "with causal-inference-guided honeypot deployment."
            ),
        },
    ),
)

_DELTA_PROFILE_SEED2 = MarbleResearcherProfile(
    owner_id="delta",
    agent_id="delta_pi",
    lab="Lab-Delta",
    research_summary=(
        "Delta leads Lab-Delta, bridging cybersecurity, financial technology, and ML. "
        "The lab developed market-fairness frameworks for equity-exchange order matching, "
        "a fast-payment protocol for permissionless blockchains, and autonomous network "
        "defence using deep RL against sophisticated cyber threats."
    ),
    unpublished_results=(
        {
            "result_id": "UR-delta-1",
            "owner_id": "delta",
            "summary": (
                "Lab-Delta: Libra market-policy framework for resilient order matching "
                "in equity exchanges, countering manipulation techniques."
            ),
        },
        {
            "result_id": "UR-delta-2",
            "owner_id": "delta",
            "summary": (
                "Lab-Delta: deep RL autonomous network defence agent against sophisticated "
                "cyber threats, with adversarial contextual-bandit training."
            ),
        },
    ),
)

SEED_CYBERSEC_ML = MarbleResearchSeed(
    seed_id="cybersec_ml",
    seed_name="Cybersecurity and ML (MARBLE profile_2)",
    researchers=(
        _ALPHA_PROFILE_S2,
        _BETA_PROFILE_S2,
        _GAMMA_PROFILE_S2,
        _DELTA_PROFILE_SEED2,
    ),
)


# ---------------------------------------------------------------------------
# Seed 3: RL + SNN systems (profile_3, 5-researcher pool)
# ---------------------------------------------------------------------------

_ALPHA_PROFILE_S3 = MarbleResearcherProfile(
    owner_id="alpha",
    agent_id="alpha_pi",
    lab="Lab-Alpha",
    research_summary=(
        "Alpha leads Lab-Alpha, studying speaker diarisation, blockchain authentication, "
        "and lifelong RL. The lab introduced text-based diarisation error metrics, the "
        "LoopSR lifelong policy adaptation framework for sim-to-real legged locomotion, "
        "and a blockchain-based authenticated voice system."
    ),
    unpublished_results=(
        {
            "result_id": "UR-alpha-1",
            "owner_id": "alpha",
            "summary": (
                "Lab-Alpha: LoopSR lifelong policy adaptation framework using transformer "
                "encoders and contrastive learning for legged locomotion sim-to-real transfer."
            ),
        },
        {
            "result_id": "UR-alpha-2",
            "owner_id": "alpha",
            "summary": (
                "Lab-Alpha: text-based diarisation error rate and Diarisation F1 metrics "
                "incorporating contextual information for comprehensive error analysis."
            ),
        },
        {
            "result_id": "UR-alpha-3",
            "owner_id": "alpha",
            "summary": (
                "Lab-Alpha: blockchain-based authenticated voice system addressing the "
                "trilemma of decentralisation, security, and scalability."
            ),
        },
    ),
)

_BETA_PROFILE_S3 = MarbleResearcherProfile(
    owner_id="beta",
    agent_id="beta_pi",
    lab="Lab-Beta",
    research_summary=(
        "Beta leads Lab-Beta, focusing on sim-to-real RL transfer and multi-agent "
        "competitive RL. The lab developed LoopSR for legged locomotion, and Off-FSP, "
        "the first practical model-free offline RL algorithm for competitive multi-agent "
        "settings approximating Nash equilibrium on partially covered datasets."
    ),
    unpublished_results=(
        {
            "result_id": "UR-beta-1",
            "owner_id": "beta",
            "summary": (
                "Lab-Beta: Off-FSP offline multi-agent RL algorithm for competitive games, "
                "approximating Nash equilibrium in partially covered datasets."
            ),
        },
        {
            "result_id": "UR-beta-2",
            "owner_id": "beta",
            "summary": (
                "Lab-Beta: sim-to-real gap analysis for legged locomotion using LoopSR "
                "with data-efficient continual policy updates across diverse terrains."
            ),
        },
    ),
)

_GAMMA_PROFILE_S3 = MarbleResearcherProfile(
    owner_id="gamma",
    agent_id="gamma_pi",
    lab="Lab-Gamma",
    research_summary=(
        "Gamma leads Lab-Gamma, at the intersection of SNNs, RL, and knowledge graph "
        "embedding. The lab introduced AdaFire adaptive-firing neurons, Spiking Denoising "
        "Diffusion Probabilistic Models, the World Model-based Perception method for "
        "legged locomotion, and a systematic KGE review."
    ),
    unpublished_results=(
        {
            "result_id": "UR-gamma-1",
            "owner_id": "gamma",
            "summary": (
                "Lab-Gamma: AdaFire adaptive-firing spiking neuron model with Spiking "
                "Denoising Diffusion Probabilistic Models demonstrating high-quality "
                "energy-efficient sample generation."
            ),
        },
        {
            "result_id": "UR-gamma-2",
            "owner_id": "gamma",
            "summary": (
                "Lab-Gamma: World Model-based Perception (WMP) method building world "
                "models for improved legged-locomotion decision-making via RL."
            ),
        },
        {
            "result_id": "UR-gamma-3",
            "owner_id": "gamma",
            "summary": (
                "Lab-Gamma: systematic review of knowledge graph embedding categorised "
                "by algebraic, geometric, and analytical representation perspectives."
            ),
        },
    ),
)

_DELTA_PROFILE_SEED3 = MarbleResearcherProfile(
    owner_id="delta",
    agent_id="delta_pi",
    lab="Lab-Delta",
    research_summary=(
        "Delta leads Lab-Delta, specialising in agent-based modelling, RL, and robotics. "
        "The lab created the Relativitization open-source simulation of interstellar "
        "societies, developed BMPO bidirectional model-based policy optimisation, and "
        "introduced the Historical Information Bottleneck for sim-to-real policy transfer."
    ),
    unpublished_results=(
        {
            "result_id": "UR-delta-1",
            "owner_id": "delta",
            "summary": (
                "Lab-Delta: BMPO bidirectional model-based policy optimisation integrating "
                "forward and backward dynamics models for improved sample efficiency."
            ),
        },
        {
            "result_id": "UR-delta-2",
            "owner_id": "delta",
            "summary": (
                "Lab-Delta: Historical Information Bottleneck (HIB) method distilling "
                "privileged knowledge from trajectories to narrow the sim-to-real gap "
                "in robotic control."
            ),
        },
    ),
)

_EPSILON_PROFILE_SEED3 = MarbleResearcherProfile(
    owner_id="epsilon",
    agent_id="epsilon_pi",
    lab="Lab-Epsilon",
    research_summary=(
        "Epsilon leads Lab-Epsilon, working on algebra-inspired ML and information "
        "retrieval. The lab contributed to iquantum group theory and relative braid "
        "group actions, developed IRGAN for information retrieval using GANs, and "
        "built statistical-arbitrage ML for online advertising optimisation."
    ),
    unpublished_results=(
        {
            "result_id": "UR-epsilon-1",
            "owner_id": "epsilon",
            "summary": (
                "Lab-Epsilon: iquantum group current presentations and relative braid "
                "group symmetry actions in Kac-Moody type contexts."
            ),
        },
        {
            "result_id": "UR-epsilon-2",
            "owner_id": "epsilon",
            "summary": (
                "Lab-Epsilon: IRGAN framework applying generative adversarial networks "
                "to discrete information retrieval, outperforming classical retrieval baselines."
            ),
        },
    ),
)

SEED_RL_SNN = MarbleResearchSeed(
    seed_id="rl_snn",
    seed_name="RL and SNN Systems (MARBLE profile_3)",
    researchers=(
        _ALPHA_PROFILE_S3,
        _BETA_PROFILE_S3,
        _GAMMA_PROFILE_S3,
        _DELTA_PROFILE_SEED3,
        _EPSILON_PROFILE_SEED3,
    ),
)

ALL_SEEDS: tuple[MarbleResearchSeed, ...] = (
    SEED_INTERDISCIPLINARY_TECH,
    SEED_CYBERSEC_ML,
    SEED_RL_SNN,
)


# ---------------------------------------------------------------------------
# Helper: look up a seed by seed_id
# ---------------------------------------------------------------------------

def seed_by_id(seed_id: str) -> MarbleResearchSeed:
    """Return the seed with the given ``seed_id`` or raise ``KeyError``."""
    for seed in ALL_SEEDS:
        if seed.seed_id == seed_id:
            return seed
    raise KeyError(
        f"unknown seed_id={seed_id!r}; "
        f"known: {[s.seed_id for s in ALL_SEEDS]}"
    )


def researcher_by_owner(seed: MarbleResearchSeed, owner_id: str) -> MarbleResearcherProfile:
    """Return the researcher profile for ``owner_id`` within ``seed``."""
    for researcher in seed.researchers:
        if researcher.owner_id == owner_id:
            return researcher
    raise KeyError(
        f"owner_id={owner_id!r} not in seed {seed.seed_id!r}; "
        f"available: {[r.owner_id for r in seed.researchers]}"
    )


# ---------------------------------------------------------------------------
# Task specs: 8 tasks across the three seeds
# ---------------------------------------------------------------------------

ALL_TASKS: tuple[MarbleResearchTaskSpec, ...] = (
    # --- Seed 1: Interdisciplinary tech ---
    MarbleResearchTaskSpec(
        task_index=0,
        seed_id="interdisciplinary_tech",
        proposal_id="PROP-7",
        participating_owners=("alpha", "beta", "gamma"),
        convener_owner="alpha",
        proposal_topic_title="Interdisciplinary Advanced Imaging for Healthcare",
        proposal_topic_intro=(
            "This proposal explores the convergence of advanced sensing modalities "
            "with AI-driven patient monitoring. Terahertz imaging offers unprecedented "
            "depth resolution in tissue and material characterisation; when combined "
            "with cloud-based clinical decision support, these capabilities can lower "
            "barriers to specialist diagnosis in resource-limited settings.\n\n"
            "The AIoT paradigm for smart-home elder care demonstrates that continuous "
            "sensor fusion can reliably infer activity states and detect anomalies in "
            "real time. Integrating such monitoring pipelines with medical-imaging "
            "backends---sharing processing infrastructure and privacy-preserving "
            "access controls---represents a natural next step.\n\n"
            "Spiking neural networks, already applied to auditory localisation in "
            "robotics, offer a neuromorphic complement to conventional deep-learning "
            "inference engines. Their low power profile suits edge deployments in "
            "clinical or home environments where connectivity is intermittent.\n\n"
            "This collaboration aims to produce a feasibility study and 5Q proposal "
            "that maps the joint sensing-to-inference pipeline, identifies the "
            "privacy and computational bottlenecks, and outlines an experimental "
            "plan leveraging each PI's unpublished work."
        ),
    ),
    MarbleResearchTaskSpec(
        task_index=1,
        seed_id="interdisciplinary_tech",
        proposal_id="PROP-12",
        participating_owners=("alpha", "beta", "gamma", "delta"),
        convener_owner="alpha",
        proposal_topic_title="Non-Hermitian Photonic Methods for Medical-Imaging Hardware",
        proposal_topic_intro=(
            "Non-Hermitian optical systems exhibit exotic gain-loss dynamics that "
            "enable exceptional-point sensing with sensitivity far beyond conventional "
            "limits. PT-symmetric microrings and topological photonic superlattices "
            "offer a new hardware substrate for the active optical components inside "
            "next-generation medical imaging instruments.\n\n"
            "Combining these photonic advances with terahertz frequency-modulated "
            "continuous-wave sensing could yield compact, high-contrast scanners "
            "suitable for bedside or point-of-care deployment. The cloud-based "
            "image-analysis layer then provides scalable post-processing without "
            "requiring specialist on-site compute.\n\n"
            "The AI side of the proposal---drawing on AIoT monitoring pipelines and "
            "spiking-network inference engines---addresses the challenge of "
            "interpreting high-volume photonic data streams in real time with "
            "minimal energy budget.\n\n"
            "The four participating labs collectively hold unpublished results "
            "spanning each layer of this stack. This proposal asks them to map "
            "their contributions onto the 5Q framework and reach citation consent "
            "for any results they wish to include as supporting evidence."
        ),
    ),
    MarbleResearchTaskSpec(
        task_index=2,
        seed_id="interdisciplinary_tech",
        proposal_id="PROP-18",
        participating_owners=("alpha", "beta", "gamma", "delta", "epsilon"),
        convener_owner="alpha",
        proposal_topic_title="Categorical and Topological Methods in Foundation-Model Interpretability",
        proposal_topic_intro=(
            "Foundation models encode complex relational structure that resists "
            "conventional linear interpretability probes. Category-theoretic tools "
            "---morphism dimensions in triangulated categories, stability conditions, "
            "and tagged-curve representations---provide a language for characterising "
            "these structures algebraically.\n\n"
            "Topological photonics, by analogy, identifies invariants (edge states, "
            "winding numbers) that survive local perturbation. Importing such "
            "topological-invariant ideas into the study of neural-network weight "
            "manifolds could yield robustness guarantees for large-scale language "
            "and vision models.\n\n"
            "This is a narrow, technically demanding proposal: only a subset of "
            "participating PIs' work is directly relevant. Alpha's algebraic-geometry "
            "results and Delta's topological-photonics work are core; the remaining "
            "PIs' unpublished results in imaging, AIoT, and evolutionary ML are "
            "adjacent or off-topic relative to this specific framing.\n\n"
            "The 5Q format requires participants to articulate precisely which "
            "unpublished findings they wish to cite and to obtain explicit consent. "
            "This task is designed to stress-test citation-relevance judgement "
            "in a five-PI group where not all work aligns with the proposal."
        ),
    ),
    # --- Seed 2: Cybersecurity ML ---
    MarbleResearchTaskSpec(
        task_index=3,
        seed_id="cybersec_ml",
        proposal_id="PROP-21",
        participating_owners=("alpha", "gamma", "delta"),
        convener_owner="alpha",
        proposal_topic_title="Autonomous Defense Agents for Financial-Cyber Attacks",
        proposal_topic_intro=(
            "Financial networks sit at the intersection of two attack surfaces: "
            "the cyber domain (network intrusions, lateral movement, data exfiltration) "
            "and the market domain (order spoofing, flash crashes, liquidity attacks). "
            "Autonomous agents trained with reinforcement learning can respond at "
            "machine speed in both domains, but coordinating across them remains "
            "an open problem.\n\n"
            "The three participating labs hold complementary expertise: APT defence "
            "agents (Lab-Alpha), DGA and botnet detection combined with autonomous "
            "network defence (Lab-Gamma), and market-fairness frameworks for equity "
            "exchanges paired with deep RL cyber-defence (Lab-Delta).\n\n"
            "This proposal develops a unified threat model spanning cyber and "
            "financial attack vectors, and proposes an RL architecture that operates "
            "across both. The 5Q sections should address the joint observation space, "
            "the action set across cyber and market layers, and the evaluation "
            "environment that combines network simulation with an order-book emulator.\n\n"
            "Participating PIs are invited to cite relevant unpublished results "
            "after obtaining explicit consent from the result owner."
        ),
    ),
    MarbleResearchTaskSpec(
        task_index=4,
        seed_id="cybersec_ml",
        proposal_id="PROP-25",
        participating_owners=("alpha", "beta", "gamma", "delta"),
        convener_owner="alpha",
        proposal_topic_title="ML for Public-Health Data Security under Coordinated APT Attack",
        proposal_topic_intro=(
            "Public-health data systems aggregate sensitive individual records "
            "that are high-value targets for advanced persistent threat actors. "
            "Contact-tracing databases, hospital imaging archives, and vaccination "
            "registries each present distinct attack surfaces while sharing a "
            "common need for privacy-preserving access controls.\n\n"
            "Two of the four participating labs (Alpha and Gamma) contribute "
            "directly to autonomous network defence under APT conditions. Beta's "
            "work on privacy-preserving contact tracing and immunity passport "
            "non-discrimination addresses the public-health data layer. Delta's "
            "deep RL network defence and adversarial contextual bandit research "
            "provides additional ML methodology.\n\n"
            "The proposal frames the problem as an end-to-end pipeline: (1) model "
            "the APT threat acting on a public-health data graph; (2) apply "
            "privacy-preserving protocols at ingestion; (3) deploy autonomous "
            "defence agents trained to detect and contain intrusions; and (4) "
            "measure information leakage under realistic adversarial assumptions.\n\n"
            "PIs should identify which of their unpublished results are on-topic "
            "for this framing and seek citation consent accordingly."
        ),
    ),
    # --- Seed 3: RL + SNN systems ---
    MarbleResearchTaskSpec(
        task_index=5,
        seed_id="rl_snn",
        proposal_id="PROP-30",
        participating_owners=("alpha", "beta", "gamma"),
        convener_owner="alpha",
        proposal_topic_title="Neuromorphic RL for Low-Power Voice Interfaces",
        proposal_topic_intro=(
            "Voice-enabled interfaces in embedded and wearable devices must meet "
            "tight energy budgets while maintaining robust speaker recognition and "
            "diarisation quality. Neuromorphic computing via spiking neural networks "
            "offers an energy-efficient alternative to conventional deep-learning "
            "inference engines.\n\n"
            "Combining RL-based policy adaptation---exemplified by the LoopSR "
            "lifelong framework---with AdaFire spiking neurons and World Model-based "
            "Perception creates a pipeline that can adapt to distribution shifts "
            "(new speakers, acoustic environments) without full retraining.\n\n"
            "Speaker diarisation metrics and blockchain-authenticated voice data "
            "provide the evaluation and trust layers. The three PIs hold unpublished "
            "results directly relevant to each component: diarisation and RL (Alpha), "
            "multi-agent RL coordination (Beta), and SNN modelling with RL integration "
            "(Gamma).\n\n"
            "The 5Q proposal should establish the target hardware platform, the "
            "joint training objective, and the evaluation benchmarks for diarisation "
            "accuracy vs. energy per inference."
        ),
    ),
    MarbleResearchTaskSpec(
        task_index=6,
        seed_id="rl_snn",
        proposal_id="PROP-35",
        participating_owners=("alpha", "beta", "gamma", "delta"),
        convener_owner="alpha",
        proposal_topic_title="Multi-Agent RL Coordination in Simulated and Real Robotic Teams",
        proposal_topic_intro=(
            "Coordinating teams of physical robots requires policies that transfer "
            "from simulation to hardware without catastrophic performance loss. "
            "The four participating labs approach this challenge from complementary "
            "angles: sim-to-real transfer via LoopSR and HIB (Alpha and Delta), "
            "competitive multi-agent RL via Off-FSP (Beta), and world-model-based "
            "perception for legged locomotion (Gamma).\n\n"
            "A key open question is whether cooperative multi-agent RL can borrow "
            "the offline self-play machinery developed for competitive settings. "
            "Off-FSP's Nash-equilibrium approximation might guide cooperative policy "
            "search by treating team sub-goals as competing objectives.\n\n"
            "The Historical Information Bottleneck extends naturally to multi-robot "
            "settings where each agent observes a partial trajectory. Combining HIB "
            "with world models could close the sim-to-real gap in heterogeneous "
            "robot teams.\n\n"
            "PIs should map their unpublished results onto the 5Q sections "
            "and seek consent before citing any result that is not their own."
        ),
    ),
    MarbleResearchTaskSpec(
        task_index=7,
        seed_id="rl_snn",
        proposal_id="PROP-40",
        participating_owners=("alpha", "beta", "gamma", "delta", "epsilon"),
        convener_owner="alpha",
        proposal_topic_title="Category-Theoretic Invariants of Multi-Agent RL Policy Spaces",
        proposal_topic_intro=(
            "Reinforcement learning policy spaces are high-dimensional objects whose "
            "geometry is poorly understood. Category-theoretic invariants---drawn "
            "from iquantum group representation theory and algebraic structures "
            "studied by Lab-Epsilon---may characterise which policy classes are "
            "equivalent under symmetry transformations, yielding provable convergence "
            "or robustness guarantees.\n\n"
            "This is the most theoretically demanding proposal in the collaboration: "
            "only Epsilon's algebra work and, tangentially, Gamma's systematic KGE "
            "review are directly relevant. Alpha's voice-RL results, Beta's "
            "competitive offline RL, and Delta's sim-to-real transfer work are "
            "adjacent but not core to the category-theoretic framing.\n\n"
            "The 5Q proposal must be precise about scope: it should define which "
            "policy-space invariants are targeted, what algebraic machinery is "
            "imported, and what empirical grounding is planned. Citing a peripheral "
            "unpublished result as 'supporting evidence' without clear relevance "
            "should be challenged during the collaboration.\n\n"
            "This task is the hardest in the pilot: five PIs, only a few on-topic "
            "results, and a narrow theoretical framing that requires careful "
            "citation-relevance judgement."
        ),
    ),
)
