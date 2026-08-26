# AI Reels Generator — Build Spec (v1 MVP)

Single source of truth for development. Any implementation decision not listed here should be raised, not assumed.

---

## 1. Overview

Ingest one long-form video → output 3–5 ready-to-post vertical (9:16) reels with burned-in captions, auto-selected and auto-edited from the source. Target: ~50 users, GCP-credit-funded MVP.

---

## 2. Scope

**In scope:**
- Email/social sign-up + login (Supabase Auth)
- ToS acceptance + content-ownership disclaimer required before upload access
- Video upload (size-capped, resumable)
- Transcription + candidate edit-plan generation (Gemini)
- Multi-segment, non-continuous clip selection (e.g., 10s + 5s + 10s stitched into one reel)
- Automated reviewer/QA loop before a reel is finalized
- 9:16 reframing with subject tracking + letterbox fallback
- Burned-in captions
- Gallery of 3–5 reels per upload, MP4 download

**Out of scope (v1):**
- Direct social posting (Instagram/X API)
- Manual crop/caption editing UI
- Multi-speaker/screen-share reframing guarantees (best-effort only, falls back to letterbox)
- >5 reels per video

---

## 3. Architecture

### Pipeline
```
Upload → Validate → Gemini: Transcript + Edit Plan → Gemini: Reviewer
  → [pass] Render (cut → reframe → stitch → caption burn-in) → Ready
  → [fail, retries left] Regenerate edit plan with feedback → Reviewer (loop, max 2 retries)
  → [fail, retries exhausted] Fall back to next-best candidate → Render
```

### Stack

| Segment | Tool | Notes |
|---|---|---|
| Auth | Supabase Auth | RLS enforced on all tables |
| Storage | Google Cloud Storage | Signed URLs, 15-min TTL |
| LLM (transcript, edit plan, review) | Gemini 3.1 Flash-Lite | Not 2.5 — deprecated no earlier than Oct 16, 2026 |
| Reframe/segmentation | YOLOv8/MediaPipe + FFmpeg | Self-built, runs on GCP compute |
| Scene detection | PySceneDetect | Pre-pass before subject tracking |
| Captions | FFmpeg (ASS subtitles) | Burned in, one render pass |
| Job queue | Google Cloud Tasks | No persistent server |
| Backend | FastAPI on Cloud Run | Cloud Run Jobs (not Services) for render stage — avoids request timeout limits |
| Frontend | React + Tailwind | Vercel/Firebase Hosting |

---

## 4. Data Model

```sql
videos (
  id UUID PK,
  user_id UUID FK -> auth.users,
  gcs_path TEXT,
  filename TEXT,
  size_bytes BIGINT,
  duration_seconds FLOAT,
  status TEXT,          -- see §6 stages
  error_message TEXT,
  uploaded_at TIMESTAMPTZ
)

transcripts (
  id UUID PK,
  video_id UUID FK,
  gemini_model TEXT,
  raw_json JSONB,        -- full transcript w/ timestamps, speakers
  created_at TIMESTAMPTZ
)

edit_plans (
  id UUID PK,
  video_id UUID FK,
  candidate_id TEXT,      -- e.g. "c1", "c2"
  segments JSONB,          -- [{start, end}, ...]
  captions JSONB,           -- [{start, end, text}, ...]
  hook_score FLOAT,
  reviewer_score FLOAT,
  reviewer_verdict TEXT,    -- accept | revise
  reviewer_feedback TEXT,
  attempt_number INT,
  created_at TIMESTAMPTZ
)

reels (
  id UUID PK,
  video_id UUID FK,
  edit_plan_id UUID FK,
  gcs_path TEXT,
  duration_seconds FLOAT,
  status TEXT,             -- rendering | ready | failed
  created_at TIMESTAMPTZ
)

jobs (
  id UUID PK,
  video_id UUID FK,
  stage TEXT,               -- see §6
  status TEXT,               -- pending | running | done | failed
  retry_count INT DEFAULT 0,
  error_message TEXT,
  updated_at TIMESTAMPTZ
)
```

**RLS:** every table scoped `user_id = auth.uid()` (via `videos.user_id`, joined for child tables). No cross-user reads at the DB layer, regardless of API bugs.

---

## 5. API Endpoints

| Method | Path | Purpose |
|---|---|---|
| POST | `/videos/upload-url` | Returns signed GCS upload URL |
| POST | `/videos/{id}/process` | Confirms upload, enqueues Cloud Task |
| GET | `/videos/{id}/status` | Poll job/pipeline state |
| GET | `/videos/{id}/reels` | List generated reels (once ready) |
| GET | `/reels/{id}/download` | Signed download URL |

Auth handled entirely by Supabase client SDK — no custom auth endpoints.

---

## 6. Job Pipeline — Stages & State Machine

