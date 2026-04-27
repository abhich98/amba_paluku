/**
 * app.js — Amba Paluku quiz frontend
 *
 * Flow:
 *   1. Fetch data/manifest.json on load.
 *   2. Determine target lesson via ?date= or latest manifest entry.
 *   3. Map lesson item types into SurveyJS pages.
 *   4. Let SurveyJS handle page-level interaction.
 *   5. Compute score using type-aware evaluation and fuzzy transliteration checks.
 *
 * All state is client-side and session-scoped; no server required.
 */

'use strict';

// ── Constants ─────────────────────────────────────────────────────────────────

const MANIFEST_URL = 'data/manifest.json';
const UI_TEXT_URL = 'data/ui-text.json';
const TRANSLIT_SIMILARITY_THRESHOLD = 0.85;
const MCQ_AUDIO_TYPE = 'mcq_audio';
const MATCH_CARDS_TYPE = 'match_cards';

// ── App state ─────────────────────────────────────────────────────────────────

let manifest     = null;   // parsed manifest.json
let currentLesson = null;  // currently loaded lesson object
let activeAudio   = null;
let surveyModel   = null;
let surveyMeta    = {};
let uiText        = null;
let surveyExtensionsRegistered = false;
let matchSelections = {};

// ── DOM references ────────────────────────────────────────────────────────────

const views = {
  loading: document.getElementById('view-loading'),
  landing: document.getElementById('view-landing'),
  error:   document.getElementById('view-error'),
  quiz:    document.getElementById('view-quiz'),
  summary: document.getElementById('view-summary'),
  archive: document.getElementById('view-archive'),
};

const el = {
  progressWrap:    document.getElementById('progress-bar-wrap'),
  progressBarFill: document.getElementById('progress-bar-fill'),
  progressBar:     document.getElementById('progress-bar'),
  progressLabel:   document.getElementById('progress-label'),

  surveyRoot:      document.getElementById('survey-root'),
  appLogo:         document.getElementById('app-logo'),
  logoLine1:       document.getElementById('logo-line-1'),
  logoLine2:       document.getElementById('logo-line-2'),
  landingKicker:   document.getElementById('landing-kicker'),
  landingHeading:  document.getElementById('landing-heading'),
  landingSubheading: document.getElementById('landing-subheading'),
  btnStartLearning: document.getElementById('btn-start-learning'),
  loadingText:     document.getElementById('loading-text'),
  summaryHeading:  document.getElementById('summary-heading'),
  archiveHeading:  document.getElementById('archive-heading'),

  summaryScore:    document.getElementById('summary-score'),
  summaryDate:     document.getElementById('summary-date'),
  archiveList:     document.getElementById('archive-list'),
  errorMsg:        document.getElementById('error-msg'),

  btnLanding:      document.getElementById('btn-landing'),
  btnToday:        document.getElementById('btn-today'),
  btnArchive:      document.getElementById('btn-archive'),
  btnRetry:        document.getElementById('btn-retry'),
  btnRestart:      document.getElementById('btn-restart'),
  btnGoArchive:    document.getElementById('btn-go-archive'),
};

function getSurveyRoot() {
  return document.getElementById('survey-root');
}

function resetSurveyRoot() {
  const existingRoot = getSurveyRoot();
  if (!existingRoot) return null;

  const freshRoot = document.createElement('div');
  freshRoot.id = 'survey-root';
  freshRoot.className = existingRoot.className;
  existingRoot.replaceWith(freshRoot);
  return freshRoot;
}

// ── View management ───────────────────────────────────────────────────────────

function showView(name) {
  Object.values(views).forEach(v => v.classList.add('hidden'));
  views[name].classList.remove('hidden');
  el.progressWrap.classList.toggle('hidden', name !== 'quiz');
}

// ── URL / routing helpers ─────────────────────────────────────────────────────

function getDateParam() {
  return new URLSearchParams(window.location.search).get('date');
}

function pushDateParam(dateStr) {
  const url = new URL(window.location);
  url.searchParams.set('date', dateStr);
  url.hash = '';
  window.history.pushState({ date: dateStr }, '', url);
}

function pushArchiveHash() {
  const url = new URL(window.location);
  url.hash = 'archive';
  window.history.pushState({ archive: true }, '', url);
}

// ── Data fetching ─────────────────────────────────────────────────────────────

async function fetchJSON(url) {
  const resp = await fetch(url);
  if (!resp.ok) throw new Error(`HTTP ${resp.status} fetching ${url}`);
  return resp.json();
}

async function loadManifest() {
  return fetchJSON(MANIFEST_URL);
}

async function loadUiText() {
  return fetchJSON(UI_TEXT_URL);
}

