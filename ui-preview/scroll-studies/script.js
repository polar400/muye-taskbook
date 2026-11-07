'use strict';
(() => {
  const root = document.documentElement;
  const preference = matchMedia('(prefers-reduced-motion: reduce)');
  let reduced = preference.matches;
  let userMotionChoice = false;
  const clamp = value => Math.max(0, Math.min(1, value));
  const $ = selector => document.querySelector(selector);
  const cards = [...document.querySelectorAll('.reveal-card')];
  const chapters = [...document.querySelectorAll('.experiment')];
  const navLinks = [...document.querySelectorAll('.chapter-nav a')];
  const motionButton = $('#motion-toggle');
  const snapWindow = $('.snap-window');
  const snapPages = [...document.querySelectorAll('.snap-page')];
  const snapDots = [...document.querySelectorAll('.snap-dots button')];
  let snapIndex = 0;
  let queued = false;

  function applyMotionPreference() {
    root.classList.toggle('reduced-motion', reduced);
    root.classList.toggle('js-motion', !reduced);
    root.classList.toggle('motion-enabled', !reduced);
    motionButton.setAttribute('aria-pressed', String(reduced));
    motionButton.textContent = reduced ? '开启动效' : '减少动效';
    if (reduced) cards.forEach(card => {
      card.classList.add('revealed');
      card.querySelector('.reveal-state').textContent = '静态展示';
    });
    else cards.filter(card => card.classList.contains('revealed')).forEach(card => {
      card.querySelector('.reveal-state').textContent = '已展示';
    });
    scheduleUpdate();
  }

  // Unobserve on first entry: scrolling back never restarts the animation.
  const revealObserver = new IntersectionObserver(entries => {
    entries.forEach(entry => {
      if (!entry.isIntersecting) return;
      const card = entry.target;
      card.classList.add('revealed');
      card.querySelector('.reveal-state').textContent = reduced ? '静态展示' : '已触发 · 仅一次';
      revealObserver.unobserve(card);
    });
  }, { threshold: 0.18 });
  cards.forEach((card, index) => {
    card.style.setProperty('--delay', `${index * 100}ms`);
    revealObserver.observe(card);
  });

  function runwayProgress(runway, stage) {
    const top = parseFloat(getComputedStyle(stage).top) || 0;
    const rect = runway.getBoundingClientRect();
    return clamp((top - rect.top) / Math.max(1, runway.offsetHeight - stage.offsetHeight));
  }

  function update() {
    queued = false;
    const fullDistance = root.scrollHeight - window.innerHeight;
    const reading = fullDistance > 0 ? clamp(window.scrollY / fullDistance) : 0;
    $('#reading-bar').style.transform = `scaleX(${reading})`;
    const percentage = Math.round(reading * 100);
    $('#reading-number').textContent = `${String(percentage).padStart(2, '0')}%`;
    $('.reading-track').setAttribute('aria-valuenow', percentage);

    const linked = reduced ? 1 : runwayProgress($('.linked-runway'), $('.linked-stage'));
    $('#linked-percent').textContent = `${Math.round(linked * 100)}%`;
    $('#timeline-fill').style.transform = `scaleX(${linked})`;
    $('#timeline-orb').style.left = `${linked * 100}%`;
    $('#linked-square').style.transform = `rotate(${linked * 180}deg) scale(${1 + linked * 0.25})`;

    const scene = $('.parallax-scene').getBoundingClientRect();
    const sceneOffset = window.innerHeight / 2 - (scene.top + scene.height / 2);
    document.querySelectorAll('.parallax-layer').forEach(layer => {
      layer.style.transform = `translateY(${reduced ? 0 : sceneOffset * Number(layer.dataset.speed)}px)`;
    });

    const horizontal = reduced ? 1 : runwayProgress($('.horizontal-runway'), $('.horizontal-stage'));
    const distance = Math.max(0, $('.horizontal-track').scrollWidth - $('.horizontal-viewport').clientWidth);
    $('.horizontal-track').style.transform = `translateX(${-horizontal * distance}px)`;
    $('#horizontal-percent').textContent = `${Math.round(horizontal * 100)}%`;
    $('#horizontal-fill').style.transform = `scaleX(${horizontal})`;

    let active = '';
    chapters.forEach(chapter => {
      if (chapter.getBoundingClientRect().top <= window.innerHeight * 0.42) active = chapter.id;
    });
    if ($('#top').getBoundingClientRect().top > -window.innerHeight * 0.5) active = '';
    navLinks.forEach(link => {
      const current = link.hash === `#${active}`;
      link.classList.toggle('active', current);
      if (current) link.setAttribute('aria-current', 'location');
      else link.removeAttribute('aria-current');
    });
  }

  function scheduleUpdate() {
    if (queued) return;
    queued = true;
    requestAnimationFrame(update);
  }

  function updateSnap() {
    snapIndex = Math.max(0, Math.min(snapPages.length - 1, Math.round(snapWindow.scrollTop / snapWindow.clientHeight)));
    $('#snap-count').textContent = `${String(snapIndex + 1).padStart(2, '0')} / 03`;
    snapDots.forEach((dot, index) => dot.setAttribute('aria-pressed', String(index === snapIndex)));
    $('#snap-prev').disabled = snapIndex === 0;
    $('#snap-next').disabled = snapIndex === snapPages.length - 1;
  }

  function goToSnap(index) {
    const target = Math.max(0, Math.min(snapPages.length - 1, index));
    snapWindow.scrollTo({ top: target * snapWindow.clientHeight, behavior: reduced ? 'instant' : 'smooth' });
  }
  snapDots.forEach((dot, index) => dot.addEventListener('click', () => goToSnap(index)));
  $('#snap-prev').addEventListener('click', () => goToSnap(snapIndex - 1));
  $('#snap-next').addEventListener('click', () => goToSnap(snapIndex + 1));
  snapWindow.addEventListener('scroll', updateSnap, { passive: true });
  motionButton.addEventListener('click', () => {
    userMotionChoice = true;
    reduced = !reduced;
    applyMotionPreference();
  });
  preference.addEventListener('change', event => {
    if (userMotionChoice) return;
    reduced = event.matches;
    applyMotionPreference();
  });
  window.addEventListener('scroll', scheduleUpdate, { passive: true });
  window.addEventListener('resize', () => { scheduleUpdate(); updateSnap(); });
  applyMotionPreference();
  updateSnap();
})();
