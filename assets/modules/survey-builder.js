import { MCQ_AUDIO_TYPE, MATCH_CARDS_TYPE } from './constants.js';
import { state, getSurveyRoot } from './context.js';
import { mkAudioBtn } from './audio.js';
import {
  buildBlankedSentence,
  buildBlankedSentenceText,
  buildMatchOptionsJson,
  buildMatchPromptsJson,
  buildMcqOptionsJson,
  buildSentenceSupportBlock,
  getSentenceAudioPath,
  getSentenceLanguage,
  getSentenceText,
  getSentenceTransliteration,
} from './sentence-utils.js';
import { evaluateItem, parseMatchAnswerValue } from './scoring.js';
import { capitalizeWord, escapeHtml } from './text-utils.js';
import { buildResultReviewHtml, showSummary, updateProgress } from './views.js';

function mkFillReferenceBlock(item) {
  const refSentence = item.reference_sentence || {};
  const refText = getSentenceText(refSentence);
  const refLang = getSentenceLanguage(refSentence, 'reference');
  const refAudio = getSentenceAudioPath(refSentence);
  const refTransliteration = getSentenceTransliteration(refSentence);
  const transliterationHtml = refTransliteration
    ? `<em>${escapeHtml(refTransliteration)}</em>`
    : '';

  return `<div class="fill-hint">${mkAudioBtn(refAudio, `Play ${refLang} audio`)}<span class="fill-ref"><strong class="fill-ref-label">Reference (${escapeHtml(capitalizeWord(refLang))}):</strong><span class="fill-ref-content">${transliterationHtml}<span>${escapeHtml(refText)}</span></span></span></div>`;
}

function mkFillPromptBlock(item) {
  const questionSentence = item.question_sentence || {};
  const questionLang = getSentenceLanguage(questionSentence, 'answer');
  const helperText = `Fill in the missing ${questionLang}/transliteration word.`;
  const blankedTransliteration = buildBlankedSentenceText(getSentenceTransliteration(questionSentence, ''), item.omit_loc);
  const promptSupport = buildSentenceSupportBlock(questionSentence, {
    showText: false,
    showAudio: true,
    showTransliteration: Boolean(blankedTransliteration),
    transliterationOverride: blankedTransliteration,
    copyClass: 'fill-ref-content',
    audioLabel: `Play ${questionLang} audio`,
  });

  return `<div class="fill-prompt-block"><p class="question-helper">${escapeHtml(helperText)} <span class="required-mark" aria-hidden="true">*</span></p><div class="fill-question-line" data-language="${escapeHtml(questionLang)}">${escapeHtml(buildBlankedSentence(item))}</div>${promptSupport}</div>`;
}

export function buildSurveyDefinition(lesson) {
  state.surveyMeta = {};
  const pages = lesson.items.map((item, idx) => {
    const qName = item.id;
    state.surveyMeta[qName] = item;

    if (item.type === 'mcq_bimodal') {
      const questionSentence = item.question_sentence || {};
      const optionLanguage = getSentenceLanguage(item.options?.[0], 'target');
      return {
        name: `page_${idx + 1}`,
        elements: [
          {
            type: MCQ_AUDIO_TYPE,
            name: qName,
            titleLocation: 'hidden',
            instructionText: `Select the appropriate ${optionLanguage} translation.`,
            promptText: getSentenceText(questionSentence),
            promptSentenceJson: JSON.stringify(questionSentence),
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
            instructionText: 'Listen to the audio and match each prompt with the correct option.',
            promptsJson: buildMatchPromptsJson(item.prompts),
            optionsJson: buildMatchOptionsJson(item.options),
            promptMode: item.prompt_mode || 'audio_text',
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

export function mountSurvey(lesson) {
  if (state.surveyModel) {
    state.surveyModel.dispose();
    state.surveyModel = null;
  }

  const surveyRoot = getSurveyRoot();
  if (!surveyRoot) {
    throw new Error('Survey root not found.');
  }

  state.matchSelections = {};
  const surveyJSON = buildSurveyDefinition(lesson);
  const Survey = window.Survey;
  state.surveyModel = new Survey.Model(surveyJSON);

  state.surveyModel.onCurrentPageChanged.add((sender) => {
    updateProgress(sender.currentPageNo, lesson.items.length);
  });

  state.surveyModel.onValidateQuestion.add((_, options) => {
    const item = state.surveyMeta[options.name];
    if (!item) return;

    if (item.type === 'match_audio_text') {
      const value = parseMatchAnswerValue(options.value || {});
      const selected = Object.values(value).filter(Boolean);
      if (selected.length !== item.prompts.length) {
        options.error = 'Match all prompts before continuing.';
        return;
      }
      if (selected.length !== new Set(selected).size) {
        options.error = 'Each English option can be used only once.';
      }
    }
  });

  state.surveyModel.onComplete.add((sender) => {
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

      const parsedFromCache = parseMatchAnswerValue(state.matchSelections[item.id]);
      if (Object.keys(parsedFromCache).length > 0) {
        answers[item.id] = JSON.stringify(parsedFromCache);
      }
    }

    const correctCount = lesson.items.filter((item) => evaluateItem(item, answers)).length;
    const reviewHtml = buildResultReviewHtml(lesson, answers);
    showSummary(correctCount, lesson.items.length, reviewHtml);
  });

  surveyRoot.innerHTML = '';
  state.surveyModel.render(surveyRoot);
  updateProgress(0, lesson.items.length);
}
