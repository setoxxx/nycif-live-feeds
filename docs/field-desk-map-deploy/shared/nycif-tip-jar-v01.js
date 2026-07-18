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

  const SOCIAL_LINKS = [
    {
      id: 'instagram',
      label: 'Instagram — @youfoundhowie',
      url: 'https://www.instagram.com/youfoundhowie/',
      icon: '<svg viewBox="0 0 24 24" aria-hidden="true"><path fill="currentColor" d="M7 2h10a5 5 0 0 1 5 5v10a5 5 0 0 1-5 5H7a5 5 0 0 1-5-5V7a5 5 0 0 1 5-5zm0 2a3 3 0 0 0-3 3v10a3 3 0 0 0 3 3h10a3 3 0 0 0 3-3V7a3 3 0 0 0-3-3H7zm11 1.5a1 1 0 1 1 0 2 1 1 0 0 1 0-2zM12 7a5 5 0 1 1 0 10 5 5 0 0 1 0-10zm0 2a3 3 0 1 0 0 6 3 3 0 0 0 0-6z"/></svg>',
    },
    {
      id: 'tiktok',
      label: 'TikTok — @howardweiss',
      url: 'https://www.tiktok.com/@howardweiss',
      icon: '<svg viewBox="0 0 24 24" aria-hidden="true"><path fill="currentColor" d="M16.5 3h3.1c.2 1.5.9 2.9 2 3.9 1.1 1 2.5 1.6 4 1.7v3.1c-1.6-.1-3.1-.6-4.4-1.5v6.8c0 4-2.9 6.8-6.6 6.8S8 21 8 17s2.9-6.8 6.6-6.8c.4 0 .8 0 1.2.1v3.3a3.4 3.4 0 0 0-1.2-.2c-1.9 0-3.4 1.5-3.4 3.6s1.5 3.6 3.4 3.6 3.4-1.6 3.4-3.8V3z"/></svg>',
    },
    {
      id: 'youtube',
      label: 'YouTube — @youfoundhowie',
      url: 'https://www.youtube.com/@youfoundhowie',
      icon: '<svg viewBox="0 0 24 24" aria-hidden="true"><path fill="currentColor" d="M21.6 7.2a2.5 2.5 0 0 0-1.8-1.8C17.8 5 12 5 12 5s-5.8 0-7.8.4A2.5 2.5 0 0 0 2.4 7.2 26 26 0 0 0 2 12a26 26 0 0 0 .4 4.8 2.5 2.5 0 0 0 1.8 1.8C6.2 19 12 19 12 19s5.8 0 7.8-.4a2.5 2.5 0 0 0 1.8-1.8A26 26 0 0 0 22 12a26 26 0 0 0-.4-4.8zM10 15.5v-7l6 3.5-6 3.5z"/></svg>',
    },
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

  function shareMessage(url) {
    const pageUrl = url || (typeof window !== 'undefined' ? window.location.href : '');
    return `You gotta check this out — NYC In Focus maps what's happening in NYC today and this week: ${pageUrl}`;
  }

  function showToast(message) {
    let toast = document.getElementById('nycifTipJarToast');
    if (!toast) {
      toast = document.createElement('div');
      toast.id = 'nycifTipJarToast';
      toast.className = 'nycif-tip-jar-toast';
      toast.setAttribute('role', 'status');
      toast.setAttribute('aria-live', 'polite');
      document.body.appendChild(toast);
    }
    toast.textContent = message;
    toast.classList.add('is-visible');
    window.clearTimeout(showToast._timer);
    showToast._timer = window.setTimeout(() => toast.classList.remove('is-visible'), 2200);
  }

  async function shareMap() {
    const text = shareMessage();
    if (navigator.share) {
      try {
        await navigator.share({
          title: 'NYC In Focus Event Map',
          text,
          url: window.location.href,
        });
        return;
      } catch (error) {
        if (error && error.name === 'AbortError') return;
      }
    }
    try {
      await navigator.clipboard.writeText(text);
      showToast('Copied — paste into a text!');
    } catch (_error) {
      const smsUrl = `sms:?&body=${encodeURIComponent(text)}`;
      window.location.href = smsUrl;
    }
  }

  function installStyles() {
    if (document.getElementById('nycif-tip-jar-style')) return;
    const style = document.createElement('style');
    style.id = 'nycif-tip-jar-style';
    style.textContent = `
      .nycif-tip-jar {
        position: relative;
        z-index: 1300;
        display: grid;
        justify-items: end;
        gap: 8px;
        flex: 0 0 auto;
      }
      .nycif-tip-jar-btn {
        width: 42px;
        height: 42px;
        border: 2px solid rgba(251,191,36,.55);
        border-radius: 999px;
        background: linear-gradient(180deg, rgba(120,53,15,.95), rgba(69,26,3,.95));
        box-shadow: 0 10px 24px rgba(0,0,0,.35);
        cursor: pointer;
        display: grid;
        place-items: center;
        padding: 0;
        transition: transform .2s ease, border-color .2s ease;
      }
      .nycif-tip-jar-btn:focus-visible {
        outline: 2px solid #fbbf24;
        outline-offset: 2px;
      }
      .nycif-tip-jar-emoji {
        font-size: 22px;
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
        position: absolute;
        top: calc(100% + 8px);
        right: 0;
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
      .nycif-tip-jar-share {
        display: flex;
        align-items: center;
        gap: 10px;
        width: 100%;
        padding: 8px 10px;
        margin-top: 0;
        border-radius: 10px;
        border: 1px solid rgba(255,255,255,.1);
        background: rgba(255,255,255,.08);
        color: #fff7ed;
        font: 600 13px/1.2 system-ui, -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif;
        cursor: pointer;
        text-align: left;
        transition: background .18s ease, border-color .18s ease, transform .22s ease, padding .22s ease;
      }
      .nycif-tip-jar.is-open .nycif-tip-jar-share {
        gap: 12px;
        padding: 12px 14px;
        border-radius: 12px;
        font-size: 15px;
        animation: nycif-tip-jar-link-pop 0.38s cubic-bezier(0.22, 1, 0.36, 1) both;
      }
      .nycif-tip-jar-share:hover {
        background: rgba(251,191,36,.14);
        border-color: rgba(251,191,36,.35);
      }
      .nycif-tip-jar-panel a.nycif-tip-pay {
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
      .nycif-tip-jar.is-open .nycif-tip-jar-panel a.nycif-tip-pay {
        gap: 12px;
        padding: 12px 14px;
        margin-top: 8px;
        border-radius: 12px;
        font-size: 15px;
        transform: scale(1);
        animation: nycif-tip-jar-link-pop 0.38s cubic-bezier(0.22, 1, 0.36, 1) both;
      }
      .nycif-tip-jar.is-open .nycif-tip-pay--cashapp { animation-delay: 0.04s; }
      .nycif-tip-jar.is-open .nycif-tip-pay--venmo { animation-delay: 0.12s; }
      .nycif-tip-jar.is-open .nycif-tip-pay--paypal { animation-delay: 0.2s; }
      @keyframes nycif-tip-jar-link-pop {
        0% { opacity: 0; transform: scale(0.88) translateY(-6px); }
        100% { opacity: 1; transform: scale(1) translateY(0); }
      }
      .nycif-tip-jar-panel a.nycif-tip-pay:hover {
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
      .nycif-tip-jar-social-label {
        margin: 10px 0 6px;
        font: 700 10px/1.2 system-ui, -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif;
        letter-spacing: .04em;
        text-transform: uppercase;
        color: rgba(253,230,138,.75);
      }
      .nycif-tip-jar-social {
        display: flex;
        gap: 8px;
        align-items: center;
      }
      .nycif-tip-jar-social a {
        display: grid;
        place-items: center;
        width: 34px;
        height: 34px;
        border-radius: 999px;
        border: 1px solid rgba(255,255,255,.1);
        background: rgba(255,255,255,.06);
        color: #fde68a;
        text-decoration: none;
        transition: background .18s ease, border-color .18s ease, transform .18s ease;
      }
      .nycif-tip-jar-social a:hover {
        background: rgba(251,191,36,.16);
        border-color: rgba(251,191,36,.35);
        transform: translateY(-1px);
      }
      .nycif-tip-jar-social a svg {
        width: 18px;
        height: 18px;
        display: block;
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
      .nycif-tip-jar-panel:not([hidden]) a.nycif-tip-pay--cashapp .pay-heart {
        animation-delay: 0.2s;
      }
      .nycif-tip-jar-panel:not([hidden]) a.nycif-tip-pay--venmo .pay-heart {
        animation-delay: 0.45s;
      }
      .nycif-tip-jar-panel:not([hidden]) a.nycif-tip-pay--paypal .pay-heart {
        animation-delay: 0.7s;
      }
      @keyframes nycif-tip-jar-heart-pulse {
        0%, 100% { transform: scale(0.9); opacity: 0.75; }
        50% { transform: scale(1.08); opacity: 1; }
      }
      .nycif-tip-jar-toast {
        position: fixed;
        left: 50%;
        bottom: calc(env(safe-area-inset-bottom, 0px) + 72px);
        transform: translateX(-50%) translateY(8px);
        z-index: 1400;
        padding: 10px 14px;
        border-radius: 999px;
        background: rgba(17,24,39,.94);
        color: #fde68a;
        font: 700 12px/1.2 system-ui, -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif;
        box-shadow: 0 12px 28px rgba(0,0,0,.35);
        opacity: 0;
        pointer-events: none;
        transition: opacity .2s ease, transform .2s ease;
      }
      .nycif-tip-jar-toast.is-visible {
        opacity: 1;
        transform: translateX(-50%) translateY(0);
      }
      @media (prefers-reduced-motion: reduce) {
        .nycif-tip-jar-panel .pay-heart {
          animation: none !important;
          opacity: 0.85;
          transform: none;
        }
        .nycif-tip-jar.is-open .nycif-tip-jar-panel a.nycif-tip-pay,
        .nycif-tip-jar.is-open .nycif-tip-jar-share {
          animation: none;
        }
        .nycif-tip-jar.shake .nycif-tip-jar-emoji {
          animation: none;
        }
      }
    `;
    document.head.appendChild(style);
  }

  function mountTarget() {
    return document.querySelector('.brand-header-row')
      || document.querySelector('.brand-card')?.parentElement
      || document.body;
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
        <button type="button" class="nycif-tip-jar-share" id="nycifTipJarShareBtn">
          <span aria-hidden="true">📣</span>
          <span>Share the map</span>
        </button>
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
        <p class="nycif-tip-jar-social-label">Follow Howie</p>
        <div class="nycif-tip-jar-social">
          ${SOCIAL_LINKS.map(link => `
            <a class="nycif-tip-social nycif-tip-social--${esc(link.id)}" href="${esc(link.url)}"
              target="_blank" rel="noopener noreferrer" aria-label="${esc(link.label)}">
              ${link.icon}
            </a>
          `).join('')}
        </div>
      </div>
    `;

    const target = mountTarget();
    if (target.classList?.contains('brand-header-row')) {
      target.appendChild(root);
    } else if (target.querySelector?.('.brand-card')) {
      const header = document.createElement('div');
      header.className = 'brand-header-row';
      header.setAttribute('aria-label', 'NYC In Focus header');
      const brand = target.querySelector('.brand-card');
      brand.parentNode.insertBefore(header, brand);
      header.appendChild(brand);
      header.appendChild(root);
    } else {
      root.style.position = 'fixed';
      root.style.top = '12px';
      root.style.right = '12px';
      document.body.appendChild(root);
    }

    const button = document.getElementById('nycifTipJarBtn');
    const panel = document.getElementById('nycifTipJarPanel');
    const shareBtn = document.getElementById('nycifTipJarShareBtn');
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

    shareBtn?.addEventListener('click', (event) => {
      event.stopPropagation();
      shareMap();
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
    VERSION: 'nycif-tip-jar-v04',
    TIP_JAR_LINKS,
    SOCIAL_LINKS,
    shareMessage,
    shareMap,
    install: installTipJar,
  };

  if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', installTipJar);
  } else {
    installTipJar();
  }
})();
