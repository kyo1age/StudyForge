import {answerLetter, shuffleQuestion} from './quiz.mjs';
import {badge, button, el, glyphBox, icon, modeBadge, number, progress, types} from './ui.js';

export function materialView(generation, cached = false) {
  const {material_type: kind, result} = generation;
  const type = types[kind];
  const body = el('div', {class: 'material-body'});
  const panel = el('article', {class: 'panel material', tabindex: '-1'},
    el('header', {class: 'material-head'},
      el('div', {class: 'metadata'}, glyphBox(type.icon, type.color), badge(type.label),
        modeBadge(generation.provider, generation.model_used), cached && badge('Из истории')),
      el('h2', {}, result.title),
      el('p', {class: 'muted'}, `Страницы ${generation.page_from}–${generation.page_to}`),
      generation.provider === 'gemini' && el('p', {class: 'muted'}, geminiUsage(generation))
    ), body);
  if (kind === 'summary') {
    if (result.main_topics?.length) {
      body.append(el('p', {class: 'muted'}, `Темы: ${result.main_topics.join(' · ')}`));
    }
    body.append(...result.sections.map(section => el('section', {class: 'summary-section'},
      el('h3', {}, section.title),
      el('ul', {}, section.points.map(point => el('li', {}, point)))
    )));
  } else if (kind === 'flashcards') {
    flashcards(body, result.cards);
  } else {
    quiz(body, result.questions);
  }
  return panel;
}

function geminiUsage(generation) {
  if (generation.prompt_tokens == null) return 'Gemini не передал данные о токенах.';
  const total = `${number(generation.tokens_used)} токенов`;
  return generation.cost_usd == null ? total : `${total} · оценка $${generation.cost_usd.toFixed(6)}`;
}

function flashcards(body, cards) {
  let index = 0;
  let flipped = false;
  const marks = new Map();

  function move(delta) {
    index += delta;
    flipped = false;
    render('flip');
  }

  function mark(value) {
    marks.set(index, value);
    if (index < cards.length - 1) move(1);
    else render('flip');
  }

  function render(focus = false) {
    const card = cards[index];
    const known = [...marks.values()].filter(value => value === 'know').length;
    const cardButton = el('button', {type: 'button', class: `flashcard${flipped ? ' flipped' : ''}`,
      'data-control': 'flip', 'aria-pressed': String(flipped), onclick: () => {
        flipped = !flipped;
        cardButton.classList.toggle('flipped', flipped);
        cardButton.setAttribute('aria-pressed', String(flipped));
        cardButton.querySelector('.front').setAttribute('aria-hidden', String(flipped));
        cardButton.querySelector('.back').setAttribute('aria-hidden', String(!flipped));
        cardButton.setAttribute('aria-label', flipped ? `Ответ: ${card.answer}. Показать вопрос.` : `Вопрос: ${card.question}. Показать ответ.`);
      },
      'aria-label': flipped ? `Ответ: ${card.answer}. Показать вопрос.` : `Вопрос: ${card.question}. Показать ответ.`
    }, el('span', {class: 'flash-inner'},
      el('span', {class: 'flash-face front', 'aria-hidden': String(flipped)},
        el('span', {class: 'eyebrow'}, 'Вопрос'), el('strong', {}, card.question),
        el('span', {class: 'flip-hint'}, icon('rotate-ccw'), 'Нажмите, чтобы увидеть ответ')),
      el('span', {class: 'flash-face back', 'aria-hidden': String(!flipped)},
        el('span', {class: 'eyebrow'}, 'Ответ'), el('strong', {}, card.answer),
        card.source_page && el('span', {class: 'muted'}, `Страница ${card.source_page}`),
        el('span', {class: 'flip-hint'}, icon('rotate-ccw'), 'Вернуться к вопросу'))
    ));

    body.replaceChildren(
      el('div', {class: 'activity-status', 'aria-live': 'polite'},
        el('strong', {}, `Карточка ${index + 1} из ${cards.length}`),
        el('span', {}, `Знаю: ${known} · Повторить: ${marks.size - known}`)
      ),
      progress(marks.size, cards.length, 'Отмеченные карточки'), cardButton,
      el('div', {class: 'action-row'},
        button('Назад', 'secondary', () => move(-1), 'arrow-left', {disabled: index === 0}),
        button('Далее', 'secondary', () => move(1), 'arrow-right', {disabled: index === cards.length - 1})
      ),
      el('div', {class: 'action-row'},
        button('Повторить', 'secondary', () => mark('repeat'), 'rotate-ccw', {'aria-pressed': String(marks.get(index) === 'repeat')}),
        button('Знаю', 'primary', () => mark('know'), 'check', {'aria-pressed': String(marks.get(index) === 'know')})
      )
    );
    if (focus) cardButton.focus();
  }
  render();
}

