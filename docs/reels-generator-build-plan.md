# AI Reels Generator — Build Plan (v1 MVP)

Execution order for the spec in `reels-generator-build-spec.md` (referenced below as §). Each phase has a done-when condition — don't move to the next phase until it's met.

---

## Phase 0 — Infra Setup

1. Create GCP project, attach $300 credit, enable: Cloud Run, Cloud Tasks, Cloud Storage, Secret Manager.
2. Create Supabase project.
3. Create GCS bucket (§3 Storage).
4. Load secrets into GCP Secret Manager per §12 list.
5. Scaffold repo per structure below.

### Project Structure

```
reels-generator/
├── backend/                      # FastAPI — §5 API endpoints
│   ├── app/
│   │   ├── main.py               # app entrypoint
│   │   ├── routers/
│   │   │   ├── videos.py         # upload-url, process, status, reels
│   │   │   └── reels.py          # download
│   │   ├── services/
│   │   │   ├── gcs.py            # signed URL gen (§7)
│   │   │   ├── supabase.py       # DB client, RLS-aware queries
│   │   │   └── tasks.py          # Cloud Tasks enqueue (§6)
│   │   ├── models/
│   │   │   └── schemas.py        # Pydantic request/response models
│   │   └── config.py             # env/secrets loader (§12)
│   ├── tests/
│   ├── Dockerfile
│   └── requirements.txt
│
├── worker/                       # Video pipeline — §6, §8, §9
│   ├── worker/
│   │   ├── pipeline.py           # state machine orchestration (§6)
│   │   ├── stages/
│   │   │   ├── validate.py       # ffprobe checks (§9)
│   │   │   ├── transcribe_plan.py # Gemini Call 1 (§8)
│   │   │   ├── review.py         # Gemini Call 2 + retry loop (§8)
│   │   │   ├── reframe.py        # YOLOv8/MediaPipe + letterbox fallback (§9)
│   │   │   ├── stitch.py         # FFmpeg concat + re-encode (§9)
│   │   │   └── captions.py       # ASS subtitle burn-in (§9)
│   │   ├── gemini/
│   │   │   ├── client.py         # Gemini API wrapper
│   │   │   ├── schemas.py        # structured output JSON schemas (§8)
│   │   │   └── prompts.py        # prompt templates, generator + reviewer
│   │   └── config.py
│   ├── tests/
│   ├── Dockerfile                # deployed as Cloud Run Job (§3)
│   └── requirements.txt
│
├── frontend/                     # React + Tailwind — §5 consumer, Phase 8
│   ├── src/
│   │   ├── pages/
│   │   │   ├── Login.tsx
│   │   │   ├── Upload.tsx
│   │   │   ├── Status.tsx        # pipeline stage polling
│   │   │   └── Gallery.tsx       # reel preview/select/download
│   │   ├── components/
│   │   ├── lib/
│   │   │   ├── supabase.ts       # auth client
│   │   │   └── api.ts            # backend API client
│   │   └── App.tsx
│   ├── package.json
│   └── tailwind.config.js
│
├── db/
│   └── schema.sql                # tables + RLS policies (§4, §7)
│
├── docs/
│   ├── reels-generator-build-spec.md
│   └── reels-generator-build-plan.md
│
└── .env.example                  # lists §12 secret keys, no values
```

**Notes:**
- `worker/` is deployed separately from `backend/` (Cloud Run Job vs Service) — render stage needs no HTTP timeout ceiling (§3).
- Each file under `worker/worker/stages/` maps 1:1 to a pipeline stage in §6 — keeps state-machine debugging traceable to one file per stage.
- `db/schema.sql` is the only place table definitions live — §4 in the spec doc should link here, not duplicate it, once this file exists.

**Done when:** empty FastAPI app deploys to Cloud Run; empty React app deploys to Vercel/Firebase; both can read a test secret from Secret Manager.

---

## Phase 1 — Database & Auth

1. Create tables per §4 schema: `videos`, `transcripts`, `edit_plans`, `reels`, `jobs`.
2. Apply RLS policies: `user_id = auth.uid()` on all tables (§4, §7).
3. Wire Supabase Auth SDK into frontend — email + Google/X/Instagram login.
4. Add ToS + content-ownership checkbox at signup, logged with timestamp (§7, §2).
5. Enforce email verification before any upload-related endpoint responds.

**Done when:** a user can sign up, verify email, accept ToS, log in — and a second test user cannot read the first user's rows via direct API call (RLS test, not just UI test).

---

## Phase 2 — Upload Flow

1. Build `POST /videos/upload-url` — returns signed GCS URL, 15-min TTL (§5, §7).
2. Build `POST /videos/{id}/process` — confirms upload, writes `videos` row with status `UPLOADED`, enqueues Cloud Task (§5, §6).
3. Enforce size cap (500 MB) client-side and server-side (§10).
4. Build `ffprobe` validation step — reject bad codec/container/zero duration before any further compute (§9, §6 `VALIDATING`).

