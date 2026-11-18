import {request, uploadPdf} from './api.js';
import {materialView} from './study.js';
import {badge, button, dateLabel, el, empty, errorBox, fileSize, glyphBox, icon, link,
  modeBadge, number, openDialog, progress, toast, types} from './ui.js';

const main = document.querySelector('#main');
const sections = {
  dashboard: ['Обзор', 'layout-dashboard'],
  documents: ['Документы', 'files'],
  study: ['AI Study', 'sparkles'],
  history: ['История', 'history'],
  settings: ['Настройки', 'settings-2']
};
const state = {
  loading: true, loadError: '', documents: [], history: [], settings: null, quota: null,
  upload: null, job: null, studyError: '', activeMaterial: null, draft: null
};

function view() {
  const name = location.hash.slice(1);
  return Object.hasOwn(sections, name) ? name : 'dashboard';
}

function go(name) {
  if (view() === name) render();
  else location.hash = name;
}

function applyTheme(name) {
  document.documentElement.dataset.theme = name;
  try { localStorage.setItem('studyforge.theme', name); } catch { /* Theme still changes in memory. */ }
  const next = name === 'dark' ? 'Светлая тема' : 'Тёмная тема';
  const control = document.querySelector('#theme');
  control.replaceChildren(icon(name === 'dark' ? 'sun' : 'moon'));
  control.setAttribute('aria-label', next);
  control.title = next;
}

try { applyTheme(localStorage.getItem('studyforge.theme') === 'light' ? 'light' : 'dark'); }
catch { applyTheme('dark'); }

document.querySelector('#theme').onclick = () => {
  applyTheme(document.documentElement.dataset.theme === 'dark' ? 'light' : 'dark');
  if (view() === 'settings') {
    render();
  }
};
document.querySelector('.skip').onclick = event => {
  event.preventDefault();
  main.focus();
};
window.addEventListener('hashchange', () => { render(); main.focus(); });

async function initialize() {
  state.loading = true;
  state.loadError = '';
  render();
  try {
    // Establish the browser's session before issuing concurrent client-scoped requests.
    state.quota = await request('/quota');
    [state.settings, state.documents, state.history] = await Promise.all([
      request('/settings'), request('/documents'), request('/generations')
    ]);
  } catch (error) {
    state.loadError = error.message;
  } finally {
    state.loading = false;
    render();
  }
}

async function refreshQuota() {
  try {
    state.quota = await request('/quota');
    renderChrome();
    const detail = document.querySelector('#quota-detail');
    if (detail) detail.textContent = quotaLabel();
  } catch (error) {
    toast(error.message, true);
  }
}

const quotaLabel = () => `${number(state.quota.used)} / ${number(state.quota.limit)} токенов`;

function renderChrome() {
  const current = view();
  document.querySelector('#navigation').replaceChildren(...Object.entries(sections).map(([key, [label, glyph]]) =>
    el('a', {href: `#${key}`, 'aria-current': current === key ? 'page' : null}, icon(glyph), label)
  ));
  document.querySelector('#crumb').textContent = sections[current][0];
  document.querySelector('#mode').replaceChildren(
    ...(state.settings ? [modeBadge(state.settings.provider, state.settings.model_used)] : [])
  );
  const quota = document.querySelector('#quota');
  if (state.quota) {
    const {used, limit} = state.quota;
    quota.replaceChildren(el('div', {class: 'quota-card'},
      el('div', {class: 'quota-title'}, icon('zap'), 'Недельная квота'),
      progress(used, limit, 'Использованные токены'),
      el('div', {class: 'muted'}, quotaLabel())
    ));
  }
}

function render() {
  renderChrome();
  if (state.loading) {
    main.replaceChildren(el('div', {class: 'skeleton', role: 'status', 'aria-label': 'Загрузка рабочей области'}));
    return;
  }
  if (state.loadError) {
    main.replaceChildren(pageTitle('Обзор', 'Рабочая область недоступна'), errorBox(state.loadError),
      button('Повторить', 'primary', initialize, 'rotate-ccw'));
    return;
  }
  const renderers = {dashboard, documents, study, history, settings};
  main.replaceChildren(renderers[view()]());
}

