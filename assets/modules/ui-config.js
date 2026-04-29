import { el } from './context.js';

export function applyUiTextConfig(ui) {
  const title = ui?.appTitle || document.title;
  document.title = title;

  const appTitleMeta = document.querySelector('meta[name="app-title"]');
  if (appTitleMeta) appTitleMeta.content = title;
  if (el.appLogo) el.appLogo.title = title;

  if (el.logoLine1 && ui?.logo?.line1) el.logoLine1.textContent = ui.logo.line1;
  if (el.logoLine2 && ui?.logo?.line2) el.logoLine2.textContent = ui.logo.line2;

  if (el.btnLanding && ui?.nav?.home) el.btnLanding.textContent = ui.nav.home;
  if (el.btnToday && ui?.nav?.today) el.btnToday.textContent = ui.nav.today;
  if (el.btnArchive && ui?.nav?.archive) el.btnArchive.textContent = ui.nav.archive;

  if (el.landingKicker && ui?.landing?.kicker) el.landingKicker.textContent = ui.landing.kicker;
  if (el.landingHeading && ui?.landing?.heading) el.landingHeading.textContent = ui.landing.heading;
  if (el.landingSubheading && ui?.landing?.subheading) {
    el.landingSubheading.textContent = ui.landing.subheading;
  }
  if (el.btnStartLearning && ui?.landing?.cta) el.btnStartLearning.textContent = ui.landing.cta;

  if (el.loadingText && ui?.loadingText) el.loadingText.textContent = ui.loadingText;
  if (el.summaryHeading && ui?.summaryHeading) el.summaryHeading.textContent = ui.summaryHeading;
  if (el.archiveHeading && ui?.archiveHeading) el.archiveHeading.textContent = ui.archiveHeading;

  const instrHeading = ui?.instructions?.heading;
  if (el.landingInstructionsHeading && instrHeading) {
    el.landingInstructionsHeading.textContent =
      instrHeading.en + (instrHeading.te ? ' / ' + instrHeading.te : '');
  }
  const instrItems = ui?.instructions?.items;
  if (el.landingInstructionsList && Array.isArray(instrItems)) {
    el.landingInstructionsList.innerHTML = '';
    instrItems.forEach((item) => {
      const row = document.createElement('div');
      row.className = 'instructions-row';
      row.setAttribute('role', 'listitem');
      const enCell = document.createElement('div');
      enCell.className = 'instructions-cell instructions-cell--en';
      enCell.textContent = item.en || '';
      const teCell = document.createElement('div');
      teCell.className = 'instructions-cell instructions-cell--te';
      teCell.textContent = item.te || '';
      row.appendChild(enCell);
      row.appendChild(teCell);
      el.landingInstructionsList.appendChild(row);
    });
  }
  if (el.btnFeedback) {
    if (ui?.landing?.feedbackCta) el.btnFeedback.textContent = ui.landing.feedbackCta;
    if (ui?.landing?.feedbackUrl) el.btnFeedback.href = ui.landing.feedbackUrl;
  }
}

export function setActiveNav(active) {
  const navMap = {
    landing: el.btnLanding,
    today: el.btnToday,
    archive: el.btnArchive,
  };
  Object.entries(navMap).forEach(([name, node]) => {
    if (!node) return;
    node.classList.toggle('active', name === active);
  });
}