function applyUiTextConfig(ui) {
  const title = ui?.appTitle || document.title;
  document.title = title;

  const appTitleMeta = document.querySelector('meta[name="app-title"]');
  if (appTitleMeta) appTitleMeta.content = title;
  if (el.appLogo) el.appLogo.title = title;

  if (el.logoLine1 && ui?.logo?.line1) el.logoLine1.textContent = ui.logo.line1;
  if (el.logoLine2 && ui?.logo?.line2) el.logoLine2.textContent = ui.logo.line2;

  if (el.btnLanding && ui?.nav?.home) el.btnLanding.textContent = ui.nav.home;
  if (el.btnToday && ui?.nav?.today) el.btnToday.textContent = ui.nav.today;
  if (el.btnArchive && ui?.nav?.archive) el.btnArchive.textContent = ui.nav.archive;

  if (el.landingKicker && ui?.landing?.kicker) el.landingKicker.textContent = ui.landing.kicker;
  if (el.landingHeading && ui?.landing?.heading) el.landingHeading.textContent = ui.landing.heading;
  if (el.landingSubheading && ui?.landing?.subheading) {
    el.landingSubheading.textContent = ui.landing.subheading;
  }
  if (el.btnStartLearning && ui?.landing?.cta) el.btnStartLearning.textContent = ui.landing.cta;

  if (el.loadingText && ui?.loadingText) el.loadingText.textContent = ui.loadingText;
  if (el.summaryHeading && ui?.summaryHeading) el.summaryHeading.textContent = ui.summaryHeading;
  if (el.archiveHeading && ui?.archiveHeading) el.archiveHeading.textContent = ui.archiveHeading;
}

function setActiveNav(active) {
  const navMap = {
    landing: el.btnLanding,
    today: el.btnToday,
    archive: el.btnArchive,
  };
  Object.entries(navMap).forEach(([name, node]) => {
    if (!node) return;
    node.classList.toggle('active', name === active);
  });
}

async function loadLesson(dateStr) {
  const entry = manifest.lessons.find(l => l.date === dateStr);
  if (!entry) throw new Error(`No lesson found for ${dateStr}.`);
  return fetchJSON(entry.path);
}

// ── Progress bar ──────────────────────────────────────────────────────────────

function updateProgress(current, total) {
  const pct = total > 0 ? Math.round((current / total) * 100) : 0;
  el.progressBarFill.style.width = `${pct}%`;
  el.progressBar.setAttribute('aria-valuenow', pct);
  const labelCurrent = total > 0 ? Math.min(current + 1, total) : 0;
  el.progressLabel.textContent = `${labelCurrent} / ${total}`;
}

// ── Audio playback ────────────────────────────────────────────────────────────

function playAudio(audioPath) {
  if (!audioPath) return;
  if (activeAudio) {
    activeAudio.pause();
    activeAudio = null;
  }
  const audio = new Audio(audioPath);
  activeAudio = audio;
  document.querySelectorAll('.inline-audio-btn.playing').forEach(btn => {
    btn.classList.remove('playing');
  });

  audio.play().catch(() => {
    // Autoplay blocked or missing file; keep UX non-blocking.
  });

  audio.addEventListener('ended', () => {
    document.querySelectorAll('.inline-audio-btn.playing').forEach(btn => {
      btn.classList.remove('playing');
    });
    if (activeAudio === audio) activeAudio = null;
  });
}

function stopAudio() {
  if (activeAudio) {
    activeAudio.pause();
    activeAudio = null;
  }
  document.querySelectorAll('.inline-audio-btn.playing').forEach(btn => {
    btn.classList.remove('playing');
  });
}

// ── SurveyJS helpers ─────────────────────────────────────────────────────────

function escapeHtml(s) {
  return String(s)
    .replaceAll('&', '&amp;')
    .replaceAll('<', '&lt;')
    .replaceAll('>', '&gt;')
    .replaceAll('"', '&quot;')
    .replaceAll("'", '&#39;');
}

function mkAudioBtn(audioPath, label = 'Play') {
  if (!audioPath) return '';
  return `<button type="button" class="inline-audio-btn" data-audio-path="${escapeHtml(audioPath)}" aria-label="${escapeHtml(label)}">🔊</button>`;
}

function buildMcqOptionsJson(options) {
  return JSON.stringify(options);
}

function buildMatchPromptsJson(prompts) {
  return JSON.stringify(prompts);
}

function buildMatchOptionsJson(options) {
  return JSON.stringify(options);
}

function parseMcqOptions(question) {
  try {
    const parsed = JSON.parse(question.optionsJson || '[]');
    return Array.isArray(parsed) ? parsed : [];
  } catch {
    return [];
  }
}

function parseMatchPrompts(question) {
  try {
    const parsed = JSON.parse(question.promptsJson || '[]');
    return Array.isArray(parsed) ? parsed : [];
  } catch {
    return [];
  }
}

function parseMatchOptions(question) {
  try {
    const parsed = JSON.parse(question.optionsJson || '[]');
    return Array.isArray(parsed) ? parsed : [];
  } catch {
    return [];
  }
}

