---
name: log-insight
description: Chunked inductive log analysis for Codex. Use when the user asks to analyze application logs by splitting a log file into fixed-size tail chunks, sending each chunk to a separate sub-agent, comparing each chunk against the current repository's documentation and rules, and merging the sub-agent summaries into one report. Accepts requests shaped like --path logs/app.log --context 256 --chunks 7.
---

# Log Insight

## Contract

Act as the orchestrator. Do not analyze log contents yourself.

Use the user's language for reports and user-facing explanations. Keep log lines, code identifiers, exception names, file paths, and technical terms as written.

This skill is intentionally inductive: each sub-agent reads one whole chunk and reasons from the complete chunk plus project context. Sub-agents must not use search or filtering tools for analysis.

## Required Input

Parse the user's request for exactly these required flags:

```text
--path <log_path> --context <context_kchars> --chunks <chunk_count>
```

Example:

```text
--path logs/log.log --context 256 --chunks 7
```

Interpretation:

- `--path`: path to the source log file.
- `--context`: context window in thousands of characters. `256` means `256000` characters.
- `--chunks`: maximum number of chunks to analyze.
- `chunk_size_chars = floor(context * 1000 * 0.70)`.
- Start from the end of the log file. Keep slicing backward by `chunk_size_chars` until the log is exhausted or `--chunks` chunks are produced.
- Number produced chunks oldest to newest. Chunk `1` is the oldest analyzed chunk, chunk `N` is the most recent chunk.

If any required flag is missing, ask for the missing value. Do not invent defaults.

## Phase 1: Build Project Briefing First

Before splitting or launching sub-agents, read repository documentation and rules. Reading repository docs is allowed. Reading log content for analysis is not.

Build one `PROJECT_BRIEFING` for all sub-agents:

- Read `AGENTS.md` and `CLAUDE.md` if present.
- Read `docs/*.md` if present.
- Read `README.md` if it contains runtime or business context.
- Include business rules and workflow rules with high fidelity. If `docs/rules.md`, `docs/business_rules.md`, or equivalent files exist, include their important rule text directly.
- Summarize architecture, runtime flow, components, expected success path, domain rules, configuration requirements, state transitions, and known invariants.
- Keep the briefing compact enough to fit alongside one chunk in a sub-agent context.

The briefing must be passed directly in every sub-agent prompt. Sub-agents must not read project docs or source files themselves.

## Phase 2: Split Log Into Chunk Files

Use the bundled splitter script. Resolve the script path relative to this `SKILL.md`; do not assume the skill is installed in a specific repository.

Create an explicit run directory, for example:

```text
.agent/log-insight-runs/<yyyyMMdd-HHmmss>/
```

Then run:

```powershell
uv run python <skill_dir>/scripts/split_log_chunks.py --path <log_path> --context <context_kchars> --chunks <chunk_count> --output-dir <run_dir> --encoding utf-8
```

If `uv` is not available for the current workspace, run the same script with `python` and state that `uv` was unavailable.

Use the JSON manifest printed by the script as the source of chunk paths, character offsets, chunk sizes, requested chunks, and actual chunks. Do not open the original log file yourself to inspect content.

## Phase 3: Launch One Sub-Agent Per Chunk

Launch exactly one sub-agent for each produced chunk. The sub-agents should run in parallel when possible.

Do not assign multiple chunks to one sub-agent. Do not analyze a chunk locally to "help" a sub-agent.

Each sub-agent receives:

- `PROJECT_BRIEFING`
- Its chunk file path
- Its chunk number and total chunk count
- Character offset metadata from the manifest
- The analysis instructions below

## Sub-Agent Prompt Template

Fill every placeholder before sending.

