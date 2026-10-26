# Forma Shorts

Automated YouTube Shorts for Forma Designs: each video takes a pipeline project's empty lot,
flips it to the finished render, runs the process, and ends on the text-LAND CTA.

## Flow

1. **Make Short** (GitHub Actions, twice daily): picks the newest rendered pipeline project
   without a Short, pulls aerial / plan / model / render / package from the Concept `pipeline`
   bucket, has Claude write the script, voices it (Kokoro), renders `template/flip.html`
   frame-by-frame in Chromium, uploads to the CRM `shorts` bucket and queues a
   `social_posts` row as `pending_review`. Skips if 4+ are already waiting.
2. **Review**: a push lands in the ntfy app (topic in `engine/notify.py`) with
   **Watch / Approve / Kill**. Approve assigns the next free slot from
   `social_config.youtube_slots` (ET).
3. **Publish Shorts** (hourly): uploads approved posts whose slot has passed and pings you the link.

## Secrets (Settings → Secrets and variables → Actions)

`ANTHROPIC_API_KEY`, `CONCEPT_SUPABASE_KEY`, `CRM_SUPABASE_KEY`,
`YT_CLIENT_ID`, `YT_CLIENT_SECRET`, `YT_REFRESH_TOKEN`. Optional: `NTFY_TOPIC`.

## Handy

- Run one now: Actions → Make Short → Run workflow (optionally force a `project_id`).
- Change posting times: `update social_config set value='["12:31","18:47"]' where key='youtube_slots';`
- Local render of a job folder: `python engine/render.py JOB_DIR out.mp4 [--only 1.5,3.0]`
