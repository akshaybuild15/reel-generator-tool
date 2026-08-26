# AI Reels Generator

Source of truth for implementation decisions: `docs/reels-generator-build-spec.md` (the spec,
referenced as §N) and `docs/reels-generator-build-plan.md` (execution order, referenced as
Phase N). Anything not covered by those two docs should be raised, not assumed.

## Git workflow

- This repo is not yet initialized with git. Run `git init` before the first commit.
- One branch per plan phase (e.g. `phase-1-db-auth`, `phase-2-upload-flow`), branched off
  `main`. Merge back to `main` only once that phase's "Done when" condition in the build plan
  is met.
- Commit messages: short imperative subject line, body explains *why* when it isn't obvious
  from the diff. Reference the phase/section, e.g. `Add ffprobe validation stage (§9, Phase 2)`.
- Never commit `.env` (only `.env.example`), service account keys, or any file under `secrets/`.
- No force-push to `main`. No `--no-verify`.

## Environment variables (spec §12)

Six secrets, all listed with empty values in `.env.example`. All of them live in **GCP Secret
Manager** in every deployed environment (Cloud Run services and jobs) — they are injected at
runtime by the deploy config, never baked into images and never committed to the repo.

| Variable | Origin |
|---|---|
| `GEMINI_API_KEY` | GCP Secret Manager |
| `GCP_PROJECT_ID` | GCP Secret Manager |
| `GCS_BUCKET_NAME` | GCP Secret Manager |
| `SUPABASE_URL` | GCP Secret Manager |
| `SUPABASE_SERVICE_KEY` | GCP Secret Manager |
| `CLOUD_TASKS_QUEUE` | GCP Secret Manager |

For local development, pull the current values from Secret Manager into a local `.env`
(`gcloud secrets versions access latest --secret=<name>`) rather than requesting new ones —
`.env` is gitignored and must never be committed.

## Local GCP auth

Local machines authenticate to GCP via **Application Default Credentials**:

```
gcloud auth application-default login
```

Do **not** create or download a service account key file for local development. ADC is
sufficient for both the `backend` and `worker` services to reach Cloud Storage, Cloud Tasks,
and Secret Manager locally, and it avoids a long-lived key sitting on disk. Downloaded keys are
only for non-interactive environments where ADC isn't an option (and even then, prefer
Workload Identity in deployed environments over a key file).