function enhanceMcqOptionDom(question, element) {
  const options = parseMcqOptions(question);
  const radioInputs = element.querySelectorAll('input[type="radio"]');

  radioInputs.forEach((input) => {
    const option = options.find(opt => opt.id === input.value);
    if (!option) return;

    const item = input.closest('.sd-item, .sd-selectbase__item');
    const label = item?.querySelector('.sd-item__control-label');
    if (!item || !label) return;
    if (label.dataset.audioEnhanced === 'true') return;

    label.dataset.audioEnhanced = 'true';
    label.innerHTML = `<span class="mcq-option-layout">${mkAudioBtn(option.audio_path, `Play option ${option.transliteration}`)}<span class="choice-copy"><em class="choice-translit">${escapeHtml(option.transliteration)}</em><span class="choice-script">${escapeHtml(option.telugu)}</span></span></span>`;
  });
}

function enhanceMatchCardsDom(question, element) {
  const prompts = parseMatchPrompts(question);
  const englishOptions = parseMatchOptions(question);
  const boardElement = element.querySelector('.match-board');
  if (!boardElement) return;

  let selectedPromptIndex = -1;
  const pairsField = question.contentPanel.getQuestionByName('pairs');
  let pairs = matchSelections[question.name] ? { ...matchSelections[question.name] } : parseMatchAnswerValue(question.value);
  if (Object.keys(pairs).length === 0) {
    try {
      const stored = pairsField?.value ? JSON.parse(pairsField.value) : {};
      if (stored && typeof stored === 'object' && !Array.isArray(stored)) {
        pairs = { ...stored };
      }
    } catch {
      pairs = {};
    }
  }

  function updateQuestionValue() {
    const nextValue = JSON.stringify(pairs);
    question.value = nextValue;
    matchSelections[question.name] = { ...pairs };
    if (pairsField) {
      pairsField.value = nextValue;
    }
  }

  function renderBoard() {
    const usedOptions = new Set(Object.values(pairs));

    const promptCards = prompts.map((prompt, index) => {
      const assigned = pairs[prompt.id] || '';
      const selectedClass = selectedPromptIndex === index ? ' selected' : '';
      const matchedClass = assigned ? ' matched' : '';
      return `<div class="match-prompt-card${selectedClass}${matchedClass}" data-prompt-idx="${index}" role="button" tabindex="0">${mkAudioBtn(prompt.audio_path, 'Play prompt audio')}<span class="match-card-copy"><em class="choice-translit">${escapeHtml(prompt.reference_transliteration)}</em><span class="choice-script">${escapeHtml(prompt.reference_telugu)}</span><span class="match-assigned">${assigned ? `Matched: ${escapeHtml(assigned)}` : 'Tap then pick English option'}</span></span></div>`;
    }).join('');

    const optionCards = englishOptions.map((option, index) => {
      const selectedClass = usedOptions.has(option) ? ' used' : '';
      return `<button type="button" class="match-option-card${selectedClass}" data-option-idx="${index}">${escapeHtml(option)}</button>`;
    }).join('');

    boardElement.innerHTML = `<div class="match-column"><h4>Telugu Prompts</h4><div class="match-card-list">${promptCards}</div></div><div class="match-column"><h4>English Options</h4><div class="match-card-list">${optionCards}</div></div>`;

    boardElement.querySelectorAll('.match-prompt-card').forEach((node) => {
      node.addEventListener('click', () => {
        selectedPromptIndex = Number(node.getAttribute('data-prompt-idx'));
        renderBoard();
      });
      node.addEventListener('keydown', (event) => {
        if (event.key !== 'Enter' && event.key !== ' ') return;
        event.preventDefault();
        selectedPromptIndex = Number(node.getAttribute('data-prompt-idx'));
        renderBoard();
      });
    });

    boardElement.querySelectorAll('.match-option-card').forEach((node) => {
      node.addEventListener('click', () => {
        if (selectedPromptIndex < 0) return;
        const optionIndex = Number(node.getAttribute('data-option-idx'));
        const option = englishOptions[optionIndex];
        const prompt = prompts[selectedPromptIndex];
        if (!prompt || !option) return;

        for (const [promptId, assigned] of Object.entries(pairs)) {
          if (assigned === option && promptId !== prompt.id) {
            delete pairs[promptId];
          }
        }

        pairs[prompt.id] = option;
        updateQuestionValue();
        selectedPromptIndex = -1;
        renderBoard();
      });
    });
  }

  renderBoard();
}

