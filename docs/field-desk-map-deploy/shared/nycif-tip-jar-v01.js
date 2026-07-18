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
      }
      .nycif-tip-jar-panel[hidden] { display: none; }
      .nycif-tip-jar-panel h3 {
        margin: 0 0 8px;
        font: 700 12px/1.2 system-ui, -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif;
        color: #fcd34d;
      }
      .nycif-tip-jar-panel a {
        display: flex;
        align-items: center;
        gap: 8px;
        padding: 8px 10px;
        margin-top: 6px;
        border-radius: 10px;
        background: rgba(255,255,255,.05);
        color: #fff7ed;
        text-decoration: none;
        font: 600 13px/1.2 system-ui, -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif;
      }
      .nycif-tip-jar-panel a:hover {
        background: rgba(251,191,36,.14);
      }
      .nycif-tip-jar-panel .pay-emoji {
        font-size: 18px;
        width: 22px;
        text-align: center;
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
          <a href="${esc(link.url)}" target="_blank" rel="noopener noreferrer">
            <span class="pay-emoji" aria-hidden="true">${link.emoji}</span>
            <span>${esc(link.label)}</span>
          </a>
        `).join('')}
      </div>
    `;
    document.body.appendChild(root);

    const button = document.getElementById('nycifTipJarBtn');
    const panel = document.getElementById('nycifTipJarPanel');
    if (!button || !panel) return;

    button.addEventListener('click', (event) => {
      event.stopPropagation();
      const open = panel.hidden;
      panel.hidden = !open;
      button.setAttribute('aria-expanded', String(open));
      if (open) root.classList.remove('shake');
    });

    document.addEventListener('click', (event) => {
      if (!root.contains(event.target)) {
        panel.hidden = true;
        button.setAttribute('aria-expanded', 'false');
      }
    });

    document.addEventListener('keydown', (event) => {
      if (event.key === 'Escape' && !panel.hidden) {
        panel.hidden = true;
        button.setAttribute('aria-expanded', 'false');
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
    VERSION: 'nycif-tip-jar-v01',
    TIP_JAR_LINKS,
    install: installTipJar,
  };

  if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', installTipJar);
  } else {
    installTipJar();
  }
})();
