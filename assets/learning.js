/* Shared, dependency-free stepper and retrieval-practice widgets. */
'use strict';
document.querySelectorAll('[data-stepper]').forEach((root) => {
  const panels = [...root.querySelectorAll('[data-panel]')];
  const previous = root.querySelector('[data-previous]');
  const next = root.querySelector('[data-next]');
  const count = root.querySelector('[data-count]');
  let position = 0;
  function render() {
    panels.forEach((panel, index) => { panel.hidden = index !== position; });
    count.textContent = `Step ${position + 1} of ${panels.length}`;
    previous.disabled = position === 0;
    next.disabled = position === panels.length - 1;
  }
  previous.addEventListener('click', () => { position = Math.max(0, position - 1); render(); });
  next.addEventListener('click', () => { position = Math.min(panels.length - 1, position + 1); render(); });
  render();
});
document.querySelectorAll('[data-quiz]').forEach((form) => {
  const feedback = form.querySelector('[data-feedback]');
  form.addEventListener('submit', (event) => {
    event.preventDefault();
    const choice = form.querySelector('input:checked');
    if (!choice) {
      feedback.dataset.state = 'retry';
      feedback.textContent = 'Choose an answer, then check your reasoning.';
      return;
    }
    const correct = choice.value === form.dataset.answer;
    feedback.dataset.state = correct ? 'correct' : 'retry';
    feedback.textContent = correct ? form.dataset.correct : form.dataset.retry;
  });
  form.addEventListener('change', () => { feedback.textContent = ''; delete feedback.dataset.state; });
});
