---
description: Create a spec file for the next AI Reels Generator phase
argument-hint: "Phase number, feature-slug: optional 1-2 line brief — e.g. 1 database-auth: Supabase tables, RLS policies, email/social login gating upload access"
allowed-tools: Read, Write, Glob
---

You are a senior developer scoping the next phase for the AI Reels
Generator — a FastAPI + React/Vite app on Supabase + GCP that converts
long-form video into caption-ready vertical reels. Always follow the
rules in CLAUDE.md.

User input: $ARGUMENTS

## Step 1 — Parse the arguments

From $ARGUMENTS extract:

1. `phase_number` — zero-padded to 2 digits: 1 → 01, 11 → 11
2. `feature_title` — human readable title in Title Case, matching the
   phase name in `docs/reels-generator-build-plan.md` (e.g. "Database And Auth")
3. `feature_slug` — file/git-safe slug: lowercase, kebab-case, only
   a-z, 0-9 and -, maximum 40 characters (e.g. `database-auth`)
4. `feature_brief` — everything after the colon, if present: the user's
   own 1–2 line description of what to build and why. Optional — if
   absent, derive the brief from the phase's description in the plan.
5. `suggested_branch_name` — format: `phase-<phase_number>-<feature_slug>`
   (e.g. `phase-01-database-auth`) — for the user's own reference only,
   this command does not create or touch any git branch.

If you cannot infer these from $ARGUMENTS, ask the user to clarify
before proceeding.

## Step 2 — Check for duplicate or conflicting specs

Read every file in `.claude/specs/`. If a spec already exists for the
same or a very similar phase, tell the user and ask whether to proceed
anyway, overwrite, or stop. Do not silently overwrite.

## Step 3 — Research the project

Read these before writing anything:
- `CLAUDE.md` (root) — conventions, env vars, git workflow
- `docs/reels-generator-build-spec.md` — the spec, referenced below as §N
- `docs/reels-generator-build-plan.md` — execution order, referenced as Phase N
- `backend/app/config.py` and `backend/app/main.py` — existing backend
- `db/schema.sql` — existing tables (if any exist yet)
- All files in `.claude/specs/` — for consistency of style and to
  avoid duplicating/conflicting with prior phases

Check `docs/reels-generator-build-plan.md` to confirm this phase's "Done when"
condition is not already met. If it is, warn the user and stop.

Compare `feature_brief` against what you find. If the brief conflicts
with a decision already recorded in the spec, plan, or CLAUDE.md — for
example, suggesting local-only storage when the architecture is GCS,
or skipping RLS, or introducing a new paid dependency without it being
flagged — do not silently reinterpret the brief to make it fit. Flag
the conflict to the user explicitly and ask how they want to proceed.

## Step 4 — Write the spec

Generate a spec document with this exact structure:

---
# Spec: <feature_title> (Phase <phase_number>)

## Overview
Expand the user's brief ("<feature_brief>") into one paragraph, grounded
in what Step 3 found. Cite the relevant plan phase and spec section(s).
Note explicitly if anything in the brief had to be adjusted, and why.

## Depends on
Which previous phases this phase requires to already be complete.
If this is the first phase: "None — this is the foundational phase."

## API endpoints
Every new/changed FastAPI route:
- `METHOD /path` — description — access level (public/authenticated) —
  spec §5 reference
If none: "No new routes."

## Database changes
Any new tables, columns, or RLS policies needed in `db/schema.sql`.
Verify against the current schema before writing this. Every new table
must specify its RLS policy (`user_id = auth.uid()` pattern per spec
§4/§7), unless auth hasn't landed yet. If none: "No database changes."

## Worker / pipeline changes
For phases touching `worker/` (Gemini calls, video processing stages):
which stage file(s) change, referencing spec §6/§8/§9, and which
stage(s) of the state machine are affected. If none: "No worker changes."

## Frontend changes
- **Create:** new pages/components under `frontend/src/`, with path
- **Modify:** existing pages/components and what changes
If none: "No frontend changes."

## Files to change
Every existing file that will be modified.

## Files to create
Every new file that will be created, including this phase's own
`CLAUDE.md` if it doesn't have one yet.

## New dependencies
Any new pip or npm packages. Flag clearly if a proposed dependency is a
new paid service or requires a new API key beyond what's already
approved (Gemini, GCP, Supabase) — this must be raised to the user
before proceeding. If none: "No new dependencies."

## Rules for implementation
Always include, plus anything specific to this feature:
- Never hardcode secrets — read via `config.py`'s `Settings`, sourced
  from `.env` locally / GCP Secret Manager in deployed environments
- Every new table gets RLS (`user_id = auth.uid()`) — no cross-user
  reads at the DB layer, regardless of API-level bugs (spec §4, §7)
- Upload/download URLs: signed, 15-min TTL only (spec §7)
- Each pipeline stage writes its output before advancing state —
  retries re-run only the failed stage, never duplicate work (spec §6)
- Tailwind utility classes only — never hardcode hex colors
- This phase must be testable end-to-end on its own before the next
  phase begins
- Do not add infrastructure ahead of when it's actually needed for
  this phase
- Cite the relevant spec section (§N) in code comments or commit
  messages where a decision traces back to a specific requirement

## Definition of done
A specific, testable checklist matching this phase's "Done when"
condition in `docs/reels-generator-build-plan.md`. Each item must be verifiable
by running the app manually, and by any automated tests this phase
includes.
---

## Step 5 — Save the spec

Save to: `.claude/specs/<phase_number>-<feature_slug>.md`
(Create the `.claude/specs/` folder first if it doesn't exist.)

## Step 6 — Report to the user

Print a short summary in this exact format:
```
Spec file:        .claude/specs/<phase_number>-<feature_slug>.md
Title:             <feature_title>
Suggested branch:  <suggested_branch_name>
```

Then tell the user:
"Review the spec at `.claude/specs/<phase_number>-<feature_slug>.md`.
Create and switch to your branch manually (e.g. `git checkout -b
<suggested_branch_name>`), then enter Plan Mode with Shift+Tab twice to
begin implementation."

Do not print the full spec in chat unless explicitly asked.
