# PR / Issue Evolution Report — `simvltanea`

**Date:** 2026-11-17  
**Stream:** B (PR / Issue Evolution) of the Autonomous Ecosystem Retirement & Enrichment plan  
**Method:** full remote inventory via `gh` (all states), heuristic supersession detection, local git/oss evidence. Machine-readable evidence: `archive/incubation/2026-11-17-pr-issue-data.json`  
**Staging run:** `09_Engineering/custody-staging/run-20261117-104235-session-retirement/`

> Supersession links below are **evidence-backed candidates**, not licensed merges. No remote PR was closed and no history was rewritten by this pass. Destructive actions are listed as ready-to-run commands for the owner or the orchestration stream.

## 1. Repository state

| Field | Value |
|---|---|
| Local path | `/Volumes/Archive4T/Projects/simvltanea` |
| GitHub remote | `4444J99/tool-video-loop-compositor` |
| Upstream archived | no |
| Default branch (remote) | main |
| Local branch | `main` |
| Dirty files | 0 |
| Linked worktrees | 1 (canonical checkout) |
| Last commit | 2026-11-17T10:13:48 — fix(silent-browser): add Firefox media.volume_scale pref and document  |
| Plan surfaces | docs/plans |

### Rename / ownership evolution

- Current canonical remote: `4444J99/tool-video-loop-compositor` — remote renamed `simvltanea` → `tool-video-loop-compositor`; local directory name retained.
- Old `owner/repo#N` references still resolve through GitHub's redirect, but new cross-references should use the current slug so the link survives a future transfer.

## 2. PR inventory

| Metric | Count |
|---|---|
| PRs (all states) | 102 |
| Merged | 100 |
| Open | 0 |
| Closed unmerged | 2 |

Closed-unmerged classification:

| Class | Count |
|---|---|
| closed without successor | 2 |

## 3. Evolution decisions (old → new)

_No supersession links detected: no closed-unmerged PR in this repo has a traced successor._

## 4. Items marked archived

- **100 merged PRs** — resolved, no action; history is the archive.
- **2 PRs closed without a traced successor** — archived as abandoned. Titles are retained in the evidence file in case a later re-cut needs the original scope.

## 5. Open PR triage

_No open PRs._

## 6. Issues

| Metric | Count |
|---|---|
| Issues (all states) | 45 |
| Open | 5 |
| Open and idle > 45 days | 0 |

## 7. Follow-up flags

- No open follow-ups: this repo is at lifecycle steady state.

## 8. Provenance and limits

- PR/issue inventory: `gh pr list`/`gh issue list --state all` for `4444J99/tool-video-loop-compositor`, captured 2026-11-17.
- Supersession classes: explicit `supersedes #N` in title; dependency retry (same package + directory, newer bump merged); rewrite series (identical title stem, later PR merged); producer retirement (Limen/Jules branch, no successor); otherwise abandoned.
- Heuristic limit: a title-stem match can link two genuinely different changes. Treat §3 as a review queue, not as settled provenance.
- No remote mutation was performed: no PR closed, no issue closed, no branch deleted.
