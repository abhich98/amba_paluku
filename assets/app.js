/**
 * app.js — Amba Paluku quiz frontend
 *
 * Flow:
 *   1. Fetch data/manifest.json on load.
 *   2. Determine the target lesson: ?date= param → latest in manifest.
 *   3. Fetch that lesson's JSON and drive a one-question-at-a-time quiz.
 *   4. Show a summary with score when all items are complete.
 *   5. Archive view lists all lessons from the manifest (most-recent first).
 *
 * All state is client-side and session-scoped; no server required.
 */

'use strict';

// ── Constants ─────────────────────────────────────────────────────────────────

const MANIFEST_URL = 'data/manifest.json';

// ── App state ─────────────────────────────────────────────────────────────────

let manifest     = null;   // parsed manifest.json
let currentLesson = null;  // currently loaded lesson object
let itemIndex    = 0;      // current question index (0-based)
let score        = 0;      // correct answers in this session
let answered     = false;  // whether the current question has been answered
let activeAudio  = null;   // currently playing Audio instance

// ── DOM references ────────────────────────────────────────────────────────────

const views = {
  loading: document.getElementById('view-loading'),
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

  englishSentence: document.getElementById('english-sentence'),
  btnAudio:        document.getElementById('btn-audio'),
  mcqOptions:      document.getElementById('mcq-options'),
  btnNext:         document.getElementById('btn-next'),

  summaryScore:    document.getElementById('summary-score'),
  summaryDate:     document.getElementById('summary-date'),
  archiveList:     document.getElementById('archive-list'),
  errorMsg:        document.getElementById('error-msg'),

  btnHome:         document.getElementById('btn-home'),
  btnArchive:      document.getElementById('btn-archive'),
  btnRetry:        document.getElementById('btn-retry'),
  btnRestart:      document.getElementById('btn-restart'),
  btnGoArchive:    document.getElementById('btn-go-archive'),
};

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
  el.progressLabel.textContent = `${current + 1} / ${total}`;
}

// ── Audio playback ────────────────────────────────────────────────────────────

function playAudio(audioPath) {
  if (activeAudio) {
    activeAudio.pause();
    activeAudio = null;
  }
  const audio = new Audio(audioPath);
  activeAudio = audio;
  el.btnAudio.classList.add('playing');

  audio.play().catch(() => {
    // Autoplay blocked or file missing — fail silently
    el.btnAudio.classList.remove('playing');
  });
  audio.addEventListener('ended', () => {
    el.btnAudio.classList.remove('playing');
    if (activeAudio === audio) activeAudio = null;
  });
}

function stopAudio() {
  if (activeAudio) {
    activeAudio.pause();
    activeAudio = null;
  }
  el.btnAudio.classList.remove('playing');
}

// ── Quiz rendering ────────────────────────────────────────────────────────────

function renderItem(index) {
  const item  = currentLesson.items[index];
  const total = currentLesson.items.length;

  answered = false;
  stopAudio();

  updateProgress(index, total);

  el.englishSentence.textContent = item.english;
  el.btnNext.classList.add('hidden');
  el.btnAudio.disabled = false;

  // Build MCQ option buttons
  el.mcqOptions.innerHTML = '';
  item.mcq.options.forEach((option, i) => {
    const btn = document.createElement('button');
    btn.className   = 'option-btn';
    btn.textContent = option;
    btn.dataset.idx = i;
    btn.addEventListener('click', () => onAnswer(i, item));
    el.mcqOptions.appendChild(btn);
  });
}

function onAnswer(selectedIndex, item) {
  if (answered) return;
  answered = true;

  const correct = selectedIndex === item.mcq.correct_index;
  if (correct) score++;

  // Reveal correct / wrong visual states on all options
  el.mcqOptions.querySelectorAll('.option-btn').forEach((btn, i) => {
    btn.disabled = true;
    if (i === item.mcq.correct_index) {
      btn.classList.add('correct');
    } else if (i === selectedIndex) {
      btn.classList.add('wrong');
    }
  });

  // Auto-play the Telugu audio as part of answer reveal
  playAudio(item.audio_path);

  el.btnNext.classList.remove('hidden');
  el.btnNext.focus();
}

function onNext() {
  itemIndex++;
  if (itemIndex >= currentLesson.items.length) {
    showSummary();
  } else {
    renderItem(itemIndex);
  }
}

// ── Summary ───────────────────────────────────────────────────────────────────

function showSummary() {
  stopAudio();
  const total = currentLesson.items.length;

  // Fill the progress bar to 100 %
  el.progressBarFill.style.width = '100%';
  el.progressBar.setAttribute('aria-valuenow', 100);
  el.progressLabel.textContent = `${total} / ${total}`;

  el.summaryScore.textContent = `${score} / ${total} correct`;
  el.summaryDate.textContent  =
    `Lesson: ${currentLesson.date}  ·  Level: ${currentLesson.difficulty}`;

  showView('summary');
}

// ── Start a quiz session ──────────────────────────────────────────────────────

async function startQuiz(dateStr) {
  showView('loading');
  el.btnHome.classList.add('active');
  el.btnArchive.classList.remove('active');

  try {
    currentLesson = await loadLesson(dateStr);
    itemIndex = 0;
    score     = 0;
    showView('quiz');
    renderItem(0);
  } catch (err) {
    el.errorMsg.textContent = err.message;
    showView('error');
  }
}

// ── Archive ───────────────────────────────────────────────────────────────────

function renderArchive() {
  el.btnHome.classList.remove('active');
  el.btnArchive.classList.add('active');
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

// ── Navigation event handlers ─────────────────────────────────────────────────

el.btnHome.addEventListener('click', () => {
  const dateStr = getDateParam() || manifest?.lessons[0]?.date;
  if (dateStr) {
    pushDateParam(dateStr);
    startQuiz(dateStr);
  }
});

el.btnArchive.addEventListener('click', () => {
  pushArchiveHash();
  renderArchive();
});

el.btnAudio.addEventListener('click', () => {
  if (!currentLesson) return;
  playAudio(currentLesson.items[itemIndex].audio_path);
});

el.btnNext.addEventListener('click', onNext);

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
  } else {
    const dateStr = getDateParam() || manifest?.lessons[0]?.date;
    if (dateStr) startQuiz(dateStr);
  }
});

// ── Bootstrap ─────────────────────────────────────────────────────────────────

(async function init() {
  showView('loading');
  try {
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

    const dateStr = getDateParam() || manifest.lessons[0].date;
    pushDateParam(dateStr);
    await startQuiz(dateStr);
  } catch (err) {
    el.errorMsg.textContent = err.message;
    showView('error');
  }
})();