function quiz(body, sourceQuestions) {
  let index = 0;
  let questions;
  let answers;

  function reset() {
    questions = sourceQuestions.map(question => shuffleQuestion(question));
    answers = new Map();
    index = 0;
  }

  function showScore() {
    const correct = questions.filter((question, position) => answers.get(position) === question.correctId).length;
    const rate = Math.round(correct / questions.length * 100);
    const heading = el('h3', {tabindex: '-1'}, 'Результат теста');
    body.replaceChildren(
      el('div', {class: 'score'}, heading, el('strong', {class: 'score-number'}, `${rate}%`),
        el('p', {}, `Верных ответов: ${correct} из ${questions.length}`),
        button('Пройти ещё раз', 'primary', () => { reset(); render(true); }, 'rotate-ccw')),
      el('h3', {class: 'review-title'}, 'Разбор ответов'),
      ...questions.map((question, position) => {
        const selection = question.options.findIndex(option => option.id === answers.get(position));
        const right = selection === question.correctIndex;
        return el('section', {class: 'review-item'},
          el('div', {class: 'metadata'}, badge(right ? 'Верно' : 'Неверно', right ? 'live' : 'wrong'),
            el('h4', {}, `${position + 1}. ${question.question}`)),
          el('p', {}, selection < 0 ? 'Ваш ответ: пропущено' :
            `Ваш ответ: ${answerLetter(selection)}. ${question.options[selection].text}`),
          el('p', {class: 'correct'}, `Правильный ответ: ${question.correctLetter}. ${question.options[question.correctIndex].text}`),
          sourceQuestions[position].explanation && el('p', {}, sourceQuestions[position].explanation),
          sourceQuestions[position].source_page && el('p', {}, `Источник: страница ${sourceQuestions[position].source_page}`)
        );
      })
    );
    heading.focus();
  }

  function render(focusQuestion = false) {
    const question = questions[index];
    const answered = el('span', {}, `Ответы: ${answers.size}/${questions.length}`);
    const track = progress(answers.size, questions.length, 'Отвеченные вопросы');
    const legend = el('legend', {tabindex: '-1'}, question.question);
    const options = question.options.map((option, position) => el('label', {class: 'option'},
      el('input', {type: 'radio', name: 'quiz-option', value: option.id,
        checked: answers.get(index) === option.id, onchange: () => {
          answers.set(index, option.id);
          track.value = answers.size;
          answered.textContent = `Ответы: ${answers.size}/${questions.length}`;
        }
      }), el('span', {class: 'answer-letter', 'aria-hidden': 'true'}, answerLetter(position)),
      el('span', {}, option.text)
    ));
    body.replaceChildren(
      el('div', {class: 'activity-status', 'aria-live': 'polite'},
        el('strong', {}, `Вопрос ${index + 1} из ${questions.length}`), answered),
      track, el('fieldset', {class: 'options'}, legend, options),
      el('div', {class: 'action-row split'},
        button('Назад', 'secondary', () => { index--; render(true); }, 'arrow-left', {disabled: index === 0}),
        index < questions.length - 1
          ? button('Далее', 'primary', () => { index++; render(true); }, 'arrow-right')
          : button('Завершить тест', 'primary', showScore, 'check'))
    );
    if (focusQuestion) legend.focus();
  }

  reset();
  render();
}

