export const state = {
  manifest: null,
  currentLesson: null,
  activeAudio: null,
  surveyModel: null,
  surveyMeta: {},
  uiText: null,
  surveyExtensionsRegistered: false,
  matchSelections: {},
};

export const views = {
  loading: document.getElementById('view-loading'),
  landing: document.getElementById('view-landing'),
  error: document.getElementById('view-error'),
  quiz: document.getElementById('view-quiz'),
  summary: document.getElementById('view-summary'),
  archive: document.getElementById('view-archive'),
};

export const el = {
  progressWrap: document.getElementById('progress-bar-wrap'),
  progressBarFill: document.getElementById('progress-bar-fill'),
  progressBar: document.getElementById('progress-bar'),
  progressLabel: document.getElementById('progress-label'),

  surveyRoot: document.getElementById('survey-root'),
  appLogo: document.getElementById('app-logo'),
  logoLine1: document.getElementById('logo-line-1'),
  logoLine2: document.getElementById('logo-line-2'),
  landingKicker: document.getElementById('landing-kicker'),
  landingHeading: document.getElementById('landing-heading'),
  landingSubheading: document.getElementById('landing-subheading'),
  btnStartLearning: document.getElementById('btn-start-learning'),
  loadingText: document.getElementById('loading-text'),
  summaryHeading: document.getElementById('summary-heading'),
  archiveHeading: document.getElementById('archive-heading'),

  summaryScore: document.getElementById('summary-score'),
  summaryDate: document.getElementById('summary-date'),
  archiveList: document.getElementById('archive-list'),
  errorMsg: document.getElementById('error-msg'),

  btnLanding: document.getElementById('btn-landing'),
  btnToday: document.getElementById('btn-today'),
  btnArchive: document.getElementById('btn-archive'),
  btnRetry: document.getElementById('btn-retry'),
  btnRestart: document.getElementById('btn-restart'),
  btnGoArchive: document.getElementById('btn-go-archive'),
  btnFeedback: document.getElementById('btn-feedback'),
  landingInstructionsHeading: document.getElementById('landing-instructions-heading'),
  landingInstructionsList: document.getElementById('landing-instructions-list'),
};

export function getSurveyRoot() {
  return document.getElementById('survey-root');
}

export function resetSurveyRoot() {
  const existingRoot = getSurveyRoot();
  if (!existingRoot) return null;

  const freshRoot = document.createElement('div');
  freshRoot.id = 'survey-root';
  freshRoot.className = existingRoot.className;
  existingRoot.replaceWith(freshRoot);
  return freshRoot;
}
