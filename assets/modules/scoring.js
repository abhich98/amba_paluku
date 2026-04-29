import { TRANSLIT_SIMILARITY_THRESHOLD } from './constants.js';
import {
  getSentenceLanguage,
  getSentenceText,
  getSentenceTransliteration,
} from './sentence-utils.js';
import { normalizeAcceptedAnswer, translitSimilarity } from './text-utils.js';

export function parseMatchAnswerValue(rawAnswer) {
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

export function getMcqAnswerValue(answers, itemId) {
  const rawAnswer = answers[itemId];
  if (typeof rawAnswer === 'string') return rawAnswer;
  return rawAnswer?.choice || '';
}

function isAnswerAccepted(input, acceptedAnswers) {
  const normalizedInput = normalizeAcceptedAnswer(input);
  if (!normalizedInput) return false;
  return (acceptedAnswers || []).some((answer) => normalizeAcceptedAnswer(getSentenceText(answer)) === normalizedInput);
}

function isTransliterationAnswerAccepted(input, acceptedAnswers) {
  const normalizedInput = normalizeAcceptedAnswer(input);
  if (!normalizedInput) return false;
  return (acceptedAnswers || []).some((answer) => {
    const transliteration = getSentenceTransliteration(answer, '');
    const text = getSentenceText(answer, '');

    if (transliteration && translitSimilarity(input, transliteration) >= TRANSLIT_SIMILARITY_THRESHOLD) {
      return true;
    }

    if (text && translitSimilarity(input, text) >= TRANSLIT_SIMILARITY_THRESHOLD) {
      return true;
    }

    return false;
  });
}

function getFillAnswerMode(item) {
  return item.answer_mode || 'exact';
}

function shouldAcceptTransliterationForFill(item) {
  const questionSentence = item.question_sentence || {};
  const questionLanguage = String(getSentenceLanguage(questionSentence, '') || '').toLowerCase();
  const hasQuestionTransliteration = Boolean(getSentenceTransliteration(questionSentence, '').trim());
  return questionLanguage && questionLanguage !== 'english' && hasQuestionTransliteration;
}

function validateFillAnswer(input, item) {
  if (getFillAnswerMode(item) === 'fuzzy') {
    return isTransliterationAnswerAccepted(input, item.accepted_answers);
  }

  if (isAnswerAccepted(input, item.accepted_answers)) {
    return true;
  }

  if (shouldAcceptTransliterationForFill(item)) {
    return isTransliterationAnswerAccepted(input, item.accepted_answers);
  }

  return false;
}

export function evaluateItem(item, answers) {
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
      const chosenOptionId = response[prompt.id];
      const correctOptionId = prompt.answer_sentence?.id;
      if (!chosenOptionId || selected.has(chosenOptionId) || chosenOptionId !== correctOptionId) {
        return false;
      }
      selected.add(chosenOptionId);
    }
    return true;
  }

  return false;
}