function pageTitle(title, description, action) {
  return el('header', {class: 'page-title'}, el('div', {},
    el('h1', {}, title), el('p', {}, description)), action);
}

function panel(title, subtitle, action, content, className = '') {
  return el('section', {class: `panel ${className}`},
    el('header', {class: 'panel-head'}, el('div', {}, el('h2', {}, title), subtitle && el('p', {}, subtitle)), action),
    content);
}

function metric(glyph, tint, label, value) {
  return el('div', {class: 'panel metric'}, glyphBox(glyph, tint),
    el('div', {}, el('span', {}, label), el('strong', {}, number(value))));
}

function dashboard() {
  return el('div', {class: 'page'},
    pageTitle('Обзор', 'Ваши документы и учебные материалы в одном месте.'),
    el('section', {class: 'hero'},
      el('div', {class: 'hero-copy'},
        el('div', {class: 'hero-kicker'}, icon('sparkles'), 'УЧЕБНАЯ МАСТЕРСКАЯ'),
        el('h2', {}, 'Рады вас видеть.'),
        el('p', {}, 'Загрузите лекцию и соберите из неё конспект, карточки или тест для самопроверки.'),
        link('Открыть AI Study', 'primary', '#study', 'arrow-right')),
      el('div', {class: 'hero-art', 'aria-hidden': 'true'},
        el('div', {class: 'orbit orbit-outer'}), el('div', {class: 'orbit orbit-inner'}),
        el('div', {class: 'art-glow'}),
        el('div', {class: 'art-card art-notes'}, icon('file-text'), el('i'), el('i')),
        el('div', {class: 'art-card art-layers'}, icon('gallery-vertical-end')),
        el('div', {class: 'art-card art-quiz'}, icon('list-checks')),
        el('div', {class: 'art-spark'}, icon('sparkles'))
      )),
    el('div', {class: 'metrics'},
      metric('files', 'violet', 'Документы', state.documents.length),
      metric('gallery-vertical-end', 'teal', 'Учебные материалы', state.history.length),
      metric('list-checks', 'amber', 'Созданные тесты', state.history.filter(item => item.material_type === 'quiz').length)),
    el('div', {class: 'dashboard-grid'},
      panel('Быстрая загрузка', 'Добавьте источник для следующего занятия.', null, uploadZone(), 'upload-panel'),
      panel('Последние документы', null, link('Все', 'quiet', '#documents', 'chevron-right'),
        state.documents.length ? el('div', {class: 'rows'}, state.documents.slice(0, 4).map(docRow))
          : empty('files', 'Здесь появятся ваши PDF', 'Загрузите первый документ, чтобы начать.'))),
    panel('Недавние материалы', 'Результаты из вашей истории генераций.',
      link('История', 'quiet', '#history', 'history'),
      state.history.length ? el('div', {class: 'rows'}, state.history.slice(0, 4).map(generationRow))
        : empty('sparkles', 'Материалов пока нет', 'Создайте конспект, карточки или тест в AI Study.'))
  );
}

