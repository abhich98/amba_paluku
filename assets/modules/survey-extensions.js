import { MCQ_AUDIO_TYPE, MATCH_CARDS_TYPE } from './constants.js';
import { state } from './context.js';
import {
  buildSentenceRichContent,
  getSentenceLanguage,
  getSentenceText,
  parseMatchOptions,
  parseMatchPrompts,
  parseMcqOptions,
  parseSerializedSentence,
} from './sentence-utils.js';
import { parseMatchAnswerValue } from './scoring.js';
import { capitalizeWord, escapeHtml } from './text-utils.js';

function enhanceMcqOptionDom(question, element) {
  const options = parseMcqOptions(question);
  const radioInputs = element.querySelectorAll('input[type="radio"]');

  radioInputs.forEach((input) => {
    const option = options.find((opt) => opt.id === input.value);
    if (!option) return;

    const item = input.closest('.sd-item, .sd-selectbase__item');
    const label = item?.querySelector('.sd-item__control-label');
    if (!item || !label) return;
    if (label.dataset.audioEnhanced === 'true') return;

    label.dataset.audioEnhanced = 'true';
    label.innerHTML = `<span class="mcq-option-layout">${buildSentenceRichContent(option, { audioLabel: 'Play option audio' })}</span>`;
  });
}

function enhanceMcqPromptDom(question, element) {
  const promptSentence = parseSerializedSentence(question.promptSentenceJson, { text: question.promptText || '' });
  const titleNode = element.querySelector('.sd-title, .sd-question__title');
  if (!titleNode || titleNode.dataset.sentenceEnhanced === 'true') return;

  titleNode.dataset.sentenceEnhanced = 'true';
  titleNode.innerHTML = buildSentenceRichContent(promptSentence, {
    audioLabel: 'Play prompt audio',
    copyClass: 'choice-copy choice-copy--prompt',
  });
}

function enhanceMatchCardsDom(question, element) {
  const prompts = parseMatchPrompts(question);
  const options = parseMatchOptions(question);
  const boardElement = element.querySelector('.match-board');
  if (!boardElement) return;

  const optionById = new Map(options.map((opt) => [opt.id, opt]));

  let selectedPromptIndex = -1;
  const pairsField = question.contentPanel.getQuestionByName('pairs');
  let pairs = state.matchSelections[question.name]
    ? { ...state.matchSelections[question.name] }
    : parseMatchAnswerValue(question.value);
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
    state.matchSelections[question.name] = { ...pairs };
    if (pairsField) {
      pairsField.value = nextValue;
    }
  }

  function renderBoard() {
    const usedOptions = new Set(Object.values(pairs));
    const promptLabelLang = getSentenceLanguage(prompts[0]?.prompt_sentence, 'prompt');
    const optionLabelLang = getSentenceLanguage(options[0], 'option');
    const promptMode = question.promptMode || 'audio_text';
    const showPromptAudio = promptMode === 'audio' || promptMode === 'audio_text';
    const showPromptText = promptMode === 'text' || promptMode === 'audio_text';
    const showPromptTransliteration = promptMode !== 'audio';

    const promptCards = prompts.map((prompt, index) => {
      const assignedOptionId = pairs[prompt.id] || '';
      const assignedText = assignedOptionId
        ? getSentenceText(optionById.get(assignedOptionId), assignedOptionId)
        : '';
      const promptSentence = prompt.prompt_sentence || {};
      const selectedClass = selectedPromptIndex === index ? ' selected' : '';
      const matchedClass = assignedOptionId ? ' matched' : '';
      const promptContent = buildSentenceRichContent(promptSentence, {
        showAudio: showPromptAudio,
        showText: showPromptText,
        showTransliteration: showPromptTransliteration,
        copyClass: 'match-card-copy',
        audioLabel: 'Play prompt audio',
      });
      const audioOnlyLabel = !showPromptText && !showPromptTransliteration
        ? `<span class="match-card-copy match-card-copy--audio-only"><span class="prompt-audio-only-label">Prompt ${index + 1}</span></span>`
        : '';
      return `<div class="match-prompt-card${selectedClass}${matchedClass}" data-prompt-idx="${index}" role="button" tabindex="0">${promptContent || audioOnlyLabel}<span class="match-assigned">${assignedText ? `Matched: ${escapeHtml(assignedText)}` : 'Tap then pick option'}</span></div>`;
    }).join('');

    const optionCards = options.map((option, index) => {
      const selectedClass = usedOptions.has(option.id) ? ' used' : '';
      return `<button type="button" class="match-option-card${selectedClass}" data-option-idx="${index}">${buildSentenceRichContent(option, { copyClass: 'match-card-copy', audioLabel: 'Play option audio' })}</button>`;
    }).join('');

    boardElement.innerHTML = `<div class="match-column"><h4>${escapeHtml(capitalizeWord(promptLabelLang))} Prompts</h4><div class="match-card-list">${promptCards}</div></div><div class="match-column"><h4>${escapeHtml(capitalizeWord(optionLabelLang))} Options</h4><div class="match-card-list">${optionCards}</div></div>`;

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
        const option = options[optionIndex];
        const prompt = prompts[selectedPromptIndex];
        if (!prompt || !option) return;

        for (const [promptId, assignedOptionId] of Object.entries(pairs)) {
          if (assignedOptionId === option.id && promptId !== prompt.id) {
            delete pairs[promptId];
          }
        }

        pairs[prompt.id] = option.id;
        updateQuestionValue();
        selectedPromptIndex = -1;
        renderBoard();
      });
    });
  }

  renderBoard();
}

export function registerSurveyExtensions() {
  const Survey = window.Survey;
  if (state.surveyExtensionsRegistered || !Survey?.ComponentCollection || !Survey?.Serializer) {
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
        name: 'promptSentenceJson:text',
        default: '{}',
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
      choice.choices = options.map((opt) => ({
        value: opt.id,
        text: getSentenceText(opt),
      }));
    },
    onPropertyChanged(question, propertyName) {
      if (propertyName !== 'instructionText' && propertyName !== 'promptText' && propertyName !== 'promptSentenceJson' && propertyName !== 'optionsJson') {
        return;
      }
      const instruction = question.contentPanel.getQuestionByName('instruction');
      const choice = question.contentPanel.getQuestionByName('choice');
      const options = parseMcqOptions(question);
      instruction.html = `<div class="question-helper question-helper-left">${escapeHtml(question.instructionText)} <span class="required-mark" aria-hidden="true">*</span></div>`;
      choice.title = question.promptText;
      choice.titleLocation = 'top';
      choice.choices = options.map((opt) => ({
        value: opt.id,
        text: getSentenceText(opt),
      }));
    },
    onAfterRender(question, element) {
      enhanceMcqPromptDom(question, element);
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
        name: 'promptMode:text',
        default: 'audio_text',
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

  state.surveyExtensionsRegistered = true;
}
