import { state } from './context.js';
import { escapeHtml } from './text-utils.js';

export function mkAudioBtn(audioPath, label = 'Play') {
  if (!audioPath) return '';
  return `<button type="button" class="inline-audio-btn" data-audio-path="${escapeHtml(audioPath)}" aria-label="${escapeHtml(label)}">🔊</button>`;
}

export function playAudio(audioPath) {
  if (!audioPath) return;
  if (state.activeAudio) {
    state.activeAudio.pause();
    state.activeAudio = null;
  }
  const audio = new Audio(audioPath);
  state.activeAudio = audio;
  document.querySelectorAll('.inline-audio-btn.playing').forEach((btn) => {
    btn.classList.remove('playing');
  });

  audio.play().catch(() => {
    // Autoplay blocked or missing file; keep UX non-blocking.
  });

  audio.addEventListener('ended', () => {
    document.querySelectorAll('.inline-audio-btn.playing').forEach((btn) => {
      btn.classList.remove('playing');
    });
    if (state.activeAudio === audio) state.activeAudio = null;
  });
}

export function stopAudio() {
  if (state.activeAudio) {
    state.activeAudio.pause();
    state.activeAudio = null;
  }
  document.querySelectorAll('.inline-audio-btn.playing').forEach((btn) => {
    btn.classList.remove('playing');
  });
}

export function bindInlineAudioClicks() {
  document.addEventListener('click', (event) => {
    const btn = event.target.closest('.inline-audio-btn');
    if (!btn) return;
    event.preventDefault();
    event.stopPropagation();
    const audioPath = btn.getAttribute('data-audio-path');
    if (!audioPath) return;
    document.querySelectorAll('.inline-audio-btn.playing').forEach((node) => {
      node.classList.remove('playing');
    });
    btn.classList.add('playing');
    playAudio(audioPath);
  });
}
