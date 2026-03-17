# Analysis Pipeline: Technical Methodology

*Internal documentation — not included in stakeholder deliverables.*

---

## Overview

The analysis pipeline uses a multi-agent architecture built with LangGraph and LiteLLM (Anthropic Claude Sonnet). Each agent is a specialised component that processes participant data through a defined stage, with outputs feeding forward to downstream agents.

The pipeline is coordinated by an **Orchestrator** (`src/pipeline/orchestrator.py`) that manages execution order, context building, and state persistence.

---

## Agent Pipeline

### Per-Participant Agents (run for each of the 35 participants)

| Agent | Input | Output | Purpose |
|-------|-------|--------|---------|
| **Summary Agent** | Transcript + diary data (if available) | `participant_summaries/{pid}_summary.json` | Structured summary of the participant's food and delivery behaviours, attitudes, and say-do gaps |
| **Analysis Agent** | Transcript + diary data + codebook | `coded_segments/{pid}_coded.json` | Multi-pass qualitative coding: initial open coding, axial coding, selective coding, and diary-specific coding (source: "diary" / "diary_reflection"). Produces coded segments with research objective codes, context tags, and emotions |

### Cross-Participant Agents (run once across all participants)

| Agent | Input | Output | Purpose |
|-------|-------|--------|---------|
| **Triangulation Agent** | All summaries + all coded segments + DScout analysis | `triangulation/triangulation_results.json` | Cross-participant pattern identification, interview-diary triangulation, say-do gap synthesis, evidence weight hierarchy |
| **Persona Agent** | Triangulation results + all summaries | `personas/personas.json` | Behavioural persona synthesis with participant assignments, delivery triggers, emotional drivers, and pain points |
| **Insight Agent** | Triangulation + personas + summaries | `insights/insights.json` | Strategic insight generation with evidence chains, confidence levels, and actionable recommendations |
| **Plus Strategy Agent** | Coded segments (subscription-related) + insights | `plus_strategy/plus_strategy.json` | Dedicated subscription strategy analysis: competitive landscape, value drivers, pain points, churn risks |
| **QA Agent** | All agent outputs | `qa_results/qa_results.json` | Quality audit: evidence coverage, contradiction detection, confidence adjustment, quote verification |
| **Advocate Agent** | Insights + QA results | `advocate_results/advocate_results.json` | Devil's advocate review: challenges each insight with counter-evidence, alternative explanations, and sample-size scrutiny |

---

## Coding Passes (Analysis Agent)

The Analysis Agent performs systematic multi-pass qualitative coding:

1. **Open coding:** Initial segment identification from transcript text. Each segment tagged with research objective codes and descriptive labels.
2. **Axial coding:** Segments grouped by theme, relationships between codes identified, context tags applied (emotion, occasion, social context).
3. **Selective coding:** Core categories identified, segments re-examined for fit. Contradictions and tensions flagged.
4. **Diary coding (participants with diary data only):** Structured meal data and open-text diary responses coded with `source: "diary"` or `source: "diary_reflection"`. Say-do gap segments created comparing interview claims with diary observations.

Diary-sourced segments are marked with `_quote_verification: {status: "DIARY_SOURCE"}` to skip transcript verification during QA.

---

## Diary Data Integration

15 of 35 participants completed a 7-day DScout diary study alongside their interviews. Diary data is processed by `src/loaders/dscout_loader.py` into per-participant JSON files containing:

- Structured meal records (breakfast, lunch, dinner) with food source, skip status, and cooking method
- Daily video reflections (transcribed)
- Open-text responses about food decisions

This data is loaded by the Orchestrator and injected into the Summary, Analysis, and Triangulation agent contexts for participants flagged as `has_diary: true` in `data/reference/participant_map.json`.

---

## State Management

The pipeline uses a `StateManager` (`src/storage/state_manager.py`) that tracks completion status per participant and agent in `data/processed/pipeline_state.json`. This enables:

- Resume-from-failure if the pipeline stops mid-run
- Selective re-processing of specific participants or agents
- Prevention of duplicate processing

---

## Output Generation

After agent processing, output generators (`src/generators/`) transform the processed JSON data into stakeholder-ready markdown reports:

- `topline_summary.py` — Stakeholder topline with narrative findings and participant quotes
- `report_generator.py` — Full research report with methodology, findings, personas, and recommendations
- `plus_strategy_generator.py` — Dedicated Plus subscription strategy report
- `persona_cards.py` — Individual persona profile cards
- `journey_viz.py` — Emotional journey maps per persona
- `tension_map.py` — Tension/paradox mapping
- Additional enrichment generators (competitive map, language patterns, value equations, micro-moments)

---

## Quality Controls

1. **Quote verification:** Fuzzy matching of coded segments against original transcripts (diary segments exempted)
2. **Persona de-duplication:** Each participant assigned to exactly one persona; duplicates resolved by keeping the first assignment
3. **Confidence adjustment:** QA Agent can downgrade insight confidence based on contradiction rates or small sample sizes
4. **Adversarial review:** Advocate Agent challenges each insight with counter-evidence and alternative explanations
5. **Participant quote cap:** Output generators limit any single participant to max 2 quotes across all findings to ensure voice diversity
6. **Global quote deduplication:** Same quote cannot appear in multiple findings