function parseMatchAnswerValue(rawAnswer) {
  if (!rawAnswer) {
    return {};
  }

  if (typeof rawAnswer === 'string') {
    try {
      const parsed = JSON.parse(rawAnswer);
      if (parsed && typeof parsed === 'object' && !Array.isArray(parsed)) {
        if (typeof parsed.pairs === 'string') {
          try {
            const nestedPairs = JSON.parse(parsed.pairs);
            if (nestedPairs && typeof nestedPairs === 'object' && !Array.isArray(nestedPairs)) {
              return nestedPairs;
            }
          } catch {
            return {};
          }
        }
        return parsed;
      }
    } catch {
      return {};
    }
  }

  if (typeof rawAnswer !== 'object') {
    return {};
  }

  if (typeof rawAnswer.pairs === 'string') {
    try {
      const parsed = JSON.parse(rawAnswer.pairs);
      if (parsed && typeof parsed === 'object' && !Array.isArray(parsed)) {
        return parsed;
      }
    } catch {
      return {};
    }
  }

  const directPairs = Object.entries(rawAnswer).filter(([k, v]) => k !== 'pairs' && typeof v === 'string');
  if (directPairs.length > 0) {
    return Object.fromEntries(directPairs);
  }

  return {};
}

function registerSurveyExtensions() {
  if (surveyExtensionsRegistered || !Survey?.ComponentCollection || !Survey?.Serializer) {
    return;
  }

  Survey.ComponentCollection.Instance.add({
    name: MCQ_AUDIO_TYPE,
    title: 'MCQ Audio',
    elementsJSON: [
      {
        type: 'html',
        name: 'instruction',
        titleLocation: 'hidden',
      },
      {
        type: 'radiogroup',
        name: 'choice',
        titleLocation: 'top',
        choices: [],
      },
    ],
    onInit() {
      Survey.Serializer.addProperty(MCQ_AUDIO_TYPE, {
        name: 'instructionText:text',
        default: 'Select the appropriate translation.',
      });
      Survey.Serializer.addProperty(MCQ_AUDIO_TYPE, {
        name: 'promptText:text',
        default: '',
      });
      Survey.Serializer.addProperty(MCQ_AUDIO_TYPE, {
        name: 'optionsJson:text',
        default: '[]',
      });
      Survey.Serializer.addProperty(MCQ_AUDIO_TYPE, {
        name: 'titleLocation',
        default: 'hidden',
        visible: false,
      });
      Survey.Serializer.addProperty(MCQ_AUDIO_TYPE, {
        name: 'title',
        default: '',
        visible: false,
      });
      Survey.Serializer.addProperty(MCQ_AUDIO_TYPE, {
        name: 'description',
        visible: false,
      });
    },
    onCreated(question) {
      question.contentPanel.showQuestionNumbers = 'off';
    },
    onLoaded(question) {
      const instruction = question.contentPanel.getQuestionByName('instruction');
      const choice = question.contentPanel.getQuestionByName('choice');
      const options = parseMcqOptions(question);

      instruction.html = `<div class="question-helper question-helper-left">${escapeHtml(question.instructionText)} <span class="required-mark" aria-hidden="true">*</span></div>`;
      choice.title = question.promptText;
      choice.titleLocation = 'top';
      choice.choices = options.map(opt => ({
        value: opt.id,
        text: opt.telugu,
      }));
    },
    onPropertyChanged(question, propertyName) {
      if (propertyName !== 'instructionText' && propertyName !== 'promptText' && propertyName !== 'optionsJson') {
        return;
      }
      const instruction = question.contentPanel.getQuestionByName('instruction');
      const choice = question.contentPanel.getQuestionByName('choice');
      const options = parseMcqOptions(question);
      instruction.html = `<div class="question-helper question-helper-left">${escapeHtml(question.instructionText)} <span class="required-mark" aria-hidden="true">*</span></div>`;
      choice.title = question.promptText;
      choice.titleLocation = 'top';
      choice.choices = options.map(opt => ({
        value: opt.id,
        text: opt.telugu,
      }));
    },
    onAfterRender(question, element) {
      enhanceMcqOptionDom(question, element);
    },
  });

  Survey.ComponentCollection.Instance.add({
    name: MATCH_CARDS_TYPE,
    title: 'Match Cards',
    elementsJSON: [
      {
        type: 'html',
        name: 'instruction',
        titleLocation: 'hidden',
      },
      {
        type: 'html',
        name: 'board',
        titleLocation: 'hidden',
      },
      {
        type: 'comment',
        name: 'pairs',
        titleLocation: 'hidden',
        visible: false,
      },
    ],
    onInit() {
      Survey.Serializer.addProperty(MATCH_CARDS_TYPE, {
        name: 'instructionText:text',
        default: 'Match each Telugu prompt with the correct English option.',
      });
      Survey.Serializer.addProperty(MATCH_CARDS_TYPE, {
        name: 'promptsJson:text',
        default: '[]',
      });
      Survey.Serializer.addProperty(MATCH_CARDS_TYPE, {
        name: 'optionsJson:text',
        default: '[]',
      });
      Survey.Serializer.addProperty(MATCH_CARDS_TYPE, {
        name: 'titleLocation',
        default: 'hidden',
        visible: false,
      });
      Survey.Serializer.addProperty(MATCH_CARDS_TYPE, {
        name: 'title',
        default: '',
        visible: false,
      });
      Survey.Serializer.addProperty(MATCH_CARDS_TYPE, {
        name: 'description',
        visible: false,
      });
    },
    onCreated(question) {
      question.contentPanel.showQuestionNumbers = 'off';
    },
    onLoaded(question) {
      const instruction = question.contentPanel.getQuestionByName('instruction');
      const board = question.contentPanel.getQuestionByName('board');
      const pairsField = question.contentPanel.getQuestionByName('pairs');
      instruction.html = `<div class="question-helper question-helper-left">${escapeHtml(question.instructionText)} <span class="required-mark" aria-hidden="true">*</span></div>`;
      board.html = '<div class="match-board"></div>';
      if (pairsField) pairsField.visible = false;
    },
    onPropertyChanged(question, propertyName) {
      if (propertyName !== 'instructionText') return;
      const instruction = question.contentPanel.getQuestionByName('instruction');
      instruction.html = `<div class="question-helper question-helper-left">${escapeHtml(question.instructionText)} <span class="required-mark" aria-hidden="true">*</span></div>`;
    },
    onAfterRender(question, element) {
      enhanceMatchCardsDom(question, element);
    },
  });

  surveyExtensionsRegistered = true;
}

