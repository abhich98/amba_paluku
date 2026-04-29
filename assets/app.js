import { bindInlineAudioClicks } from './modules/audio.js';
import { el, getSurveyRoot, resetSurveyRoot, state } from './modules/context.js';
import {
  loadLesson,
  loadManifest,
  loadUiText,
  resolveActiveLessonEntries,
} from './modules/data-loader.js';
import {
  getDateParam,
  pushArchiveHash,
  pushDateParam,
  pushLandingRoute,
} from './modules/router.js';
import { mountSurvey } from './modules/survey-builder.js';
import { registerSurveyExtensions } from './modules/survey-extensions.js';
import { applyUiTextConfig, setActiveNav } from './modules/ui-config.js';
import { renderArchive, renderLanding, showView } from './modules/views.js';

async function startQuiz(dateStr) {
  showView('loading');
  setActiveNav('today');

  try {
    state.currentLesson = await loadLesson(dateStr);
    const surveyRoot = resetSurveyRoot() || getSurveyRoot();
    if (!surveyRoot) throw new Error('Survey root not found.');
    surveyRoot.innerHTML = '';
    showView('quiz');
    await new Promise((resolve) => requestAnimationFrame(() => requestAnimationFrame(resolve)));
    mountSurvey(state.currentLesson);
  } catch (err) {
    el.errorMsg.textContent = err.message;
    showView('error');
  }
}

function showLanding() {
  setActiveNav('landing');
  renderLanding();
}

function showArchive() {
  setActiveNav('archive');
  renderArchive(startQuiz);
}

function bindNavigationEvents() {
  el.btnLanding.addEventListener('click', () => {
    pushLandingRoute();
    showLanding();
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
    showArchive();
  });

  el.btnRestart.addEventListener('click', () => {
    if (state.currentLesson) startQuiz(state.currentLesson.date);
  });

  el.btnGoArchive.addEventListener('click', () => {
    pushArchiveHash();
    showArchive();
  });

  el.btnRetry.addEventListener('click', () => {
    const dateStr = getDateParam() || state.manifest?.lessons[0]?.date;
    if (dateStr) startQuiz(dateStr);
    else location.reload();
  });

  window.addEventListener('popstate', () => {
    if (window.location.hash === '#archive') {
      showArchive();
    } else if (!getDateParam()) {
      showLanding();
    } else {
      const dateStr = getDateParam() || state.manifest?.lessons[0]?.date;
      if (dateStr) startQuiz(dateStr);
    }
  });
}

async function init() {
  showView('loading');
  try {
    registerSurveyExtensions();
    try {
      state.uiText = await loadUiText();
      applyUiTextConfig(state.uiText);
    } catch {
      // Continue with inline defaults when UI text file is missing.
    }

    const rawManifest = await loadManifest();
    const activeEntries = await resolveActiveLessonEntries(rawManifest.lessons || []);
    state.manifest = {
      ...rawManifest,
      lessons: activeEntries,
    };

    if (state.manifest.lessons.length === 0) {
      el.errorMsg.textContent =
        'No lessons available yet. Run the Python generator to create today\'s lesson.';
      showView('error');
      return;
    }

    if (window.location.hash === '#archive') {
      showArchive();
      return;
    }

    if (!getDateParam()) {
      showLanding();
      return;
    }

    const dateStr = getDateParam() || state.manifest.lessons[0].date;
    pushDateParam(dateStr);
    await startQuiz(dateStr);
  } catch (err) {
    el.errorMsg.textContent = err.message;
    showView('error');
  }
}

bindInlineAudioClicks();
bindNavigationEvents();
init();
