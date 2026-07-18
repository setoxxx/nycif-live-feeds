/**
 * NYC In Focus — tip jar widget (public map + preview).
 */
(function () {
  'use strict';

  const TIP_JAR_LINKS = [
    { id: 'cashapp', label: 'Cash App', emoji: '💵', url: 'https://cash.app/$NYCINFOCUS' },
    { id: 'venmo', label: 'Venmo', emoji: '💙', url: 'https://venmo.com/u/Howie-Doin' },
    { id: 'paypal', label: 'PayPal', emoji: '🅿️', url: 'https://py.pl/oxvv2Mgg0bztfniKXwpQWA' },
  ];

  function esc(value) {
    return String(value ?? '').replace(/[&<>"']/g, ch => ({
      '&': '&amp;',
      '<': '&lt;',
      '>': '&gt;',
      '"': '&quot;',
      "'": '&#39;',
    }[ch]));
  }

  function installStyles() {
    if (document.getElementById('nycif-tip-jar-style')) return;
    const style = document.createElement('style');
    style.id = 'nycif-tip-jar-style';
    style.textContent = `
      .nycif-tip-jar {
        position: fixed;
        top: 12px;
        right: 12px;
        z-index: 1300;
        display: grid;
        justify-items: end;
        gap: 8px;
      }
      .nycif-tip-jar-btn {
        width: 52px;
        height: 52px;
        border: 2px solid rgba(251,191,36,.55);
        border-radius: 999px;
        background: linear-gradient(180deg, rgba(120,53,15,.95), rgba(69,26,3,.95));
        box-shadow: 0 10px 24px rgba(0,0,0,.35);
        cursor: pointer;
        display: grid;
        place-items: center;
        padding: 0;
      }
      .nycif-tip-jar-btn:focus-visible {
        outline: 2px solid #fbbf24;
        outline-offset: 2px;
      }
      .nycif-tip-jar-emoji {
        font-size: 26px;
        line-height: 1;
        transform-origin: 50% 85%;
        display: block;
      }
      .nycif-tip-jar.shake .nycif-tip-jar-emoji {
        animation: nycif-tip-jar-shake 0.55s ease-in-out;
      }
      @keyframes nycif-tip-jar-shake {
        0%, 100% { transform: rotate(0deg) translateY(0); }
        15% { transform: rotate(-14deg) translateY(1px); }
        30% { transform: rotate(12deg) translateY(-1px); }
        45% { transform: rotate(-10deg) translateY(1px); }
        60% { transform: rotate(8deg) translateY(0); }
        75% { transform: rotate(-6deg) translateY(1px); }
      }
      .nycif-tip-jar-panel {
        min-width: 220px;
        padding: 12px;
        border-radius: 14px;
        border: 1px solid rgba(251,191,36,.35);
        background: rgba(17,24,39,.96);
        box-shadow: 0 16px 36px rgba(0,0,0,.35);
        color: #fde68a;
        transform-origin: top right;
      }
      .nycif-tip-jar.is-open .nycif-tip-jar-panel {
        min-width: 252px;
        padding: 14px 14px 16px;
        border-color: rgba(251,191,36,.5);
        box-shadow: 0 20px 44px rgba(0,0,0,.42), 0 0 0 1px rgba(251,191,36,.12);
      }
      .nycif-tip-jar.is-open .nycif-tip-jar-btn {
        transform: scale(1.04);
        border-color: rgba(252,211,77,.75);
      }
      .nycif-tip-jar-btn {
        transition: transform .2s ease, border-color .2s ease;
      }
      .nycif-tip-jar-panel[hidden] { display: none; }
      .nycif-tip-jar-panel h3 {
        margin: 0 0 8px;
        font: 700 12px/1.2 system-ui, -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif;
        color: #fcd34d;
      }
      .nycif-tip-jar.is-open .nycif-tip-jar-panel h3 {
        margin-bottom: 10px;
        font-size: 13px;
      }
      .nycif-tip-jar-panel a {
        display: flex;
        align-items: center;
        gap: 10px;
        padding: 8px 10px;
        margin-top: 6px;
        border-radius: 10px;
        border: 1px solid rgba(255,255,255,.06);
        background: rgba(255,255,255,.05);
        color: #fff7ed;
        text-decoration: none;
        font: 600 13px/1.2 system-ui, -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif;
        transition: background .18s ease, border-color .18s ease, box-shadow .18s ease,
          transform .22s ease, padding .22s ease;
      }
      .nycif-tip-jar.is-open .nycif-tip-jar-panel a {
        gap: 12px;
        padding: 12px 14px;
        margin-top: 8px;
        border-radius: 12px;
        font-size: 15px;
        transform: scale(1);
        animation: nycif-tip-jar-link-pop 0.38s cubic-bezier(0.22, 1, 0.36, 1) both;
      }
      .nycif-tip-jar.is-open .nycif-tip-jar-panel a:nth-child(2) { animation-delay: 0.04s; }
      .nycif-tip-jar.is-open .nycif-tip-jar-panel a:nth-child(3) { animation-delay: 0.12s; }
      .nycif-tip-jar.is-open .nycif-tip-jar-panel a:nth-child(4) { animation-delay: 0.2s; }
      @keyframes nycif-tip-jar-link-pop {
        0% { opacity: 0; transform: scale(0.88) translateY(-6px); }
        100% { opacity: 1; transform: scale(1) translateY(0); }
      }
      .nycif-tip-jar-panel a:hover {
        background: rgba(251,191,36,.12);
      }
      .nycif-tip-jar-panel a.nycif-tip-pay--cashapp:hover {
        border-color: rgba(0,214,50,.45);
        background: rgba(0,214,50,.12);
        box-shadow: inset 3px 0 0 rgba(0,214,50,.75);
      }
      .nycif-tip-jar-panel a.nycif-tip-pay--venmo:hover {
        border-color: rgba(61,149,206,.5);
        background: rgba(61,149,206,.14);
        box-shadow: inset 3px 0 0 rgba(61,149,206,.85);
      }
      .nycif-tip-jar-panel a.nycif-tip-pay--paypal:hover {
        border-color: rgba(0,156,222,.5);
        background: rgba(0,48,135,.22);
        box-shadow: inset 3px 0 0 rgba(0,156,222,.85);
      }
      .nycif-tip-jar-panel .pay-emoji-wrap {
        position: relative;
        flex: 0 0 24px;
        width: 24px;
        height: 24px;
        display: grid;
        place-items: center;
        transition: width .22s ease, height .22s ease, flex-basis .22s ease;
      }
      .nycif-tip-jar.is-open .nycif-tip-jar-panel .pay-emoji-wrap {
        flex: 0 0 36px;
        width: 36px;
        height: 36px;
      }
      .nycif-tip-jar-panel .pay-emoji {
        font-size: 18px;
        line-height: 1;
        display: block;
        transition: font-size .22s ease, transform .22s ease;
      }
      .nycif-tip-jar.is-open .nycif-tip-jar-panel .pay-emoji {
        font-size: 28px;
        transform: scale(1);
      }
      .nycif-tip-jar-panel .pay-heart {
        position: absolute;
        top: -3px;
        right: -5px;
        font-size: 9px;
        line-height: 1;
        color: #fb7185;
        text-shadow: 0 0 6px rgba(251,113,133,.55);
        pointer-events: none;
        opacity: 0;
        transform: scale(0.85);
        transition: font-size .22s ease, top .22s ease, right .22s ease;
      }
      .nycif-tip-jar.is-open .nycif-tip-jar-panel .pay-heart {
        top: -2px;
        right: -4px;
        font-size: 11px;
      }
      .nycif-tip-jar-panel:not([hidden]) .pay-heart {
        opacity: 0.92;
        animation: nycif-tip-jar-heart-pulse 1.6s ease-in-out infinite;
      }
      .nycif-tip-jar-panel:not([hidden]) a:nth-child(2) .pay-heart {
        animation-delay: 0.2s;
      }
      .nycif-tip-jar-panel:not([hidden]) a:nth-child(3) .pay-heart {
        animation-delay: 0.45s;
      }
      .nycif-tip-jar-panel:not([hidden]) a:nth-child(4) .pay-heart {
        animation-delay: 0.7s;
      }
      @keyframes nycif-tip-jar-heart-pulse {
        0%, 100% { transform: scale(0.9); opacity: 0.75; }
        50% { transform: scale(1.08); opacity: 1; }
      }
      @media (prefers-reduced-motion: reduce) {
        .nycif-tip-jar-panel .pay-heart {
          animation: none !important;
          opacity: 0.85;
          transform: none;
        }
        .nycif-tip-jar.is-open .nycif-tip-jar-panel a {
          animation: none;
        }
        .nycif-tip-jar.shake .nycif-tip-jar-emoji {
          animation: none;
        }
      }
    `;
    document.head.appendChild(style);
  }

  function installTipJar() {
    if (document.getElementById('nycifTipJar')) return;

    installStyles();
    const root = document.createElement('div');
    root.id = 'nycifTipJar';
    root.className = 'nycif-tip-jar';
    root.innerHTML = `
      <button type="button" class="nycif-tip-jar-btn" id="nycifTipJarBtn"
        aria-expanded="false" aria-controls="nycifTipJarPanel" aria-label="Open tip jar">
        <span class="nycif-tip-jar-emoji" aria-hidden="true">🫙</span>
      </button>
      <div class="nycif-tip-jar-panel" id="nycifTipJarPanel" hidden>
        <h3>Tip jar — support NYC In Focus</h3>
        ${TIP_JAR_LINKS.map(link => `
          <a class="nycif-tip-pay nycif-tip-pay--${esc(link.id)}" href="${esc(link.url)}"
            target="_blank" rel="noopener noreferrer">
            <span class="pay-emoji-wrap">
              <span class="pay-emoji" aria-hidden="true">${link.emoji}</span>
              <span class="pay-heart" aria-hidden="true">♥</span>
            </span>
            <span class="pay-label">${esc(link.label)}</span>
          </a>
        `).join('')}
      </div>
    `;
    document.body.appendChild(root);

    const button = document.getElementById('nycifTipJarBtn');
    const panel = document.getElementById('nycifTipJarPanel');
    if (!button || !panel) return;

    const setPanelOpen = (open) => {
      panel.hidden = !open;
      button.setAttribute('aria-expanded', String(open));
      root.classList.toggle('is-open', open);
      if (open) root.classList.remove('shake');
    };

    button.addEventListener('click', (event) => {
      event.stopPropagation();
      setPanelOpen(panel.hidden);
    });

    document.addEventListener('click', (event) => {
      if (!root.contains(event.target)) {
        setPanelOpen(false);
      }
    });

    document.addEventListener('keydown', (event) => {
      if (event.key === 'Escape' && !panel.hidden) {
        setPanelOpen(false);
      }
    });

    const scheduleRandomShake = () => {
      const waitMs = 5000 + Math.floor(Math.random() * 9000);
      window.setTimeout(() => {
        if (!panel.hidden) {
          scheduleRandomShake();
          return;
        }
        root.classList.add('shake');
        window.setTimeout(() => root.classList.remove('shake'), 560);
        scheduleRandomShake();
      }, waitMs);
    };
    scheduleRandomShake();
  }

  window.NYCIF_TIP_JAR = {
    VERSION: 'nycif-tip-jar-v03',
    TIP_JAR_LINKS,
    install: installTipJar,
  };

  if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', installTipJar);
  } else {
    installTipJar();
  }
})();