function mkFillReferenceBlock(item) {
  const referenceSentence = item.reference_sentence || item.reference_telugu;
  const questionLanguage = item.question_language || 'english';

  if (questionLanguage === 'telugu_transliteration') {
    return `<div class="fill-hint"><span class="fill-ref"><strong class="fill-ref-label">Reference (English):</strong><span class="fill-ref-content">${escapeHtml(referenceSentence)}</span></span></div>`;
  }

  return `<div class="fill-hint">${mkAudioBtn(item.audio_path, 'Play Telugu audio')}<span class="fill-ref"><strong class="fill-ref-label">Reference (Telugu):</strong><span class="fill-ref-content"><em>${escapeHtml(item.reference_transliteration)}</em><span>${escapeHtml(item.reference_telugu)}</span></span></span></div>`;
}

function mkFillPromptBlock(item) {
  const helperText = (item.question_language || 'english') === 'telugu_transliteration'
    ? 'Fill in the missing transliterated Telugu word.'
    : 'Fill in the missing English word.';

  return `<div class="fill-prompt-block"><p class="question-helper">${escapeHtml(helperText)} <span class="required-mark" aria-hidden="true">*</span></p><div class="fill-question-line">${escapeHtml(buildBlankedSentence(item))}</div></div>`;
}

function buildMatchPairLines(prompts, response) {
  return prompts.map((prompt) => {
    const chosen = response[prompt.id] || 'No answer';
    return `<li><span class="match-result-left">${escapeHtml(prompt.reference_transliteration)}</span><span class="match-result-arrow" aria-hidden="true">→</span><span class="match-result-right">${escapeHtml(chosen)}</span></li>`;
  }).join('');
}

function buildCorrectMatchPairLines(prompts) {
  return prompts.map(prompt => (`<li><span class="match-result-left">${escapeHtml(prompt.reference_transliteration)}</span><span class="match-result-arrow" aria-hidden="true">→</span><span class="match-result-right">${escapeHtml(prompt.correct_english)}</span></li>`)).join('');
}

function buildBlankedSentence(item) {
  const sourceSentence = item.question_sentence || item.sentence_english || '';
  const words = String(sourceSentence).split(/\s+/).filter(Boolean);
  const omitIndex = Number(item.omit_loc) - 1;
  if (omitIndex < 0 || omitIndex >= words.length) {
    return sourceSentence;
  }
  words[omitIndex] = '_____';
  return words.join(' ');
}

function normalizeTransliteration(s) {
  return String(s || '')
    .toLowerCase()
    .normalize('NFKD')
    .replace(/[\u0300-\u036f]/g, '')
    .replace(/[^a-z0-9\s]/g, ' ')
    .replace(/\s+/g, ' ')
    .trim();
}

function levenshteinDistance(a, b) {
  const m = a.length;
  const n = b.length;
  if (m === 0) return n;
  if (n === 0) return m;

  const dp = Array.from({ length: m + 1 }, () => new Array(n + 1).fill(0));
  for (let i = 0; i <= m; i++) dp[i][0] = i;
  for (let j = 0; j <= n; j++) dp[0][j] = j;

  for (let i = 1; i <= m; i++) {
    for (let j = 1; j <= n; j++) {
      const cost = a[i - 1] === b[j - 1] ? 0 : 1;
      dp[i][j] = Math.min(
        dp[i - 1][j] + 1,
        dp[i][j - 1] + 1,
        dp[i - 1][j - 1] + cost,
      );
    }
  }

  return dp[m][n];
}

function translitSimilarity(a, b) {
  const na = normalizeTransliteration(a);
  const nb = normalizeTransliteration(b);
  const denom = Math.max(na.length, nb.length, 1);
  const dist = levenshteinDistance(na, nb);
  return 1 - dist / denom;
}

