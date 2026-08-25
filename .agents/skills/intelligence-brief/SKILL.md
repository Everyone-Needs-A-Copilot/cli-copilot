---
name: intelligence-brief
description: >-
  Generate strategic intelligence reports from copilot data — Insights Copilot articles,
  forces, synthesis, BI analytics, and Brevo campaign data.
  Use when preparing intelligence briefs, market analysis, or strategic reports.
triggers:
  keywords: ["intelligence", "brief", "report", "analysis", "strategic", "insights",
             "synthesis", "forces", "market", "competitive", "dossier", "signals"]
allowed-tools: Read, Bash, Grep, Glob
execution:
  steps:
    - name: weekly-brief
      script: scripts/weekly-brief.sh
      description: Gather signals, analyze forces, run synthesis, generate report, check costs
  verify:
    - name: insights-healthy
      command: copilot insights health --json
      expect: 'exit_code == 0'
---

# Intelligence Brief

## Overview

Generate comprehensive intelligence reports by combining data from Insights Copilot (articles, forces, synthesis), BI analytics, and Brevo campaign metrics. Produces actionable briefs for strategic decision-making.

## Define Done

An intelligence brief is complete when:

- [ ] Signals gathered from Insights dashboard (activity, signals, latest report)
- [ ] Force landscape analyzed (force list, stats, patterns)
- [ ] Synthesis run and correlations identified
- [ ] Report generated from collected intelligence
- [ ] Cost of intelligence operations tracked

## Prerequisites

- Insights Copilot configured: `INSIGHTS_BASE_URL`, `INSIGHTS_API_KEY` in `.env`
- Verify: `copilot insights health --json`
- For full briefs, also configure: Brevo

## Instructions

### Step 1: Gather Intelligence Signals (REQUIRED)

```bash
# Latest strategic signals from dashboard
copilot insights dashboard signals --json

# Recent activity feed
copilot insights dashboard activity --json

# Latest report
copilot insights dashboard latest-report --json

# Dashboard health overview
copilot insights dashboard summary --json
```

### Step 2: Analyze Strategic Forces (REQUIRED)

```bash
# List all identified forces
copilot insights forces list --json

# Get details on a specific force
copilot insights forces get --id "$FORCE_ID" --json

# Force statistics summary
copilot insights forces stats --json
```

### Step 3: Review Intelligence Articles (REQUIRED)

```bash
# List recent articles
copilot insights articles list --json

# Get a specific article
copilot insights articles get --id "$ARTICLE_ID" --json

# Article statistics
copilot insights articles stats --json

# Find similar articles (for pattern detection)
copilot insights articles similar --id "$ARTICLE_ID" --json

# Generate intelligence from article data
copilot insights articles generate-intel --id "$ARTICLE_ID" --json
```

### Step 4: Run Synthesis (REQUIRED)

```bash
# Run full synthesis pipeline
copilot insights synthesis run --json

# Get forces identified by synthesis
copilot insights synthesis forces --json

# Cross-force correlations
copilot insights synthesis correlations --json

# Emerging patterns
copilot insights synthesis patterns --json

# Pipeline status
copilot insights synthesis status --json
```

### Step 5: Generate Reports (REQUIRED)

**Report type routing:**

| Report Type | Command | When to Use |
|-------------|---------|-------------|
| From existing articles | `copilot insights reports from-existing --json` | Summarize collected intelligence |
| Topical report | `copilot insights reports topical --topic "topic" --json` | Focused analysis on a theme |
| From fresh scan | `copilot insights reports from-scan --json` | New intelligence gathering |
| Article-centric | `copilot insights reports article-centric --article-id "$ID" --json` | Deep dive on one article |

### Step 6: Enrich with Company Dossiers (OPTIONAL)

```bash
# List existing dossiers
copilot insights dossiers list --json

# Get specific company dossier
copilot insights dossiers get --id "$DOSSIER_ID" --json

# Create new dossier
copilot insights dossiers create --company "Company Name" --json

# Enrich with additional data
copilot insights dossiers enrich --id "$DOSSIER_ID" --json

# Priority-ranked prospects
copilot insights prospects priority --json
```

