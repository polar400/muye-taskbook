// Evaluate this file in a freshly loaded 1440 x 900 preview tab.
// PowerShell: encode UTF-8 contents and pass to agent-browser eval -b (see README.md).
(async () => {
  const results = [];
  const q = selector => document.querySelector(selector);
  const pause = ms => new Promise(resolve => setTimeout(resolve, ms));
  const check = (name, condition, detail) => {
    results.push({ name, passed: Boolean(condition), detail });
    if (!condition) throw new Error(`${name}: ${JSON.stringify(detail)}`);
  };
  const pageY = element => element.getBoundingClientRect().top + scrollY;
  async function move(y) {
    window.scrollTo({ top: y, behavior: 'instant' });
    await new Promise(resolve => requestAnimationFrame(() => requestAnimationFrame(resolve)));
    await pause(50);
  }
  const runwayY = (runwaySelector, stageSelector, progress) => {
    const runway = q(runwaySelector), stage = q(stageSelector);
    return pageY(runway) - parseFloat(getComputedStyle(stage).top) + (runway.offsetHeight - stage.offsetHeight) * progress;
  };
  if (document.documentElement.classList.contains('reduced-motion')) q('#motion-toggle').click();
  check('six_sections_and_navigation', document.querySelectorAll('.experiment').length === 6 && document.querySelectorAll('.chapter-nav a').length === 6, '6 / 6');

  const cards = [...document.querySelectorAll('.reveal-card')];
  let animationStarts = 0;
  cards.forEach(card => card.addEventListener('animationstart', () => animationStarts++));
  await move(pageY(q('.reveal-grid')) - 180);
  await pause(1200);
  check('reveal_all_cards', cards.every(card => card.classList.contains('revealed') && Number(getComputedStyle(card).opacity) === 1), cards.map(card => card.querySelector('.reveal-state').textContent));
  const firstStarts = animationStarts;
  await move(0);
  await move(pageY(q('.reveal-grid')) - 180);
  await pause(200);
  check('reveal_does_not_replay', firstStarts > 0 && animationStarts === firstStarts, { firstStarts, animationStarts });

  await move(runwayY('.linked-runway', '.linked-stage', .25));
  const linkedA = parseInt(q('#linked-percent').textContent);
  const readingA = Number(q('.reading-track').getAttribute('aria-valuenow'));
  await move(runwayY('.linked-runway', '.linked-stage', .75));
  const linkedB = parseInt(q('#linked-percent').textContent);
  const readingB = Number(q('.reading-track').getAttribute('aria-valuenow'));
  await move(runwayY('.linked-runway', '.linked-stage', .25));
  const linkedReturn = parseInt(q('#linked-percent').textContent);
  check('linked_progress_and_reverse', Math.abs(linkedA - 25) <= 1 && Math.abs(linkedB - 75) <= 1 && linkedReturn === linkedA && readingB > readingA, { linkedA, linkedB, linkedReturn, readingA, readingB });
  await pause(120);
  check('linked_stops_with_scroll', parseInt(q('#linked-percent').textContent) === linkedReturn, linkedReturn);

  await move(pageY(q('.parallax-scene')) - 300);
  const offsetsA = [...document.querySelectorAll('.parallax-layer')].map(layer => new DOMMatrix(getComputedStyle(layer).transform).m42);
  await move(scrollY + 180);
  const offsetsB = [...document.querySelectorAll('.parallax-layer')].map(layer => new DOMMatrix(getComputedStyle(layer).transform).m42);
  const deltas = offsetsB.map((value, index) => Math.round(value - offsetsA[index]));
  check('parallax_distinct_layer_speeds', deltas.every(value => value > 0) && deltas[3] > deltas[2] && deltas[2] > deltas[0], deltas);

  const stickyStart = pageY(q('.sticky-layout')) - parseFloat(getComputedStyle(q('.sticky-card')).top) + 80;
  await move(stickyStart);
  const pinA = q('.sticky-card').getBoundingClientRect().top;
  await move(stickyStart + 180);
  const pinB = q('.sticky-card').getBoundingClientRect().top;
  await move(pageY(q('.sticky-layout')) + q('.sticky-layout').offsetHeight);
  const pinEnd = q('.sticky-card').getBoundingClientRect().top;
  check('sticky_pins_and_releases', Math.abs(pinA - pinB) < 1 && pinEnd < pinA, { pinA, pinB, pinEnd });

  await move(pageY(q('#snap')) - 100);
  q('.snap-dots button:nth-child(2)').click();
  await pause(850);
  const snapMid = q('.snap-window').scrollTop / q('.snap-window').clientHeight;
  check('snap_dot_aligns_full_panel', Math.abs(snapMid - 1) < .01 && q('#snap-count').textContent === '02 / 03', snapMid);
  q('#snap-next').click();
  await pause(850);
  check('snap_next_and_end_state', q('#snap-count').textContent === '03 / 03' && q('#snap-next').disabled, q('#snap-count').textContent);
  q('#snap-prev').click();
  await pause(850);
  check('snap_previous', q('#snap-count').textContent === '02 / 03', q('#snap-count').textContent);

  await move(runwayY('.horizontal-runway', '.horizontal-stage', .25));
  const horizontalA = new DOMMatrix(getComputedStyle(q('.horizontal-track')).transform).m41;
  await move(runwayY('.horizontal-runway', '.horizontal-stage', .75));
  const horizontalB = new DOMMatrix(getComputedStyle(q('.horizontal-track')).transform).m41;
  await move(runwayY('.horizontal-runway', '.horizontal-stage', 1));
  const lastRight = q('.horizontal-card:last-child').getBoundingClientRect().right;
  const viewportRight = q('.horizontal-viewport').getBoundingClientRect().right;
  check('horizontal_moves_and_last_card_reachable', horizontalB < horizontalA && Math.abs(lastRight - viewportRight) < 2 && q('#horizontal-percent').textContent === '100%', { horizontalA, horizontalB, lastRight, viewportRight });
  await move(document.documentElement.scrollHeight);
  check('horizontal_releases_and_reading_completes', q('.page-footer').getBoundingClientRect().bottom <= innerHeight + 1 && q('.reading-track').getAttribute('aria-valuenow') === '100', q('#reading-number').textContent);

  q('#motion-toggle').click();
  await pause(80);
  check('reduced_motion_keeps_all_content', document.documentElement.classList.contains('reduced-motion') && getComputedStyle(q('.horizontal-stage')).position === 'relative' && getComputedStyle(q('.horizontal-track')).flexWrap === 'wrap' && cards.every(card => Number(getComputedStyle(card).opacity) === 1), q('#motion-toggle').textContent);
  q('#motion-toggle').click();
  await move(0);
  check('no_page_horizontal_overflow', document.documentElement.scrollWidth <= innerWidth, { scrollWidth: document.documentElement.scrollWidth, innerWidth });
  return { passed: results.length, results };
})();