function uploadZone() {
  const limits = state.settings;
  const upload = el('input', {type: 'file', accept: '.pdf,application/pdf', hidden: true});
  const feedback = el('div', {class: 'upload-feedback'});
  const track = progress(0, 100, 'Ход загрузки PDF');
  const status = el('span', {role: 'status'});
  const choose = button('Выбрать PDF', 'secondary', () => upload.click(), 'plus');
  const zone = el('div', {class: 'dropzone'},
    glyphBox('cloud-upload'),
    el('strong', {}, 'Перетащите PDF сюда'),
    el('span', {class: 'muted'}, `До ${fileSize(limits.max_upload_bytes)} · До ${limits.max_pdf_pages} страниц`),
    choose, upload
  );

  function updateUpload() {
    if (!state.upload) return;
    choose.disabled = true;
    zone.setAttribute('aria-busy', 'true');
    const {percent, processing} = state.upload;
    track.max = processing?.total || 100;
    if (processing?.total) track.value = processing.current - 1;
    else if (percent === 100) track.removeAttribute('value');
    else track.value = percent;
    const stage = processing?.stage === 'ocr' ? 'OCR' : 'Чтение PDF';
    status.textContent = processing?.total
      ? `${stage}: страница ${processing.page} · ${processing.current} из ${processing.total}`
      : percent === 100 ? 'Файл отправлен. Извлекаем текст…' : `Загрузка… ${percent}%`;
    if (!feedback.contains(track)) feedback.replaceChildren(status, track);
  }

  async function start(file) {
    if (state.upload || !file) return;
    const problem = !file.name.toLowerCase().endsWith('.pdf') ? 'Выберите файл с расширением .pdf.'
      : !file.size ? 'Файл пуст.' : file.size > limits.max_upload_bytes ? `Файл превышает лимит ${fileSize(limits.max_upload_bytes)}.` : '';
    if (problem) {
      feedback.replaceChildren(errorBox(problem));
      return;
    }
    const uploadId = crypto.randomUUID();
    const active = {percent: 0, update: updateUpload};
    state.upload = active;
    let polling = false;
    const timer = setInterval(async () => {
      if (polling || active.percent < 100) return;
      polling = true;
      try {
        active.processing = await request(`/documents/upload-progress/${uploadId}`);
        if (state.upload === active) active.update();
      } catch { /* The original upload still reports its outcome. */ }
      finally { polling = false; }
    }, 400);
    updateUpload();
    try {
      const doc = await uploadPdf(file, percent => {
        state.upload.percent = percent;
        state.upload.update();
      }, uploadId);
      state.documents.unshift(doc);
      state.upload = null;
      toast('PDF загружен, текст готов к работе.');
      render();
      if (doc.warnings?.length) {
        document.querySelector('.upload-feedback')?.replaceChildren(errorBox(doc.warnings.join(' ')));
        toast(doc.warnings.join(' '), true);
      }
    } catch (error) {
      state.upload = null;
      render();
      document.querySelector('.upload-feedback')?.replaceChildren(errorBox(error.message));
      toast(error.message, true);
    } finally {
      clearInterval(timer);
    }
  }

  upload.onchange = () => { start(upload.files[0]); upload.value = ''; };
  zone.ondragover = event => {
    event.preventDefault();
    if (!state.upload) zone.classList.add('dragging');
  };
  zone.ondragleave = event => { if (!zone.contains(event.relatedTarget)) zone.classList.remove('dragging'); };
  zone.ondrop = event => {
    event.preventDefault();
    zone.classList.remove('dragging');
    if (event.dataTransfer.files.length > 1) {
      feedback.replaceChildren(errorBox('Загрузите один PDF за раз.'));
      return;
    }
    start(event.dataTransfer.files[0]);
  };
  if (state.upload) {
    state.upload.update = updateUpload;
    updateUpload();
  }
  return el('div', {}, zone, feedback);
}

function docRow(doc) {
  return el('div', {class: 'entry'},
    button(null, 'entry-main', () => showDocument(doc), null, {'aria-label': `Открыть ${doc.filename}`}),
    glyphBox('file-text'),
    el('div', {class: 'entry-label'}, el('strong', {}, doc.filename),
      el('small', {}, `${doc.page_count} стр. · ${fileSize(doc.size)}`)),
    el('span', {class: 'entry-end'}, icon('chevron-right'))
  );
}

function documents() {
  return el('div', {class: 'page'},
    pageTitle('Документы', 'Управляйте источниками и просматривайте текст по страницам.'),
    el('div', {class: 'document-grid'},
      panel('Библиотека PDF', `Файлов: ${number(state.documents.length)}`, null,
        state.documents.length ? el('div', {class: 'rows'}, state.documents.map(docRow))
          : empty('files', 'Нет загруженных документов', 'Добавьте PDF, чтобы открыть предпросмотр.')),
      panel('Загрузить PDF', 'Сканы распознаются при настроенном OCR.', null, uploadZone(), 'upload-panel')));
}

