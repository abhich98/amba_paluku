## Configuration

Primary config file: `config.yml`

Important keys include:

- `date`, `difficulty`, `num_questions`
- `reference_lang`, `target_lang`
- `resource_dir`, `resource_reuse_pct`, `topics`
- `question_type_weights`
- `text_provider`, `LLM_model`
- `speech_provider`, `speech_opts`

Environment variables are documented in `.env.example`.

## Quick Start

### 1. Prerequisites

- Python 3.11+
- Node.js + npm (for local web server)
- `uv`

### 2. Install dependencies

```bash
uv sync
```

### 3. Configure environment

Copy `.env.example` to `.env` and set keys:

- `OPENROUTER_API_KEY`
- `SARVAM_API_KEY`

Optional model/provider overrides are also in `.env.example`.

### 4. Generate draft lesson (text-only)

```bash
uv run scripts/generate_daily_lesson.py --date 2026-05-02 --difficulty A1 --num-questions 12
```

Useful variants:

```bash
uv run scripts/generate_daily_lesson.py --config config.yml
uv run scripts/generate_daily_lesson.py --date 2026-05-02 --difficulty A2 --num-questions 10
uv run scripts/generate_daily_lesson.py --date 2026-05-02 --dry-run
```

This writes a draft file at `data/lessons/{date}.json`.

### 5. Review/edit the draft

Open `data/lessons/{date}.json` and make any content corrections before finalizing.

### 6. Finalize lesson (audio + manifest + resources)

```bash
uv run scripts/finalize_lesson.py --date 2026-05-02
```

Useful variants:

```bash
uv run scripts/finalize_lesson.py --date 2026-05-02 --dry-run
uv run scripts/finalize_lesson.py --date 2026-05-02 --config config.yml
```

Finalization updates:

- `data/lessons/{date}.json` (status/audio/transliteration)
- `data/manifest.json`
- `resources/audio/*.mp3`
- `resources/{CEFR}.md` pair libraries

### 7. Run the web app locally

```bash
npx live-server --port=5500 --open=index.html
```

Alternative:

```bash
python3 -m http.server 8765
```

Then open `http://127.0.0.1:8765/index.html`.
