import { el, state, views } from './context.js';
import { stopAudio } from './audio.js';
import {
  buildBlankedSentence,
  formatMcqOption,
  getSentenceText,
  getSentenceTransliteration,
} from './sentence-utils.js';
import {
  evaluateItem,
  getMcqAnswerValue,
  parseMatchAnswerValue,
} from './scoring.js';
import { escapeHtml } from './text-utils.js';
import { pushDateParam } from './router.js';

export function showView(name) {
  Object.values(views).forEach((v) => v.classList.add('hidden'));
  views[name].classList.remove('hidden');
  el.progressWrap.classList.toggle('hidden', name !== 'quiz');
}

export function updateProgress(current, total) {
  const pct = total > 0 ? Math.round((current / total) * 100) : 0;
  el.progressBarFill.style.width = `${pct}%`;
  el.progressBar.setAttribute('aria-valuenow', pct);
  const labelCurrent = total > 0 ? Math.min(current + 1, total) : 0;
  el.progressLabel.textContent = `${labelCurrent} / ${total}`;
}

function buildMatchPairLines(prompts, options, response) {
  const optionById = new Map((options || []).map((opt) => [opt.id, opt]));
  return prompts.map((prompt) => {
    const promptSentence = prompt.prompt_sentence || {};
    const promptLeft = getSentenceText(promptSentence);
    const chosenOptionId = response[prompt.id] || '';
    const chosen = chosenOptionId
      ? getSentenceText(optionById.get(chosenOptionId), chosenOptionId)
      : 'No answer';
    return `<li><span class="match-result-left">${escapeHtml(promptLeft)}</span><span class="match-result-arrow" aria-hidden="true">→</span><span class="match-result-right">${escapeHtml(chosen)}</span></li>`;
  }).join('');
}

function buildCorrectMatchPairLines(prompts) {
  return prompts.map((prompt) => {
    const promptSentence = prompt.prompt_sentence || {};
    const answerSentence = prompt.answer_sentence || {};
    return `<li><span class="match-result-left">${escapeHtml(getSentenceText(promptSentence))}</span><span class="match-result-arrow" aria-hidden="true">→</span><span class="match-result-right">${escapeHtml(getSentenceText(answerSentence))}</span></li>`;
  }).join('');
}

export function buildResultReviewHtml(lesson, answers) {
  const rows = lesson.items.map((item, idx) => {
    const isCorrect = evaluateItem(item, answers);
    const status = isCorrect ? 'Correct' : 'Wrong';
    const statusClass = isCorrect ? 'result-pill correct' : 'result-pill wrong';

    if (item.type === 'mcq_bimodal') {
      const selected = item.options.find((opt) => opt.id === getMcqAnswerValue(answers, item.id));
      const correct = item.options.find((opt) => opt.id === item.correct_option_id);
      return `<li class="result-row"><div class="result-head"><span class="${statusClass}">${status}</span><span class="result-q">Q${idx + 1}: ${escapeHtml(getSentenceText(item.question_sentence || {}))}</span></div><div class="result-detail"><strong>Your answer:</strong> ${escapeHtml(formatMcqOption(selected))}</div><div class="result-detail"><strong>Correct answer:</strong> ${escapeHtml(formatMcqOption(correct))}</div></li>`;
    }

    if (item.type === 'fill_blank_audio') {
      const userAnswer = answers[item.id] || 'No answer';
      const correctAnswerText = getSentenceText(item.display_correct_answer || {}, '');
      const correctAnswerTransliteration = getSentenceTransliteration(item.display_correct_answer || {}, '');
      const correctAnswerDisplay = correctAnswerTransliteration
        ? `${correctAnswerText} (${correctAnswerTransliteration})`
        : correctAnswerText;
      return `<li class="result-row"><div class="result-head"><span class="${statusClass}">${status}</span><span class="result-q">Q${idx + 1}: ${escapeHtml(buildBlankedSentence(item))}</span></div><div class="result-detail"><strong>Your answer:</strong> ${escapeHtml(userAnswer)}</div><div class="result-detail"><strong>Correct answer:</strong> ${escapeHtml(correctAnswerDisplay)}</div></li>`;
    }

    if (item.type === 'match_audio_text') {
      const response = parseMatchAnswerValue(answers[item.id]);
      return `<li class="result-row"><div class="result-head"><span class="${statusClass}">${status}</span><span class="result-q">Q${idx + 1}: Match prompts to options</span></div><div class="result-detail"><strong>Your answer:</strong><ul class="match-result-list">${buildMatchPairLines(item.prompts, item.options, response)}</ul></div><div class="result-detail"><strong>Correct answer:</strong><ul class="match-result-list">${buildCorrectMatchPairLines(item.prompts)}</ul></div></li>`;
    }

    return '';
  });

  return `<div class="results-review"><h3>Your Responses</h3><ul class="result-list">${rows.join('')}</ul></div>`;
}

export function showSummary(correctCount, total, reviewHtml) {
  stopAudio();

  el.progressBarFill.style.width = '100%';
  el.progressBar.setAttribute('aria-valuenow', 100);
  el.progressLabel.textContent = `${total} / ${total}`;

  el.summaryScore.textContent = `${correctCount} / ${total} correct`;
  el.summaryDate.innerHTML =
    `Lesson: ${escapeHtml(state.currentLesson.date)}  ·  Level: ${escapeHtml(state.currentLesson.difficulty)}${reviewHtml}`;

  showView('summary');
}

export function renderArchive(startQuiz) {
  stopAudio();

  el.archiveList.innerHTML = '';

  if (!state.manifest || state.manifest.lessons.length === 0) {
    const li = document.createElement('li');
    li.className = 'archive-empty';
    li.textContent = 'No lessons yet. Run the generator to create the first lesson.';
    el.archiveList.appendChild(li);
    showView('archive');
    return;
  }

  state.manifest.lessons.forEach((entry) => {
    const li = document.createElement('li');
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

export function renderLanding() {
  stopAudio();
  showView('landing');
}