| Stage | Description | On failure |
|---|---|---|
| `UPLOADED` | File received in GCS | — |
| `VALIDATING` | `ffprobe` checks codec/container/duration/size | Reject immediately, no compute spent |
| `TRANSCRIBING_PLANNING` | Gemini call 1: transcript + N candidate edit plans | Retry stage only (not full pipeline) |
| `REVIEWING` | Gemini call 2: scores each candidate | If `overall_score < 0.7`: loop to `TRANSCRIBING_PLANNING` with feedback, max 2 retries |
| `RENDERING` | Cut → reframe → stitch → caption burn-in (FFmpeg) | Retry stage; if reframe fails but cut succeeded, ship raw cut as degraded fallback |
| `READY` | Reels available in gallery | — |
| `FAILED` | Terminal, retries exhausted | User notified; last successful stage + partial output (if any) retained |

**Idempotency:** each stage writes its output before advancing state. Retries re-run only the failed stage, never duplicate completed work.

---

## 7. Auth & Security

- OAuth (Google/X/Instagram) via Supabase's built-in PKCE flow — no custom OAuth code.
- RLS on all tables (see §4) — primary defense layer.
- JWT: 1-hour expiry, refresh token rotation (Supabase default).
- Session tokens: secure, httpOnly cookies only — never localStorage.
- Email verification required before upload access granted.
- ToS + content-ownership checkbox required at first upload — logged with timestamp, gates upload endpoint.
- Secrets (Gemini key, GCS credentials) in **GCP Secret Manager** — never in repo/env files.
- Rate limiting on login/signup endpoints.
- Upload/download URLs: signed, 15-min TTL, single-use where possible.

---

## 8. Gemini Integration

**Model:** `gemini-3.1-flash-lite` for both calls below.

### Call 1 — Transcript + Candidate Edit Plans
Input: video (GCS URI). Structured output (schema-enforced):
```json
{
  "transcript": [{"start": 0.0, "end": 3.2, "speaker": "S1", "text": "..."}],
  "candidates": [
    {
      "id": "c1",
      "segments": [{"start": 10.0, "end": 20.0}, {"start": 180.0, "end": 185.0}],
      "hook_score": 0.87,
      "theme": "short description",
      "captions": [{"start": 10.0, "end": 12.0, "text": "..."}]
    }
  ]
}
```
Candidates are non-continuous multi-segment plans (per §2 scope), not single continuous clips. Segment timestamps validated against actual video duration before use — invalid ranges discarded, not trusted.

### Call 2 — Reviewer
Input: one candidate + transcript. Output:
```json
{
  "candidate_id": "c1",
  "coherence_score": 0.9,
  "hook_score": 0.8,
  "cut_quality_score": 0.85,
  "overall_score": 0.85,
  "verdict": "accept",
  "feedback": "text, used to regenerate if verdict = revise"
}
```
Accept threshold: `overall_score >= 0.7`. Max 2 regeneration attempts; after that, fall back to the next-best candidate by original `hook_score` and render without further review.

**Malformed output:** schema validation failure → automatic reprompt, not silent accept.

---

## 9. Video Processing

- **Validation:** `ffprobe` on upload — reject invalid codec/container/zero duration before any compute.
- **Scene detection:** PySceneDetect pre-pass — subject tracking runs per scene, never across a hard cut.
- **Subject detection/reframe:** YOLOv8/MediaPipe per scene.
  - Single confident subject → dynamic crop, tracked.
  - Multiple/no confident subject → **letterbox fallback** (full frame preserved). Never guess a crop that risks cutting off a face.
- **Segment stitching:** FFmpeg concat demuxer — cut each sub-segment individually, concatenate, single re-encode pass (libx264, 1080x1920 target) for consistency.
- **Captions:** ASS subtitle burn-in via FFmpeg, generated from `captions` array in the accepted edit plan.

---

## 10. Limits (MVP)

| Constraint | Value |
|---|---|
| Max upload size | 500 MB (raise once processing capacity is measured) |
| Max reels per video | 5 |
| Max edit-plan regeneration attempts | 2 |
| Upload/download URL TTL | 15 min |
| Gemini call timeout | 10 min |
| Render stage timeout | 20 min |

---

## 11. Known Risks — Condensed

| Risk | Mitigation |
|---|---|
| Reframe fails on multi-speaker/screen-share | Letterbox fallback, not a promised feature at v1 |
| Gemini returns malformed/inconsistent JSON | Schema validation + auto-reprompt |
| "Best highlight" has no ground truth | User picks from gallery; no blind auto-publish |
| Jarring cuts in stitched multi-segment reels | Reviewer loop scores cut coherence explicitly |
| Corrupt/oversized uploads | `ffprobe` validation + size cap before compute spent |
| Job crash mid-pipeline | Stage-based state machine, idempotent retries |
| Gemini 2.5 deprecation (no earlier than Oct 16, 2026) | Built on 3.1 Flash-Lite from day one |

---

## 12. Environment / Secrets

```
GEMINI_API_KEY
GCP_PROJECT_ID
GCS_BUCKET_NAME
SUPABASE_URL
SUPABASE_SERVICE_KEY
CLOUD_TASKS_QUEUE
```
All stored in GCP Secret Manager, injected at runtime — never committed.