function normalizeAcceptedAnswer(s) {
  return String(s || '')
    .toLowerCase()
    .trim()
    .replace(/^[^a-z0-9]+|[^a-z0-9]+$/gi, '');
}

function isAnswerAccepted(input, acceptedAnswers) {
  const normalizedInput = normalizeAcceptedAnswer(input);
  if (!normalizedInput) return false;
  return acceptedAnswers.some(ans => normalizeAcceptedAnswer(ans) === normalizedInput);
}

function isTransliterationAnswerAccepted(input, acceptedAnswers) {
  const normalizedInput = normalizeAcceptedAnswer(input);
  if (!normalizedInput) return false;
  return acceptedAnswers.some(ans => translitSimilarity(input, ans) >= TRANSLIT_SIMILARITY_THRESHOLD);
}

function getFillAnswerMode(item) {
  return item.answer_mode || 'english';
}

function validateFillAnswer(input, item) {
  if (getFillAnswerMode(item) === 'transliteration') {
    return isTransliterationAnswerAccepted(input, item.accepted_answers);
  }
  return isAnswerAccepted(input, item.accepted_answers);
}

function getFillPromptTitle(item) {
  if ((item.question_language || 'english') === 'telugu_transliteration') {
    return `Type the missing transliterated Telugu word: ${buildBlankedSentence(item)}`;
  }
  return `Type the missing English word: ${buildBlankedSentence(item)}`;
}

function buildSurveyDefinition(lesson) {
  surveyMeta = {};
  const pages = lesson.items.map((item, idx) => {
    const qName = item.id;
    surveyMeta[qName] = item;

    if (item.type === 'mcq_bimodal') {
      return {
        name: `page_${idx + 1}`,
        elements: [
          {
            type: MCQ_AUDIO_TYPE,
            name: qName,
            titleLocation: 'hidden',
            instructionText: 'Select the appropriate Telugu translation.',
            promptText: item.sentence_english,
            isRequired: true,
            optionsJson: buildMcqOptionsJson(item.options),
          },
        ],
      };
    }

    if (item.type === 'fill_blank_audio') {
      return {
        name: `page_${idx + 1}`,
        elements: [
          {
            type: 'html',
            name: `${qName}_prompt`,
            html: mkFillPromptBlock(item),
          },
          {
            type: 'text',
            name: qName,
            isRequired: true,
            title: 'Your answer',
            titleLocation: 'hidden',
            placeholder: 'Type the missing word',
          },
          {
            type: 'html',
            name: `${qName}_reference`,
            html: mkFillReferenceBlock(item),
          },
        ],
      };
    }

    if (item.type === 'match_audio_text') {
      return {
        name: `page_${idx + 1}`,
        elements: [
          {
            type: MATCH_CARDS_TYPE,
            name: qName,
            titleLocation: 'hidden',
            isRequired: true,
            instructionText: 'Match each Telugu prompt with the correct English option.',
            promptsJson: buildMatchPromptsJson(item.prompts),
            optionsJson: buildMatchOptionsJson(item.english_options),
          },
        ],
      };
    }

    throw new Error(`Unsupported question type: ${item.type}`);
  });

  return {
    allowHtml: false,
    showQuestionNumbers: 'off',
    showProgressBar: 'off',
    showPrevButton: false,
    goNextPageAutomatic: false,
    pageNextText: 'Next ->',
    completeText: 'Finish Session ->',
    pages,
  };
}

function getMcqAnswerValue(answers, itemId) {
  const rawAnswer = answers[itemId];
  if (typeof rawAnswer === 'string') return rawAnswer;
  return rawAnswer?.choice || '';
}

function evaluateItem(item, answers) {
  if (item.type === 'mcq_bimodal') {
    return getMcqAnswerValue(answers, item.id) === item.correct_option_id;
  }

  if (item.type === 'fill_blank_audio') {
    const userText = answers[item.id] || '';
    return validateFillAnswer(userText, item);
  }

  if (item.type === 'match_audio_text') {
    const response = parseMatchAnswerValue(answers[item.id]);
    const selected = new Set();
    for (const prompt of item.prompts) {
      const chosen = response[prompt.id];
      if (!chosen || selected.has(chosen) || chosen !== prompt.correct_english) {
        return false;
      }
      selected.add(chosen);
    }
    return true;
  }

  return false;
}

function formatMcqOption(option) {
  if (!option) return 'No answer';
  return `${option.transliteration} (${option.telugu})`;
}

