## Quick Start

### 1. Prerequisites

- Python 3.11+
- Node.js + npm (for local static server)
- `uv` installed

### 2. Install dependencies

```bash
uv sync
```

### 3. Configure environment

Copy `.env.example` to `.env` and fill in required keys:

- `OPENROUTER_API_KEY`
- `SARVAM_API_KEY`

Optional provider/model settings are also in `.env.example`.

### 4. Generate a lesson

```bash
uv run scripts/generate_daily_lesson.py --count 12
```

Useful variants:

```bash
uv run scripts/generate_daily_lesson.py --date 2026-04-25 --difficulty A2 --count 10
uv run scripts/generate_daily_lesson.py --dry-run
```

### 5. Run the web app locally (development mode)

```bash
npx live-server --port=5500 --open=index.html
```
