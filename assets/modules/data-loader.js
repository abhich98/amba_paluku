import { MANIFEST_URL, UI_TEXT_URL } from './constants.js';
import { state } from './context.js';

export async function fetchJSON(url) {
  const resp = await fetch(url);
  if (!resp.ok) throw new Error(`HTTP ${resp.status} fetching ${url}`);
  return resp.json();
}

export async function loadManifest() {
  return fetchJSON(MANIFEST_URL);
}

export async function resolveActiveLessonEntries(entries) {
  const checks = await Promise.all(
    (entries || []).map(async (entry) => {
      try {
        const lesson = await fetchJSON(entry.path);
        return lesson?.status === 'active' ? entry : null;
      } catch {
        return null;
      }
    }),
  );
  return checks.filter(Boolean);
}

export async function loadUiText() {
  return fetchJSON(UI_TEXT_URL);
}

export async function loadLesson(dateStr) {
  const entry = state.manifest.lessons.find((l) => l.date === dateStr);
  if (!entry) throw new Error(`No lesson found for ${dateStr}.`);
  return fetchJSON(entry.path);
}
