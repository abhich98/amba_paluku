export function getDateParam() {
  return new URLSearchParams(window.location.search).get('date');
}

export function pushDateParam(dateStr) {
  const url = new URL(window.location);
  url.searchParams.set('date', dateStr);
  url.hash = '';
  window.history.pushState({ date: dateStr }, '', url);
}

export function pushArchiveHash() {
  const url = new URL(window.location);
  url.hash = 'archive';
  window.history.pushState({ archive: true }, '', url);
}

export function pushLandingRoute() {
  const url = new URL(window.location);
  url.searchParams.delete('date');
  url.hash = '';
  window.history.pushState({ landing: true }, '', url);
}
