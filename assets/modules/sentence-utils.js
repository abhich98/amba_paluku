import { mkAudioBtn } from './audio.js';
import { escapeHtml } from './text-utils.js';

export function getSentenceField(sentence, field, fallback = '') {
  if (!sentence || typeof sentence !== 'object') return fallback;
  const value = sentence[field];
  return value == null ? fallback : value;
}

export function getSentenceText(sentence, fallback = '') {
  return getSentenceField(sentence, 'text', fallback);
}

export function getSentenceLanguage(sentence, fallback = '') {
  return getSentenceField(sentence, 'language', fallback);
}

export function getSentenceAudioPath(sentence, fallback = '') {
  return getSentenceField(sentence, 'audio_path', fallback);
}

export function getSentenceTransliteration(sentence, fallback = '') {
  return getSentenceField(sentence, 'transliteration', fallback);
}

export function parseSerializedSentence(raw, fallback = {}) {
  if (!raw) return fallback;
  if (typeof raw === 'object') return raw;
  try {
    const parsed = JSON.parse(raw);
    return parsed && typeof parsed === 'object' && !Array.isArray(parsed) ? parsed : fallback;
  } catch {
    return fallback;
  }
}

export function buildSentenceRichContent(
  sentence,
  {
    textOverride = null,
    transliterationOverride = null,
    showText = true,
    showAudio = true,
    showTransliteration = true,
    copyClass = 'choice-copy',
    textClass = 'choice-script',
    audioLabel = 'Play audio',
  } = {},
) {
  const language = getSentenceLanguage(sentence);
  const text = textOverride == null ? getSentenceText(sentence) : textOverride;
  const transliteration = transliterationOverride == null
    ? getSentenceTransliteration(sentence)
    : transliterationOverride;
  const audioPath = showAudio ? getSentenceAudioPath(sentence) : '';

  const audioHtml = audioPath ? mkAudioBtn(audioPath, audioLabel) : '';
  const transliterationHtml = showTransliteration && transliteration
    ? `<em class="choice-translit">${escapeHtml(transliteration)}</em>`
    : '';
  const textHtml = showText && text
    ? `<span class="${textClass}" data-language="${escapeHtml(language)}">${escapeHtml(text)}</span>`
    : '';

  if (!transliterationHtml && !textHtml) {
    return audioHtml;
  }

  return `${audioHtml}<span class="${copyClass}">${transliterationHtml}${textHtml}</span>`;
}

export function buildSentenceSupportBlock(sentence, options = {}) {
  const content = buildSentenceRichContent(sentence, options);
  if (!content) return '';
  return `<div class="sentence-support">${content}</div>`;
}

export function buildBlankedSentenceText(sourceSentence, omitLoc) {
  const words = String(sourceSentence || '').split(/\s+/).filter(Boolean);
  const omitIndex = Number(omitLoc) - 1;
  if (omitIndex < 0 || omitIndex >= words.length) {
    return String(sourceSentence || '');
  }
  words[omitIndex] = '_____';
  return words.join(' ');
}

export function buildBlankedSentence(item) {
  const sourceSentence = getSentenceText(item.question_sentence || {}, '');
  return buildBlankedSentenceText(sourceSentence, item.omit_loc);
}

export function buildMcqOptionsJson(options) {
  return JSON.stringify(options);
}

export function buildMatchPromptsJson(prompts) {
  return JSON.stringify(prompts);
}

export function buildMatchOptionsJson(options) {
  return JSON.stringify(options);
}

export function parseMcqOptions(question) {
  try {
    const parsed = JSON.parse(question.optionsJson || '[]');
    return Array.isArray(parsed) ? parsed : [];
  } catch {
    return [];
  }
}

export function parseMatchPrompts(question) {
  try {
    const parsed = JSON.parse(question.promptsJson || '[]');
    return Array.isArray(parsed) ? parsed : [];
  } catch {
    return [];
  }
}

export function parseMatchOptions(question) {
  try {
    const parsed = JSON.parse(question.optionsJson || '[]');
    return Array.isArray(parsed) ? parsed : [];
  } catch {
    return [];
  }
}

export function formatMcqOption(option) {
  if (!option) return 'No answer';
  const transliteration = getSentenceTransliteration(option);
  const text = getSentenceText(option);
  return transliteration ? `${transliteration} (${text})` : text;
}
