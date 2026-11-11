'use strict';

/** Static-hosting entry point. It deliberately does not load app.js or call /api/*. */
(() => {
  const settings = window.CAMPUSLOOP_PAGES || {};
  const main = document.getElementById('app');
  const dialog = document.getElementById('pages-dialog');
  const header = document.querySelector('body > header');
  const version = document.querySelector('meta[name="campusloop-pages-version"]')?.content || 'preview';
  const reduceMotion = window.matchMedia('(prefers-reduced-motion: reduce)').matches;

  function externalHttpsUrl(value) {
    if (typeof value !== 'string' || !value.trim()) return '';
    try {
      const url = new URL(value);
      if (url.protocol !== 'https:' || url.username || url.password) return '';
      // Avoid accidentally redirecting a showcase back to itself.
      if (url.origin === location.origin) return '';
      return url.href;
    } catch {
      return '';
    }
  }

  const liveAppUrl = externalHttpsUrl(settings.liveAppUrl);
  const repositoryUrl = externalHttpsUrl(settings.repositoryUrl);

  function bindExternalLinks() {
    document.querySelectorAll('[data-repository-link]').forEach(link => {
      if (repositoryUrl) {
        link.href = repositoryUrl;
        link.hidden = false;
      }
    });
    document.querySelectorAll('[data-live-app-link]').forEach(link => {
      if (liveAppUrl) {
        link.href = liveAppUrl;
        link.hidden = false;
      }
    });
  }

  function showAppInfo() {
    if (!dialog.open) dialog.showModal();
  }

  function updateHeaderHeight() {
    document.documentElement.style.setProperty('--pages-header-height', `${header.getBoundingClientRect().height}px`);
  }

  try {
    if (typeof landing !== 'function') throw new Error('Landing-page JavaScript did not load.');
    // Render into an inert template BEFORE inserting it. This prevents the browser
    // from requesting /static/... at the domain root of a /Repository/ project site.
    const template = document.createElement('template');
    template.innerHTML = landing();
    template.content.querySelectorAll('[src^="/static/"]').forEach(element => {
      const source = element.getAttribute('src');
      const relativeUrl = new URL(`.${source}`, document.baseURI);
      relativeUrl.searchParams.set('v', version);
      element.setAttribute('src', relativeUrl.href);
    });
    main.replaceChildren(template.content);

    document.querySelectorAll('[data-pricing-demo]').forEach(updateCampusPricingDemo);

    const footer = document.querySelector('.landing-copyright');
    if (footer) {
      const note = document.createElement('div');
      note.className = 'pages-footer-note';
      note.textContent = 'GitHub Pages project showcase · No live accounts or bookings on this site.';
      if (repositoryUrl) {
        const sourceLink = document.createElement('a');
        sourceLink.href = repositoryUrl;
        sourceLink.textContent = 'View source on GitHub ↗';
        sourceLink.target = '_blank';
        sourceLink.rel = 'noopener noreferrer';
        note.append(sourceLink);
      }
      footer.append(note);
    }

    bindExternalLinks();
    if (liveAppUrl) {
      const startButton = document.querySelector('.landing-header-start');
      startButton.textContent = 'Open live app ↗';
    }
    updateHeaderHeight();
    if ('ResizeObserver' in window) new ResizeObserver(updateHeaderHeight).observe(header);
    else window.addEventListener('resize', updateHeaderHeight);

    // Deep links work when someone shares the pricing/roadmap section directly.
    // Wait for local photos to settle so a late layout shift doesn't hide the section.
    const restoreSection = () => {
      let id;
      try { id = decodeURIComponent(location.hash.slice(1)); } catch { return; }
      const target = document.getElementById(id);
      if (target) target.scrollIntoView({behavior: 'instant', block: 'start'});
    };
    if (location.hash) {
      if (document.readyState === 'complete') restoreSection();
      else window.addEventListener('load', restoreSection, {once: true});
    }
  } catch (error) {
    main.replaceChildren();
    const section = document.createElement('section');
    section.className = 'panel pages-loading';
    const heading = document.createElement('h1');
    heading.textContent = 'CampusLoop could not load.';
    const message = document.createElement('p');
    message.textContent = 'Refresh this page. When deploying, include the root index.html and the static assets listed in GITHUB_PAGES.md.';
    section.append(heading, message);
    main.append(section);
    console.error(error);
  }

  document.addEventListener('click', event => {
    const button = event.target.closest('[data-nav], [data-pages-help], [data-pages-close]');
    if (!button) return;
    if (button.hasAttribute('data-pages-close')) {
      dialog.close();
      return;
    }
    if (button.hasAttribute('data-pages-help')) {
      showAppInfo();
      return;
    }
    if (button.dataset.nav === 'home') {
      event.preventDefault();
      if (/^https?:$/.test(location.protocol)) {
        history.replaceState(null, '', `${location.pathname}${location.search}`);
      }
      window.scrollTo({top: 0, behavior: reduceMotion ? 'instant' : 'smooth'});
      return;
    }
    // Existing landing-page calls to action remain clickable, without showing a
    // broken login form or pretending a real booking has been made on Pages.
    if (liveAppUrl) window.location.assign(liveAppUrl);
    else showAppInfo();
  });

  dialog.addEventListener('click', event => {
    if (event.target !== dialog) return;
    const bounds = dialog.getBoundingClientRect();
    if (event.clientX < bounds.left || event.clientX > bounds.right ||
        event.clientY < bounds.top || event.clientY > bounds.bottom) dialog.close();
  });
})();
