const svgNS = 'http://www.w3.org/2000/svg';

// Content from PDFs, API errors and AI is always inserted as text nodes.
export function el(tag, attrs = {}, ...children) {
  const node = document.createElement(tag);
  for (const [name, value] of Object.entries(attrs)) {
    if (name.startsWith('on')) node.addEventListener(name.slice(2), value);
    else if (value !== false && value != null) node.setAttribute(name, value === true ? '' : value);
  }
  node.append(...children.flat(Infinity).filter(child => child != null && child !== false));
  return node;
}

export function icon(name) {
  const svg = document.createElementNS(svgNS, 'svg');
  svg.setAttribute('aria-hidden', 'true');
  svg.setAttribute('viewBox', '0 0 24 24');
  const use = document.createElementNS(svgNS, 'use');
  use.setAttribute('href', `/vendor/icons.svg#${name}`);
  svg.append(use);
  return svg;
}

export const button = (label, shape, action, glyph, attrs = {}) =>
  el('button', {type: 'button', class: `btn ${shape}`, onclick: action, ...attrs}, glyph && icon(glyph), label);
export const link = (label, shape, href, glyph) =>
  el('a', {class: `btn ${shape}`, href}, glyph && icon(glyph), label);
export const badge = (text, kind = '') => el('span', {class: `badge ${kind}`}, text);
export const glyphBox = (glyph, color = 'violet') => el('span', {class: `glyph ${color}`}, icon(glyph));

export const types = {
  summary: {label: 'Конспект', icon: 'file-text', color: 'violet', hint: 'Главные идеи по разделам'},
  flashcards: {label: 'Карточки', icon: 'gallery-vertical-end', color: 'teal', hint: 'Вопросы для повторения'},
  quiz: {label: 'Тест', icon: 'list-checks', color: 'amber', hint: 'Проверка понимания'}
};

export const number = value => new Intl.NumberFormat('ru-RU').format(value);
export const fileSize = bytes => bytes >= 1024 * 1024
  ? `${number(Math.round(bytes / (1024 * 1024) * 10) / 10)} МБ`
  : `${number(Math.max(1, Math.ceil(bytes / 1024)))} КБ`;

export function dateLabel(value) {
  const time = new Date(value?.replace(' ', 'T') + 'Z');
  return Number.isNaN(time.getTime()) ? '' : new Intl.DateTimeFormat('ru', {day: 'numeric', month: 'short', year: 'numeric'}).format(time);
}

export function progress(value, max, label) {
  return el('progress', {value, max: Math.max(1, max), 'aria-label': label});
}

export function empty(glyph, title, detail, action) {
  return el('div', {class: 'empty'}, glyphBox(glyph), el('h3', {}, title),
    el('p', {}, detail), action);
}

export function errorBox(text) {
  return el('div', {class: 'notice error', role: 'alert'}, icon('circle-alert'), el('span', {}, text));
}

let toastTimer;
export function toast(message, error = false) {
  const box = document.querySelector('#toasts');
  clearTimeout(toastTimer);
  box.replaceChildren(el('div', {class: `toast${error ? ' failed' : ''}`},
    icon(error ? 'circle-alert' : 'check'), el('span', {}, message)));
  toastTimer = setTimeout(() => box.replaceChildren(), 4800);
}

export function openDialog(title, ...children) {
  const dialog = document.querySelector('#modal');
  document.querySelector('#dialog-content').replaceChildren(
    el('div', {class: 'dialog-head'}, el('h2', {id: 'dialog-title'}, title),
      button(null, 'icon-button', () => dialog.close(), 'x', {'aria-label': 'Закрыть'})),
    ...children
  );
  if (!dialog.open) dialog.showModal();
  return dialog;
}

export function modeBadge(provider, model) {
  if (provider === 'mock') return badge('Mock Mode', 'mock');
  if (provider === 'gemini') return badge('AI-провайдер', 'live');
  if (provider === 'openai') return badge('OpenAI', 'live');
  return badge('Режим неизвестен');
}