async function showDocument(doc) {
  const body = el('div', {class: 'skeleton small', role: 'status', 'aria-label': 'Загрузка предпросмотра'});
  const dialog = openDialog('Документ', body);
  try {
    const detail = await request(`/documents/${doc.id}`);
    body.className = 'document-detail';
    body.removeAttribute('aria-label');
    body.removeAttribute('role');
    body.replaceChildren(
      el('div', {class: 'detail-file'}, glyphBox('file-text'),
        el('div', {}, el('h3', {}, detail.filename),
          el('p', {class: 'muted'}, `${detail.page_count} стр. · ${fileSize(detail.size)} · ${dateLabel(detail.created_at)}`))),
      el('div', {class: 'action-row'},
        button('Удалить', 'danger', () => confirmDelete(detail), 'trash-2'),
        button('Использовать в AI Study', 'primary', () => {
          dialog.close();
          state.draft = {id: detail.id, kind: 'summary', from: '1', to: String(Math.min(detail.page_count, state.settings.max_pages_per_generation))};
          state.activeMaterial = null;
          state.studyError = '';
          go('study');
        }, 'sparkles')),
      el('h3', {}, 'Предпросмотр текста'),
      el('div', {class: 'page-previews'}, detail.pages.map(page => el('article', {},
        el('h4', {}, `Страница ${page.page_num}`), el('p', {}, page.text_preview || 'Текст не найден.'))))
    );
  } catch (error) {
    body.className = 'document-detail';
    body.replaceChildren(errorBox(error.message), button('Повторить', 'secondary', () => showDocument(doc), 'rotate-ccw'));
  }
}

function confirmDelete(doc) {
  const issues = el('div', {});
  const remove = button('Удалить PDF', 'danger solid', async () => {
    remove.disabled = true;
    try {
      await request(`/documents/${doc.id}`, {method: 'DELETE'});
      state.documents = state.documents.filter(item => item.id !== doc.id);
      state.history = state.history.filter(item => item.document_id !== doc.id);
      if (state.activeMaterial?.item.document_id === doc.id) state.activeMaterial = null;
      if (state.draft?.id === doc.id) state.draft = null;
      dialog.close();
      toast('Документ удалён.');
      render();
      main.focus();
    } catch (error) {
      issues.replaceChildren(errorBox(error.message));
    } finally {
      remove.disabled = false;
    }
  }, 'trash-2');
  const dialog = openDialog('Удалить документ?',
    el('p', {}, `«${doc.filename}» и созданные по нему материалы будут удалены.`), issues,
    el('div', {class: 'action-row'}, button('Отмена', 'secondary', () => showDocument(doc)), remove));
}

function generationRow(item) {
  const type = types[item.material_type];
  const doc = state.documents.find(entry => entry.id === item.document_id);
  return el('div', {class: 'entry'},
    button(null, 'entry-main', () => {
      state.activeMaterial = {item, cached: false};
      state.studyError = '';
      go('study');
      requestAnimationFrame(() => main.querySelector('.material')?.focus());
    }, null, {'aria-label': `Открыть материал ${item.result.title}`}),
    glyphBox(type.icon, type.color),
    el('div', {class: 'entry-label'}, el('strong', {}, item.result.title),
      el('small', {}, `${type.label} · ${doc?.filename || 'PDF'} · ${dateLabel(item.created_at)}`)),
    el('span', {class: 'entry-end'}, modeBadge(item.provider, item.model_used), icon('chevron-right'))
  );
}

function history() {
  return el('div', {class: 'page'}, pageTitle('История', 'Сохранённые конспекты, карточки и тесты.'),
    panel('Все материалы', `Сохранено: ${number(state.history.length)}`, null,
      state.history.length ? el('div', {class: 'rows'}, state.history.map(generationRow))
        : empty('history', 'История пока пуста', 'Завершённые генерации появятся здесь.', link('Открыть AI Study', 'primary', '#study', 'sparkles'))));
}

