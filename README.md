# Amba Paluku/అంబ పలుకు

**Amba Paluku** is a daily Telugu learning web app with audio-supported questions and an archive of past lessons. 

**అంబ పలుకు**, తెలుగు నేర్చుకుంటున్న వారు రోజూ అభ్యాసం చెయ్యటానికి ఉపయోగపడే అంతర్జాల ఆప్.


> _Amba Paluku, Jagadamba Paluku_ is just a popular Telugu phrase used by Budabukkala storytellers and fortune tellers, meaning they are speaking the words of the goddess Jagadamba. The name is randomly chosen since it is playful.

The repository includes:
- a Python content-generation pipeline for daily lessons and audio assets
- a browser-based quiz app built using SurveyJS elements
- schema validation to keep generated lesson data consistent and reliable

## Goals
- Create a sustainable daily content generation pipeline for Telugu learners
- Provide daily practice with a variety of question types and audio support
- Accumulate a growing archive of lessons and resources (sentences, words, audio) following the CEFR language levels (starting with A1)

## Features

- Daily lesson generation with configurable date, difficulty, and question count
- Current question types:
	- Multiple choice (English to Telugu translation)
	- Fill in the blank (English and transliteration sentences)
	- Match the following (audio words to English meanings)
- Audio per question/option for listening practice
- Session summary with per-question review
- Archive view for previous lessons

## Tech Stack

- Python 3.11+
- `uv` for Python environment and dependency management
- SurveyJS (`survey-core`, `survey-js-ui`) for quiz rendering
- OpenRouter (text generation)
- Sarvam AI (speech generation)

## Repository Layout

- `scripts/generate_daily_lesson.py`: main lesson generation pipeline
- `scripts/schema/`: lesson and manifest validation
- `scripts/providers/`: provider adapters for text and speech
- `data/lessons/`: generated lesson JSON files
- `data/audio/`: generated audio assets
- `data/manifest.json`: lesson index consumed by the frontend
- `assets/app.js`: frontend quiz runtime
- `assets/styles.css`: frontend styling
- `index.html`: app entry page

> Read the [QUICK_START.md](QUICK_START.md) for detailed setup and usage instructions.

## Contributing

Contributions are welcome. This project is open source under the MIT License. See the `LICENSE` file for details.

### Suggested workflow

1. Fork the repository
2. Create a feature branch
3. Make focused changes
4. Run validation/checks locally
5. Open a pull request with a clear summary

### Before opening a PR

- Ensure generated data still validates
- Verify quiz flow and summary behavior in browser
- Keep changes small and scoped when possible

## TODOs:

- [ ] Update the README.md to the current state of the project.
- [ ] Inspect the generated lesson schema and look into how each question is defined.
- [ ] Inspect how the lessons are generated on consecutive days and look into how the sentences vary across days.
- [ ] Almost ready, make final inspections and frontend adjustments.