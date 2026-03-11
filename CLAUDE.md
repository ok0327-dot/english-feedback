# CLAUDE.md

## Project Overview

Automated phone English lesson feedback system (전화영어 자동 피드백 시스템). A single-script Python pipeline that runs daily via GitHub Actions to process recorded English lessons and deliver personalized feedback.

## Architecture

The entire pipeline lives in `process_lesson.py` (~1140 lines) and executes 8 sequential steps:

1. **Download** audio recording from Google Drive (`download_latest_recording`)
2. **Transcribe** audio to text via Groq Whisper API (`transcribe_audio`)
3. **Clean/correct** transcript via Gemini LLM (`clean_transcript`)
4. **Generate feedback** via Gemini LLM (`generate_feedback`)
5. **Build review webpage** as static HTML (`generate_review_page`, `deploy_review_page`)
6. **Send email** with feedback + review link via Gmail SMTP (`send_email`)
7. **Move** processed audio to "done" folder in Google Drive (`move_to_done_folder`)
8. **Record** processed file ID to `docs/processed.txt` to prevent duplicates (`save_processed_id`, `commit_processed_record`)

Entry point: `main()` at line 1070, called via `if __name__ == "__main__"`.

## Repository Structure

```
process_lesson.py     # Main pipeline script (all logic in one file)
requirements.txt      # Python dependencies (google-api, requests)
docs/                 # GitHub Pages output directory
  index.html          # Review page listing (auto-generated)
  YYYY-MM-DD.html     # Individual lesson review pages (auto-generated)
  processed.txt       # List of processed Google Drive file IDs
.github/workflows/
  english-feedback.yml   # Main workflow: runs Mon-Fri at KST 09:10 and 10:00
  delete-review.yml      # Manual workflow: delete a review page by date
gitignore             # Note: named "gitignore" not ".gitignore"
```

## Development Workflow

### Running Locally

```bash
pip install -r requirements.txt
# Set required environment variables (see below)
python process_lesson.py
```

### Required Environment Variables (stored in GitHub Secrets)

| Variable | Purpose |
|---|---|
| `GOOGLE_CREDENTIALS` | Base64-encoded Google service account JSON |
| `GROQ_API_KEY` | Groq API key for Whisper transcription |
| `GEMINI_API_KEY` | Google Gemini API key for LLM tasks |
| `GMAIL_ADDRESS` | Sender Gmail address |
| `GMAIL_APP_PASSWORD` | Gmail app password (16-char code) |
| `RECIPIENT_EMAIL` | Feedback recipient email |
| `DRIVE_FOLDER_ID` | Google Drive source folder ID |
| `DRIVE_DONE_FOLDER_ID` | Google Drive "done" folder ID |
| `GITHUB_PAGES_URL` | Base URL for GitHub Pages site |

### CI/CD

- **Main workflow** (`.github/workflows/english-feedback.yml`): Scheduled Mon-Fri at UTC 00:10 and 01:00 (KST 09:10 and 10:00). Also supports `workflow_dispatch`. Uses concurrency groups to prevent duplicate runs.
- **Delete workflow** (`.github/workflows/delete-review.yml`): Manual trigger to remove a review page by date and regenerate `index.html`.

Both workflows commit and push to `master` using the `github-actions` bot.

## Key Conventions

- **Language**: Comments and documentation are in Korean. Code identifiers (function/variable names) are in English.
- **Single-file architecture**: All logic is in `process_lesson.py`. No modules or packages.
- **LLM fallback**: `llm_request()` tries Gemini first, falls back to Groq LLM if Gemini key is missing.
- **Idempotency**: Processed file IDs are tracked in `docs/processed.txt` to prevent reprocessing.
- **Graceful no-op**: If no new recordings exist, the pipeline exits cleanly without error.
- **HTML generation**: Review pages and index are generated as raw HTML strings in Python (no templating engine).
- **Git operations**: The script runs `git` commands via `subprocess` to commit and push generated pages.

## Files to Never Commit

- `.env` or any file containing API keys/credentials
- `*.json` (credential files)
- `*.m4a`, `*.mp3`, `*.wav` (audio files)
- `__pycache__/`, `*.pyc`

## Testing

There are no automated tests. Changes should be validated by:
1. Reading the code carefully
2. Testing with `workflow_dispatch` trigger on a branch if possible
3. Checking GitHub Actions logs after deployment