function modeDescription() {
  if (state.settings.provider === 'gemini') return 'Для генерации текст выбранных страниц (до 24 000 символов) передаётся Google, стороннему AI-провайдеру. Обработка регулируется условиями и политикой конфиденциальности провайдера; запросы могут быть платными.';
  if (state.settings.provider === 'openai') return 'Для генерации текст выбранных страниц (до 24 000 символов) передаётся OpenAI, стороннему AI-провайдеру. Обработка регулируется условиями и политикой конфиденциальности провайдера; запросы могут быть платными.';
  if (state.settings.fallback_reason === 'missing_api_key') {
    return 'Для AI-провайдера не задан ключ. Доступен Mock Mode: материалы собираются локально по шаблонам.';
  }
  if (['invalid_budget', 'invalid_model'].includes(state.settings.fallback_reason)) {
    return 'Проверьте модель, тарифы и лимиты AI-провайдера в конфигурации сервера. Сейчас активен Mock Mode.';
  }
  if (state.settings.fallback_reason === 'unsupported_provider') {
    return 'Сервер не распознал выбранного провайдера. Доступен Mock Mode.';
  }
  return 'Демонстрационный режим. Материалы собираются по шаблонам из текста PDF без вызовов AI.';
}

function settings() {
  const themeOptions = el('div', {class: 'action-row'}, ['dark', 'light'].map(name => {
    const current = document.documentElement.dataset.theme === name;
    return button(name === 'dark' ? 'Тёмная' : 'Светлая', current ? 'primary' : 'secondary', () => {
      applyTheme(name);
      render();
      main.querySelector(`[data-theme-option="${name}"]`)?.focus();
    }, name === 'dark' ? 'moon' : 'sun', {'aria-pressed': String(current), 'data-theme-option': name});
  }));
  const {max_upload_bytes, max_pdf_pages, max_pages_per_generation} = state.settings;
  return el('div', {class: 'page settings-page'},
    pageTitle('Настройки', 'Тема интерфейса и параметры сервера.'),
    panel('Внешний вид', 'Тема сохраняется в этом браузере.', null, themeOptions),
    panel('Режим генерации', modeDescription(), modeBadge(state.settings.provider, state.settings.model_used),
      el('p', {class: 'muted'}, 'Провайдер и ключ настраиваются в файле .env на сервере.')),
    panel('Лимиты', null, button('Обновить квоту', 'quiet', refreshQuota, 'rotate-ccw'),
      el('dl', {class: 'limits'},
        el('div', {}, el('dt', {}, 'Размер PDF'), el('dd', {}, fileSize(max_upload_bytes))),
        el('div', {}, el('dt', {}, 'Страниц в PDF'), el('dd', {}, max_pdf_pages)),
        el('div', {}, el('dt', {}, 'Страниц за генерацию'), el('dd', {}, max_pages_per_generation)),
        el('div', {}, el('dt', {}, 'Недельная квота'), el('dd', {id: 'quota-detail'}, quotaLabel())))));
}

function study() {
  const intro = pageTitle('AI Study', 'Соберите учебный материал из выбранных страниц PDF.');
  const modeNote = el('div', {class: 'notice'}, icon('info'), el('span', {}, modeDescription()));
  const form = state.documents.length ? studyForm() : empty('sparkles', 'Добавьте PDF', 'Для генерации нужен документ с извлечённым текстом.',
    link('Перейти к документам', 'primary', '#documents', 'files'));
  const right = state.activeMaterial ? materialView(state.activeMaterial.item, state.activeMaterial.cached)
    : panel('Результат', null, null, empty('book-open', 'Здесь появится материал',
      'Выберите документ, диапазон страниц и формат, затем запустите генерацию.'));
  return el('div', {class: 'page'}, intro, modeNote,
    el('div', {class: 'study-grid'}, panel('Новый материал', null, null, form), right));
}