### Step 7: Supplement with Business Data (OPTIONAL)

```bash
# BI analytics on internal data
copilot bi analyze --file "data.json" --json
copilot bi kpis --file "data.json" --json
copilot bi summary --file "data.json" --json

# Brevo campaign performance (email engagement signals)
copilot brevo campaigns list --json
copilot brevo campaigns stats --campaign-id "$CAMPAIGN_ID" --json
```

> Note: Notion was retired 2026-06-29; this step needs a replacement knowledge-base query source (TBD by owner).

### Step 8: Monitor Intelligence Costs (OPTIONAL)

```bash
# LLM cost summary
copilot insights monitoring cost-summary --json

# Costs by provider
copilot insights monitoring cost-by-provider --json

# Cost trends
copilot insights monitoring cost-trend --json

# API performance
copilot insights monitoring performance --json
```

## Examples

### Example: Weekly Strategic Brief

```bash
# 1. Dashboard overview
copilot insights dashboard summary --json
copilot insights dashboard signals --json

# 2. Force landscape
copilot insights forces stats --json
copilot insights synthesis forces --json

# 3. Emerging patterns
copilot insights synthesis patterns --json
copilot insights synthesis correlations --json

# 4. Generate report
copilot insights reports from-existing --json

# 5. Supplement with campaign data
copilot brevo campaigns list --json
```

### Example: Company Deep Dive

```bash
# 1. Get or create dossier
copilot insights dossiers create --company "TargetCorp" --json
# → {"id": "dossier-789"}

# 2. Enrich
copilot insights dossiers enrich --id "dossier-789" --json

# 3. Find related articles
copilot insights articles list --json
# → Filter for articles mentioning TargetCorp

# 4. Generate article-centric report
copilot insights reports article-centric --article-id "article-456" --json

# 5. Check Conversations for existing relationship
copilot conv intel search --query "TargetCorp" --json
```

## Error Handling

| Error Type | Symptom | Recovery |
|------------|---------|----------|
| `ConfigError` | "Missing INSIGHTS_API_KEY" | Add to `.env` |
| `AuthError` | 401 from Insights API | Verify `INSIGHTS_API_KEY` |
| `ConnectionError` | Can't reach Insights API | `copilot insights health --json`, check Coolify |
| `NotFoundError` | Article/dossier not found | List first: `copilot insights articles list --json` |
| `TimeoutError` | Synthesis takes too long | Check `copilot insights synthesis status --json` |

## Quality Tests

### Freshness Test
- Intelligence is based on recent data, not stale reports
- **PASS:** `copilot insights dashboard activity --json` shows activity within the last 7 days
- **FAIL:** Most recent activity is older than 2 weeks — signals may be outdated

### Synthesis Completeness Test
- Report includes cross-force correlations, not just individual force summaries
- **PASS:** `copilot insights synthesis correlations --json` returns correlation data included in the brief
- **FAIL:** Brief lists forces individually without identifying patterns between them

### Cost Awareness Test
- Intelligence generation costs are tracked and within budget
- **PASS:** `copilot insights monitoring cost-summary --json` checked before running expensive operations
- **FAIL:** Synthesis or report generation run without checking current cost levels

### Source Diversity Test
- Brief draws from multiple data sources, not just one
- **PASS:** Brief includes data from at least 3 sources (Insights, Conv/CRM, Brevo/BI)
- **FAIL:** Brief relies solely on Insights articles without cross-referencing other systems

## Guidelines

1. Start with dashboard signals — they show what's new since last check
2. Run synthesis before generating reports — it produces better correlations
3. Use dossier enrichment for company-specific intelligence
4. Check costs periodically — synthesis and reports consume LLM credits
5. Cross-reference Insights data with Conversations for relationship context
6. Use `copilot insights articles generate-intel` to extract structured intelligence from raw articles

## References

- Related skills: `conversation-prep`, `lead-pipeline`, `cli-router`
- Insights docs: `docs/services/16-insights.md`
- BI docs: `docs/services/13-bi.md`
