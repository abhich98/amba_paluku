# Amba Paluku / అంబ పలుకు

[**Amba Paluku**](https://abhich98.github.io/amba_paluku/) is a daily Telugu learning web app with audio-supported questions and an archive of past lessons. It consists of:

- a Python pipeline that generates and finalizes lesson JSON + audio assets
- a browser quiz app (SurveyJS-based) for daily practice and archive review
- schema validation to keep lesson/manifest data consistent

[**అంబ పలుకు**](https://abhich98.github.io/amba_paluku/), తెలుగు నేర్చుకుంటున్న వారు రోజూ అభ్యాసం చెయ్యటానికి ఉపయోగపడే అంతర్జాల ఆప్.

> _Amba Paluku, Jagadamba Paluku_ is just a popular Telugu phrase used by Budabukkala storytellers and fortune tellers, meaning they are speaking the words of the goddess Jagadamba. The name is randomly chosen since it is playful.

## What This Repo Does

The workflow is intentionally split into two stages:

1. Draft generation (text only)
- Script: `scripts/generate_daily_lesson.py`
- Produces `data/lessons/{date}.json` with status `draft`
- No audio is generated in this stage

2. Finalization (audio + publishing)
- Script: `scripts/finalize_lesson.py`
- Fills transliteration/audio fields
- Generates/rehydrates audio under `resources/audio/`
- Updates `data/manifest.json`
- Appends reusable sentence/word pairs into `resources/{CEFR}.md`
- Marks lesson status as `active`

## Current Question Types

- `mcq_bimodal`: multiple-choice translation
- `fill_blank_audio`: fill-in-the-blank with prompt/reference support
- `match_audio_text`: match prompt cards to options (prompt mode currently audio)

Language direction is bilingual and can vary per item depending on generation logic.

## Tech Stack

- Python 3.11+
- `uv` for env/dependency management
- SurveyJS (`survey-core`, `survey-js-ui`) on the frontend
- OpenRouter for text generation
- Sarvam AI for text-to-speech

## Quick Start

For a step-by-step setup and runbook, see [QUICK_START.md](QUICK_START.md).

## Repository Structure

- `scripts/generate_daily_lesson.py`: stage 1 draft generation
- `scripts/finalize_lesson.py`: stage 2 finalization and publishing
- `scripts/lesson_builder.py`: question assembly from generated pairs
- `scripts/providers/text_generator.py`: LLM adapter (OpenRouter)
- `scripts/providers/speech_generator.py`: TTS adapter (Sarvam)
- `scripts/providers/resource_loader.py`: load reusable pairs
- `scripts/providers/resource_writer.py`: append reusable pairs
- `scripts/schema/lesson_schema.py`: lesson/manifest validation
- `scripts/schema/language_properties.yml`: per-language transliteration/audio rules
- `config.yml`: default generation/finalization config
- `data/lessons/`: lesson JSON files
- `data/manifest.json`: lesson index consumed by frontend
- `data/ui-text.json`: configurable frontend text content
- `resources/`: CEFR resource files used for reuse (`A1.md`, `A2.md`, `B1.md`, ...)
- `resources/audio/`: generated audio assets
- `assets/app.js`: frontend entrypoint (ES module)
- `assets/modules/`: modular frontend runtime (scoring, views, survey, routing, etc.)
- `assets/styles.css`: frontend styles
- `index.html`: app shell and SurveyJS bootstrapping
- `.github/workflows/daily-content.yml`: scheduled/manual automation for generation

## GitHub Actions

> NOTE: NOT SET UP YET.

The workflow `.github/workflows/daily-content.yml` currently exists and supports:

- scheduled runs (daily)
- manual dispatch with optional date/difficulty/count inputs

It commits generated changes under `data/` when differences are detected.

## Development Notes

- Validate and review `data/lessons/{date}.json` before running finalization.
- Frontend reads only active lessons from `data/manifest.json`.
- Keep docs and CLI flags aligned with script arg names (`--num-questions`, not legacy aliases).

## License

MIT. See `LICENSE`.

## TODO
- [ ] Fill in the blank questions are set to `check mode: "exact"` even when the language of the question is Telugu and the answer is transliterated. Change it to `"fuzzy"` when comparing transliterated answers.
- [ ] The finalization script is addding the senstence pairs from "fill in the blank" questions in a different order to the resource `...md`, file compared to "mcq" questions. This is a problem.
- [ ] In the review section, match the following prompt text is only visible in Telugu text (not transliterated). 
- [ ] Maybe add audio to the sentences in the review section.