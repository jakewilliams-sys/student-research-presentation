# Student Research Analysis System

Multi-agent qualitative research analysis system for Deliveroo's student food and delivery habits study. Processes interview transcripts, diary studies, participant context data, and researcher notes to produce a comprehensive research report with full evidence traceability.

## Quick Start

```bash
# 1. Install dependencies
pip install -r requirements.txt

# 2. Set your API key
export ANTHROPIC_API_KEY="sk-..."

# 3. Sync data from external sources
python main.py sync-google   # Pull participant data + researcher notes
python main.py sync-marvin   # Pull interview transcripts

# 4. Ingest into vector store
python main.py ingest

# 5. Run the full analysis pipeline
python main.py analyze

# 6. Generate deliverables
python main.py generate
```

## Data Sources

| Source | What | Access |
|--------|------|--------|
| Marvin | 14+ interview transcripts with AI summaries | Marvin MCP |
| Google Sheets | 34 participant profiles across 3 segments | Google Workspace MCP |
| Google Docs | Researcher notes, discussion guides | Google Workspace MCP |
| Glean | Internal Deliveroo strategy documents | Glean MCP |
| DScout | Diary study exports (deferred) | Manual import |

## Analysis Pipeline

The system runs 7 agents in sequence with human-in-the-loop checkpoints:

1. **Summary Agent** -- Holistic participant understanding before coding
2. **Analysis Agent** -- 4-pass deep coding with quote quality scoring
3. **Triangulation Agent** -- Cross-referencing and segment comparison
4. **Persona Agent** -- Behavioral clustering and journey mapping
5. **Insight Agent** -- Strategic insight distillation with business context
6. **Quality Agent** -- Evidence audit and confidence scoring
7. **Devil's Advocate Agent** -- Challenge findings, identify blind spots

## Interactive Workflow

Use the Jupyter notebooks in `notebooks/` for step-by-step analysis with review at each stage. See `docs/project-structure.md` for the full folder layout.

## CLI Reference

```bash
python main.py ingest                          # Load all data sources
python main.py analyze                         # Run all agents
python main.py analyze --agent summary         # Run a single agent
python main.py generate                        # Generate all deliverables
python main.py generate --output report        # Generate specific output
python main.py sync-google                     # Refresh Google Workspace data
python main.py sync-marvin                     # Refresh Marvin transcripts
python main.py deep-dive --focus "topic"       # Guided second-pass analysis
python main.py status                          # Check pipeline progress
python main.py validate                        # Verify data integrity
python main.py export --format json            # Export all data
```

## Research Objectives

- **RO1:** Map the full spectrum of student eating moments and contexts
- **RO2:** Identify triggers and barriers to food delivery ordering
- **RO3:** Understand emotional and social dimensions of delivery
- **RO4:** Track how food habits evolve from student to graduate
- **RO5:** Identify opportunities for Deliveroo engagement

## Segments

- Undergraduate (n=18)
- Postgraduate (n=5)
- Early Graduate (n=5)
- In-Home (n=6, with live order observation)