```text
You are a log chunk analyzer. Analyze exactly one generated chunk file.

Use the user's language for prose in your final answer. Keep log lines, exception names, code identifiers, paths, and technical terms as written.

Hard tool rules:
- You may read exactly one file: "{CHUNK_PATH}".
- Read that file in full. On PowerShell, use: Get-Content -Raw -LiteralPath "{CHUNK_PATH}".
- Do not read the original log file.
- Do not read project documentation, source files, config files, or any other file.
- Do not use rg, grep, Select-String, findstr, awk, sed, tail, head, cat with filters, Python scripts, parsers, or any search/filtering command for analysis.
- After reading the chunk, use no more tools. Analyze only from the full chunk text and PROJECT_BRIEFING.

Purpose:
This is inductive log analysis. You must reason from the complete chunk content, not from filtered matches. Compare observed behavior against the project rules and expected runtime flow.

Chunk metadata:
- Chunk: {CHUNK_NUMBER}/{TOTAL_CHUNKS}
- Ordering: chunk 1 is the oldest analyzed chunk, chunk {TOTAL_CHUNKS} is the newest.
- Source character range: {CHAR_START}-{CHAR_END}
- Chunk characters: {CHARS}

PROJECT_BRIEFING:
---
{PROJECT_BRIEFING}
---

Analysis checklist:
1. Errors and exceptions:
   - ERROR, CRITICAL, Exception, Traceback, failed operations.
   - Group repeated patterns. Count exact occurrences.
   - Capture first and last timestamps for each pattern.
2. Warnings and degradation:
   - WARNING lines, retries, timeouts, resource pressure, slow operations, repeated degraded states.
3. Logic and workflow integrity:
   - Missing start/end pairs, orphaned operations, contradictory decisions, impossible state transitions.
   - Compare observed state transitions, counters, decisions, configuration assumptions, and domain rules against PROJECT_BRIEFING.
4. Timing and volume anomalies:
   - Large gaps, sudden bursts, stalled cycles, unusually long iterations.
5. External dependencies:
   - API failures, DB failures, rate limits, connection errors, DNS/TLS errors.
6. Cross-chunk metrics:
   - Produce structured metrics so the orchestrator can compare chunks.

For every finding, include:
- Exact count.
- First timestamp and last timestamp from the chunk when available.
- One or two representative log lines as evidence.
- Why this violates or stresses the expected behavior.
- Severity: CRITICAL, MEDIUM, or LOW.

Output exactly this structure:

## Chunk {CHUNK_NUMBER}/{TOTAL_CHUNKS}
**Range:** chars {CHAR_START}-{CHAR_END}
**Time range:** <first timestamp> -> <last timestamp>

### CRITICAL
- **<title>**: <description, exact count, first/last timestamp>
  - Evidence: `<representative log line>`
  - Expected behavior: <from PROJECT_BRIEFING, or N/A>
  - Root cause hypothesis: <best hypothesis from chunk context>

### MEDIUM
- **<title>**: <description, exact count, first/last timestamp>
  - Evidence: `<representative log line>`
  - Expected behavior: <from PROJECT_BRIEFING, or N/A>

### LOW
- **<title>**: <description, exact count, first/last timestamp>
  - Evidence: `<representative log line>`

### Chunk Statistics
- Characters analyzed: {CHARS}
- Errors (ERROR/CRITICAL/Exception/Traceback): <number>
- Warnings (WARNING): <number>
- Max timestamp gap: <number or N/A>
- Active components: <comma-separated list>
- Health summary: <one sentence>

### Cross-Chunk Signals
- errors_total: <number>
- warnings_total: <number>
- critical_findings_total: <number>
- medium_findings_total: <number>
- low_findings_total: <number>
- max_gap_seconds: <number or N/A>
- active_components: <comma-separated list>
- pattern_counts:
  - <pattern name>: <count>
```

If there are no findings in a severity section, write `None`.

Before returning, verify:

- Every finding has an exact count.
- Every finding has first and last timestamps when timestamps exist in the chunk.
- `### Cross-Chunk Signals` is present.
- No tool was used after the full chunk read.

## Phase 4: Consolidate

Wait for every sub-agent to finish. Base the final report only on sub-agent responses and the project briefing. Do not open chunk files or the source log file for your own analysis.

Merge duplicate findings:

- Same root cause across chunks becomes one report item.
- Aggregate total count, affected chunks, and full time range.
- Keep the clearest evidence line.
- Mark whether the issue is isolated, stable, improving, worsening, or spiking across chunks.

Build a metric timeline from each `### Cross-Chunk Signals` section:

```markdown
| Metric | Chunk 1 | Chunk 2 | ... | Chunk N | Trend |
|--------|---------|---------|-----|---------|-------|
| errors_total | 0 | 2 | ... | 7 | worsening |
```

Sort findings:

1. CRITICAL before MEDIUM before LOW.
2. More affected chunks before fewer affected chunks.
3. Higher total count before lower total count.

## Final Report Shape

Return one report in chat:

```markdown
# Log Insight Report

## Parameters
- **File:** <path>
- **Context:** <context>k chars, chunk size <chunk_size_chars> chars (70%)
- **Chunks requested:** <requested>
- **Chunks analyzed:** <actual>
- **Analyzed characters:** <sum>
- **Method:** one sub-agent per chunk; sub-agents read full chunks without search/filter tools

## Project Context Used
<short summary of briefing sources and key rules>

## Chunk Summary
| Chunk | Range | Time range | Critical | Medium | Low | Status |
|-------|-------|------------|----------|--------|-----|--------|

## Metric Trends
| Metric | Chunk 1 | Chunk 2 | ... | Chunk N | Trend |
|--------|---------|---------|-----|---------|-------|

## Critical Problems
### <title>
- **Where:** chunks <list>, <total count> occurrences
- **Evidence:** `<representative log line>`
- **Expected behavior:** <project rule or N/A>
- **Impact:** <impact>
- **Trend:** <isolated/stable/improving/worsening/spike>
- **Recommendation:** <actionable next step>

## Medium Problems
<same compact structure>

## Low Notes
- <one-line notes with chunk references>

## Aggregated Statistics
- Errors total: <number>
- Warnings total: <number>
- Highest max gap: <number or N/A>
- Active components: <merged list>

## Priority Actions
1. <highest-value action>
2. <next action>
3. <next action>
```

If all chunks are healthy, still include Parameters, Project Context Used, Chunk Summary, Metric Trends, and Aggregated Statistics, then state that no significant issues were found.