function studyForm() {
  const max = state.settings.max_pages_per_generation;
  if (!state.documents.some(doc => doc.id === state.draft?.id)) {
    const doc = state.documents[0];
    state.draft = {id: doc.id, kind: 'summary', from: '1', to: String(Math.min(max, doc.page_count))};
  }
  const draft = state.draft;
  const select = el('select', {id: 'document-choice', required: true, disabled: Boolean(state.job)},
    state.documents.map(doc => el('option', {value: doc.id, selected: doc.id === draft.id}, doc.filename)));
  const from = el('input', {id: 'from-page', type: 'number', min: 1, step: 1, required: true,
    value: draft.from, disabled: Boolean(state.job)});
  const to = el('input', {id: 'to-page', type: 'number', min: 1, step: 1, required: true,
    value: draft.to, disabled: Boolean(state.job)});
  const range = el('small', {class: 'muted'});
  const fieldset = el('fieldset', {class: 'formats', disabled: Boolean(state.job)}, el('legend', {}, 'Формат'),
    Object.entries(types).map(([key, type]) => el('label', {class: 'format'},
      el('input', {type: 'radio', name: 'material', value: key, checked: draft.kind === key,
        onchange: () => { draft.kind = key; }}),
      glyphBox(type.icon, type.color), el('span', {}, el('strong', {}, type.label), el('small', {}, type.hint))
    )));
  const setRange = () => {
    const doc = state.documents.find(item => item.id === draft.id);
    from.max = to.max = doc.page_count;
    range.textContent = `В PDF ${doc.page_count} стр. · До ${max} страниц за генерацию.`;
  };
  select.onchange = () => {
    draft.id = Number(select.value);
    setRange();
    from.value = draft.from = '1';
    to.value = draft.to = String(Math.min(max, Number(to.max)));
  };
  from.oninput = () => { draft.from = from.value; };
  to.oninput = () => { draft.to = to.value; };
  setRange();
  const issue = el('div', {}, state.studyError && errorBox(state.studyError));
  const status = el('div', {class: 'notice', role: 'status'}, icon('loader-circle'),
    el('span', {}, state.job?.label || ''));
  if (state.job) state.job.status = status.lastElementChild;
  return el('form', {class: 'study-form', onsubmit: event => {
    event.preventDefault();
    const first = Number(from.value);
    const last = Number(to.value);
    if (last < first || last - first + 1 > max) {
      issue.replaceChildren(errorBox(`Укажите диапазон по порядку, не более ${max} страниц.`));
      return;
    }
    generate({document_id: draft.id, material_type: draft.kind, page_from: first, page_to: last});
  }},
  el('label', {class: 'field', for: 'document-choice'}, 'Документ', select),
  el('div', {class: 'range'},
    el('label', {class: 'field', for: 'from-page'}, 'С какой страницы', from),
    el('label', {class: 'field', for: 'to-page'}, 'По какую страницу', to)),
  range, fieldset, issue, state.job && status,
  el('button', {type: 'submit', class: 'btn primary submit', disabled: Boolean(state.job)},
    icon('sparkles'), state.job ? 'Генерация…' : 'Сгенерировать'));
}

async function generate(payload) {
  if (state.job) return;
  state.studyError = '';
  state.job = {label: 'Отправляем запрос…'};
  const update = label => {
    state.job.label = label;
    if (state.job.status) state.job.status.textContent = label;
  };
  render();
  try {
    let job = await request('/generations', {method: 'POST', body: payload});
    const cached = job.status === 'existing';
    const jobId = job.job_id;
    const deadline = Date.now() + 180_000;
    while (!job.generation && Date.now() < deadline) {
      if (job.status === 'error') throw new Error(job.error || 'Генерация завершилась ошибкой.');
      if (job.status === 'done') throw new Error('Генерация завершилась без результата.');
      update(job.status === 'running' ? 'Готовим материал…' : 'Запрос принят. Ожидаем выполнения…');
      await new Promise(resolve => setTimeout(resolve, 850));
      job = await request(`/jobs/${encodeURIComponent(jobId)}`);
    }
    if (!job.generation) throw new Error('Ответ задерживается. Повторная отправка подключится к той же задаче.');
    const item = job.generation;
    state.activeMaterial = {item, cached};
    if (!state.history.some(entry => entry.id === item.id)) state.history.unshift(item);
    toast(cached ? 'Открыт сохранённый материал.' : 'Учебный материал готов.');
  } catch (error) {
    state.studyError = error.message;
    toast(error.message, true);
  } finally {
    state.job = null;
    render();
    if (!state.studyError && view() === 'study') {
      const result = main.querySelector('.material');
      result?.focus();
      result?.scrollIntoView({block: 'nearest'});
    }
    await refreshQuota();
  }
}

initialize();