function buildResultReviewHtml(lesson, answers) {
  const rows = lesson.items.map((item, idx) => {
    const isCorrect = evaluateItem(item, answers);
    const status = isCorrect ? 'Correct' : 'Wrong';
    const statusClass = isCorrect ? 'result-pill correct' : 'result-pill wrong';

    if (item.type === 'mcq_bimodal') {
      const selected = item.options.find(opt => opt.id === getMcqAnswerValue(answers, item.id));
      const correct = item.options.find(opt => opt.id === item.correct_option_id);
      return `<li class="result-row"><div class="result-head"><span class="${statusClass}">${status}</span><span class="result-q">Q${idx + 1}: ${escapeHtml(item.sentence_english)}</span></div><div class="result-detail"><strong>Your answer:</strong> ${escapeHtml(formatMcqOption(selected))}</div><div class="result-detail"><strong>Correct answer:</strong> ${escapeHtml(formatMcqOption(correct))}</div></li>`;
    }

    if (item.type === 'fill_blank_audio') {
      const userAnswer = answers[item.id] || 'No answer';
      return `<li class="result-row"><div class="result-head"><span class="${statusClass}">${status}</span><span class="result-q">Q${idx + 1}: ${escapeHtml(buildBlankedSentence(item))}</span></div><div class="result-detail"><strong>Your answer:</strong> ${escapeHtml(userAnswer)}</div><div class="result-detail"><strong>Correct answer:</strong> ${escapeHtml(item.display_correct_answer)}</div></li>`;
    }

    if (item.type === 'match_audio_text') {
      const response = parseMatchAnswerValue(answers[item.id]);
      return `<li class="result-row"><div class="result-head"><span class="${statusClass}">${status}</span><span class="result-q">Q${idx + 1}: Match audio/transliteration to English</span></div><div class="result-detail"><strong>Your answer:</strong><ul class="match-result-list">${buildMatchPairLines(item.prompts, response)}</ul></div><div class="result-detail"><strong>Correct answer:</strong><ul class="match-result-list">${buildCorrectMatchPairLines(item.prompts)}</ul></div></li>`;
    }

    return '';
  });

  return `<div class="results-review"><h3>Your Responses</h3><ul class="result-list">${rows.join('')}</ul></div>`;
}

function mountSurvey(lesson) {
  if (surveyModel) {
    surveyModel.dispose();
    surveyModel = null;
  }

  const surveyRoot = getSurveyRoot();
  if (!surveyRoot) {
    throw new Error('Survey root not found.');
  }

  matchSelections = {};
  const surveyJSON = buildSurveyDefinition(lesson);
  surveyModel = new Survey.Model(surveyJSON);

  surveyModel.onCurrentPageChanged.add((sender) => {
    updateProgress(sender.currentPageNo, lesson.items.length);
  });

  surveyModel.onValidateQuestion.add((_, options) => {
    const item = surveyMeta[options.name];
    if (!item) return;

    if (item.type === 'match_audio_text') {
      const value = parseMatchAnswerValue(options.value || {});
      const selected = Object.values(value).filter(Boolean);
      if (selected.length !== item.prompts.length) {
        options.error = 'Match all Telugu prompts before continuing.';
        return;
      }
      if (selected.length !== new Set(selected).size) {
        options.error = 'Each English option can be used only once.';
      }
    }
  });

  surveyModel.onComplete.add((sender) => {
    const answers = { ...(sender.data || {}) };

    for (const item of lesson.items) {
      if (item.type !== 'match_audio_text') continue;
      const parsedFromData = parseMatchAnswerValue(
        answers[item.id]
        ?? answers[`${item.id}.pairs`]
        ?? answers[`${item.id}_pairs`]
        ?? answers.pairs,
      );
      if (Object.keys(parsedFromData).length > 0) {
        answers[item.id] = JSON.stringify(parsedFromData);
        continue;
      }

      const question = sender.getQuestionByName(item.id);
      const parsedFromQuestion = parseMatchAnswerValue(question?.value);

      if (Object.keys(parsedFromQuestion).length > 0) {
        answers[item.id] = JSON.stringify(parsedFromQuestion);
        continue;
      }

      const pairsField = question?.contentPanel?.getQuestionByName?.('pairs');
      const parsedFromField = parseMatchAnswerValue({ pairs: pairsField?.value || '' });
      if (Object.keys(parsedFromField).length > 0) {
        answers[item.id] = JSON.stringify(parsedFromField);
        continue;
      }

      const parsedFromCache = parseMatchAnswerValue(matchSelections[item.id]);
      if (Object.keys(parsedFromCache).length > 0) {
        answers[item.id] = JSON.stringify(parsedFromCache);
      }
    }

    const correctCount = lesson.items.filter(item => evaluateItem(item, answers)).length;
    const reviewHtml = buildResultReviewHtml(lesson, answers);
    showSummary(correctCount, lesson.items.length, reviewHtml);
  });

  surveyRoot.innerHTML = '';
  surveyModel.render(surveyRoot);
  updateProgress(0, lesson.items.length);
}

// ── Summary ───────────────────────────────────────────────────────────────────

function showSummary(correctCount, total, reviewHtml) {
  stopAudio();

  // Fill the progress bar to 100 %
  el.progressBarFill.style.width = '100%';
  el.progressBar.setAttribute('aria-valuenow', 100);
  el.progressLabel.textContent = `${total} / ${total}`;

  el.summaryScore.textContent = `${correctCount} / ${total} correct`;
  el.summaryDate.innerHTML =
    `Lesson: ${escapeHtml(currentLesson.date)}  ·  Level: ${escapeHtml(currentLesson.difficulty)}${reviewHtml}`;

  showView('summary');
}

