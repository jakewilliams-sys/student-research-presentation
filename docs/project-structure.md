# Project Structure

```
student-research-analysis/
├── README.md                              # Quick start and CLI reference
├── requirements.txt                       # Python dependencies with pinned versions
├── main.py                                # CLI entry point
│
├── docs/
│   └── project-structure.md               # This file
│
├── config/
│   ├── settings.py                        # LLM provider, API keys, paths
│   ├── research_objectives.yaml           # 5 research objectives with sub-questions
│   ├── segment_definitions.yaml           # Segment slicing rules
│   ├── business_context.yaml              # Deliveroo strategy, challenges, opportunities
│   ├── google_sources.yaml                # Google Workspace + Marvin document IDs
│   ├── in_home_analysis.yaml              # Micro-moment observation framework
│   └── prompts/                           # Editable agent system prompts (one per agent)
│       ├── participant_summary.md
│       ├── analysis_agent.md
│       ├── triangulation_agent.md
│       ├── persona_agent.md
│       ├── insight_agent.md
│       ├── quality_agent.md
│       └── devils_advocate.md
│
├── data/
│   ├── raw/                               # NEVER MODIFY - original source data
│   │   ├── interviews/                    # Reserved for local transcript files
│   │   ├── diary_exports/                 # Reserved for DScout exports
│   │   └── media/                         # Reserved for diary photos
│   │
│   ├── processed/                         # System-generated intermediate data
│   │   ├── participant_profiles.json      # Parsed from Google Sheets
│   │   ├── pipeline_state.json            # Tracks which agents have run per participant
│   │   ├── transcripts/                   # Cached Marvin transcripts
│   │   ├── marvin_summaries/              # Cached Marvin AI summaries
│   │   ├── researcher_notes/              # Parsed per-participant notes
│   │   ├── participant_summaries/         # Agent 0 output
│   │   ├── coded_segments/                # Agent 1 output
│   │   ├── triangulated_data/             # Agent 2 output
│   │   ├── personas/                      # Agent 3 output
│   │   ├── insights/                      # Agent 4 output
│   │   ├── qa_results/                    # Agent 5 output
│   │   ├── advocate_results/              # Agent 6 output
│   │   ├── glean_cache/                   # Cached Glean query results
│   │   └── business_context_sources/      # Cached strategy doc snapshots
│   │
│   └── reference/                         # Static lookups and mappings
│       ├── participant_map.json           # Links participant IDs across all sources
│       ├── codebook.json                  # Theme hierarchy (evolves during analysis)
│       ├── discussion_guide_online.md     # Synced from Google Docs
│       └── discussion_guide_inhome.md     # Synced from Google Docs
│
├── src/
│   ├── __init__.py
│   │
│   ├── loaders/                           # Data ingestion modules
│   │   ├── __init__.py
│   │   ├── marvin_loader.py               # Marvin MCP transcript fetcher
│   │   ├── gworkspace_loader.py           # Google Workspace sync
│   │   └── glean_loader.py                # Glean strategic context provider
│   │
│   ├── storage/                           # Data persistence layer
│   │   ├── __init__.py
│   │   ├── vector_store.py                # ChromaDB semantic search
│   │   ├── codebook.py                    # Theme/code management
│   │   └── state_manager.py               # Pipeline progress tracking
│   │
│   ├── agents/                            # Analysis agents
│   │   ├── __init__.py
│   │   ├── base_agent.py                  # Shared LLM infrastructure
│   │   ├── summary_agent.py               # Agent 0: Participant summaries
│   │   ├── analysis_agent.py              # Agent 1: Deep coding + quote scoring
│   │   ├── triangulation_agent.py         # Agent 2: Cross-referencing
│   │   ├── persona_agent.py               # Agent 3: Personas + journeys
│   │   ├── insight_agent.py               # Agent 4: Strategic insights
│   │   ├── quality_agent.py               # Agent 5: QA validation
│   │   ├── advocate_agent.py              # Agent 6: Devil's advocate
│   │   └── deep_dive_agent.py             # Optional guided second pass
│   │
│   ├── pipeline/                          # Orchestration
│   │   ├── __init__.py
│   │   └── orchestrator.py                # LangGraph agent graph
│   │
│   └── generators/                        # Output generators
│       ├── __init__.py
│       ├── report_generator.py            # Full research report
│       ├── persona_cards.py               # Formatted persona profiles
│       ├── journey_viz.py                 # Mermaid journey diagrams
│       ├── evidence_formatter.py          # Quote citation formatting
│       ├── quote_library.py               # Ranked quotes per theme
│       ├── tension_map.py                 # Paradox/tension visualization
│       ├── emotional_journey.py           # Emotional arc analysis
│       ├── competitive_map.py             # Competitor perception mapping
│       ├── language_patterns.py           # Word/metaphor analysis
│       ├── value_equations.py             # Value components per persona
│       └── micro_moments.py               # In-home behavioral insights
│
├── notebooks/                             # Interactive analysis workflow
│   ├── 01_ingest_data.ipynb
│   ├── 02_participant_summaries.ipynb
│   ├── 03_run_coding.ipynb
│   ├── 04_triangulate.ipynb
│   ├── 05_build_personas.ipynb
│   ├── 06_generate_insights.ipynb
│   ├── 07_quality_and_challenge.ipynb
│   ├── 08_deep_dive.ipynb
│   └── 09_export_deliverables.ipynb
│
├── output/                                # Final deliverables
│   ├── report/
│   ├── personas/
│   ├── journeys/
│   ├── qa_report/
│   ├── devils_advocate/
│   ├── quotes/
│   ├── participant_summaries/
│   ├── enrichments/
│   ├── micro_moments/
│   ├── executive_summary/
│   ├── data_exports/
│   └── archive/                           # Date-prefixed previous versions
│
└── scratch/                               # Temporary experiments
```

## Key Principles

- **Raw data is immutable** -- never modify files in `data/raw/`.
- **Processed data is regenerable** -- everything in `data/processed/` can be rebuilt by re-running agents.
- **Output archiving** -- before overwriting any file in `output/`, the existing version is moved to `output/archive/` with a date prefix.
- **Traceability** -- every insight links back to coded segments which link back to participant quotes with timestamps.
- **Human-in-the-loop** -- the pipeline pauses at 3 checkpoints for researcher review.