**Done when:** valid video uploads and reaches `VALIDATING → VALIDATED` state; corrupt/oversized files are rejected with a clear error and zero compute spent downstream.

---

## Phase 3 — Gemini Integration: Transcript + Edit Plan

1. Implement Call 1 (§8) — send video GCS URI to `gemini-3.1-flash-lite`, request structured JSON (transcript + N candidates).
2. Enforce schema validation on response; auto-reprompt on malformed JSON (§8).
3. Validate every candidate's segment timestamps against actual video duration; discard invalid ranges (§8).
4. Persist transcript to `transcripts`, candidates to `edit_plans` (status: pending review).

**Done when:** a validated video produces 3–5 schema-valid candidate edit plans with plausible timestamps, stored in DB.

---

## Phase 4 — Gemini Integration: Reviewer Loop

1. Implement Call 2 (§8) — reviewer scores each candidate (coherence, hook, cut quality, overall).
2. Apply accept threshold `overall_score >= 0.7` (§8).
3. On `revise`: feed `feedback` back into Call 1 prompt, regenerate — cap at 2 attempts (§6, §8).
4. On retries exhausted: fall back to next-best candidate by original `hook_score`, skip further review (§8).

**Done when:** a low-quality candidate is caught, revised, and either improves above threshold or falls back correctly — verify with a deliberately bad test video (noisy audio, no clear speaker).

---

## Phase 5 — Video Processing: Reframe & Segmentation

1. Implement PySceneDetect pre-pass — split source into scenes (§9).
2. Implement YOLOv8/MediaPipe subject detection per scene.
3. Implement crop logic: single confident subject → tracked dynamic crop.
4. Implement **letterbox fallback**: multiple/no confident subject → preserve full frame, never guess a bad crop (§9, §11).

**Done when:** a single-speaker talking-head video reframes cleanly to 9:16; a multi-speaker/screen-share video falls back to letterbox instead of cutting off a face — verify both cases explicitly.

---

## Phase 6 — Video Processing: Cut, Stitch, Caption

1. Implement FFmpeg cut per segment from accepted edit plan.
2. Implement concat demuxer to stitch non-continuous segments into one file (§9).
3. Single re-encode pass post-stitch for consistency (libx264, 1080x1920) (§9).
4. Generate ASS subtitles from `captions` array, burn in via FFmpeg (§9).
5. Wire into `RENDERING` job stage; on partial failure (e.g. reframe fails, cut succeeded), ship degraded raw-cut fallback rather than nothing (§6).

**Done when:** an accepted edit plan with 3 non-continuous segments (e.g. 10s+5s+10s) produces one coherent captioned 9:16 MP4 — no jump-cut glitches, no audio desync.

---

## Phase 7 — Job Orchestration End-to-End

1. Wire full state machine: `UPLOADED → VALIDATING → TRANSCRIBING_PLANNING → REVIEWING → RENDERING → READY` (§6).
2. Implement stage-level retry (not full-pipeline restart) on failure.
3. Implement `FAILED` terminal state with last-successful-stage + partial output retained, user notified.
4. Store intermediate artifacts (transcript, edit plan JSON) independently so downstream failure never re-triggers upstream Gemini calls (§6, §11).

**Done when:** killing the worker mid-`RENDERING` and restarting resumes from `RENDERING`, not from `UPLOADED` — verify by force-killing a job mid-pipeline.

---

## Phase 8 — Frontend

1. Auth screens (signup/login/ToS gate) — Phase 1 backend.
2. Upload screen with progress bar, size-cap validation.
3. Status polling (`GET /videos/{id}/status`) with visible pipeline stage.
4. Gallery view (`GET /videos/{id}/reels`) — 3–5 reels, preview + select.
5. Download (`GET /reels/{id}/download`, signed URL).

**Done when:** full user journey — signup → upload → wait → preview gallery → download — works without any manual backend intervention.

---

## Phase 9 — Risk Regression Pass

Run through §11 explicitly, one test per row, before calling MVP done:

| Test | Expected behavior |
|---|---|
| Upload corrupt file | Rejected at `VALIDATING`, no compute spent |
| Upload oversized file | Rejected client + server side |
| Multi-speaker video | Letterbox fallback, not bad crop |
| Force malformed Gemini response (mock) | Auto-reprompt, not silent accept |
| Deliberately low-quality candidate | Reviewer catches it, revises or falls back |
| Kill worker mid-render | Resumes from `RENDERING`, not from scratch |
| Second user attempts cross-user data read | RLS blocks it at DB layer |

**Done when:** every row passes. This is the MVP exit gate — not feature completeness, this.

---

## Phase 10 — Deploy

1. Deploy backend to Cloud Run (Service for API, Jobs for render stage) (§3).
2. Confirm Cloud Tasks queue routes correctly in production.
3. Confirm Secret Manager injection works in deployed environment, not just local.
4. Smoke test full pipeline against a real ~50MB test video in production.

**Done when:** a real user, outside your dev environment, completes the full journey in Phase 8 successfully.