// ── Start a quiz session ──────────────────────────────────────────────────────

async function startQuiz(dateStr) {
  showView('loading');
  setActiveNav('today');

  try {
    currentLesson = await loadLesson(dateStr);
    const surveyRoot = resetSurveyRoot() || getSurveyRoot();
    if (!surveyRoot) throw new Error('Survey root not found.');
    surveyRoot.innerHTML = '';
    showView('quiz');
    await new Promise(resolve => requestAnimationFrame(() => requestAnimationFrame(resolve)));
    mountSurvey(currentLesson);
  } catch (err) {
    el.errorMsg.textContent = err.message;
    showView('error');
  }
}

// ── Archive ───────────────────────────────────────────────────────────────────

function renderArchive() {
  setActiveNav('archive');
  stopAudio();

  el.archiveList.innerHTML = '';

  if (!manifest || manifest.lessons.length === 0) {
    const li = document.createElement('li');
    li.className   = 'archive-empty';
    li.textContent = 'No lessons yet. Run the generator to create the first lesson.';
    el.archiveList.appendChild(li);
    showView('archive');
    return;
  }

  manifest.lessons.forEach(entry => {
    const li  = document.createElement('li');
    const btn = document.createElement('button');
    btn.className = 'archive-link';
    btn.innerHTML = `
      <span class="archive-date">${entry.date}</span>
      <span class="archive-meta">${entry.difficulty} · ${entry.item_count} items</span>
    `;
    btn.addEventListener('click', () => {
      pushDateParam(entry.date);
      startQuiz(entry.date);
    });
    li.appendChild(btn);
    el.archiveList.appendChild(li);
  });

  showView('archive');
}

function renderLanding() {
  stopAudio();
  setActiveNav('landing');
  showView('landing');
}

// ── Navigation event handlers ─────────────────────────────────────────────────

el.btnLanding.addEventListener('click', () => {
  const url = new URL(window.location);
  url.searchParams.delete('date');
  url.hash = '';
  window.history.pushState({ landing: true }, '', url);
  renderLanding();
});

el.btnToday.addEventListener('click', () => {
  const dateStr = new Date().toISOString().slice(0, 10);
  pushDateParam(dateStr);
  startQuiz(dateStr);
});

el.btnStartLearning.addEventListener('click', () => {
  const dateStr = new Date().toISOString().slice(0, 10);
  pushDateParam(dateStr);
  startQuiz(dateStr);
});

el.btnArchive.addEventListener('click', () => {
  pushArchiveHash();
  renderArchive();
});

el.btnRestart.addEventListener('click', () => {
  if (currentLesson) startQuiz(currentLesson.date);
});

el.btnGoArchive.addEventListener('click', () => {
  pushArchiveHash();
  renderArchive();
});

el.btnRetry.addEventListener('click', () => {
  const dateStr = getDateParam() || manifest?.lessons[0]?.date;
  if (dateStr) startQuiz(dateStr);
  else location.reload();
});

window.addEventListener('popstate', () => {
  if (window.location.hash === '#archive') {
    renderArchive();
  } else if (!getDateParam()) {
    renderLanding();
  } else {
    const dateStr = getDateParam() || manifest?.lessons[0]?.date;
    if (dateStr) startQuiz(dateStr);
  }
});

document.addEventListener('click', (event) => {
  const btn = event.target.closest('.inline-audio-btn');
  if (!btn) return;
  event.preventDefault();
  event.stopPropagation();
  const audioPath = btn.getAttribute('data-audio-path');
  if (!audioPath) return;
  document.querySelectorAll('.inline-audio-btn.playing').forEach(node => {
    node.classList.remove('playing');
  });
  btn.classList.add('playing');
  playAudio(audioPath);
});

// ── Bootstrap ─────────────────────────────────────────────────────────────────

(async function init() {
  showView('loading');
  try {
    registerSurveyExtensions();
    try {
      uiText = await loadUiText();
      applyUiTextConfig(uiText);
    } catch {
      // Continue with inline defaults when UI text file is missing.
    }

    manifest = await loadManifest();

    if (manifest.lessons.length === 0) {
      el.errorMsg.textContent =
        'No lessons available yet. Run the Python generator to create today\'s lesson.';
      showView('error');
      return;
    }

    if (window.location.hash === '#archive') {
      renderArchive();
      return;
    }

    if (!getDateParam()) {
      renderLanding();
      return;
    }

    const dateStr = getDateParam() || manifest.lessons[0].date;
    pushDateParam(dateStr);
    await startQuiz(dateStr);
  } catch (err) {
    el.errorMsg.textContent = err.message;
    showView('error');
  }
})();
