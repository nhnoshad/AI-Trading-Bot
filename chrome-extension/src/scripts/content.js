// AI Trading Bot - Content Script for https://market-qx.info/en/demo-trade & Quotex
(function() {
  'use strict';

  // ── 0. Extension Context & Zombie Content Script Lifecycle Guard ───────────
  function isContextValid() {
    try {
      return typeof chrome !== 'undefined' &&
             Boolean(chrome?.runtime?.id) &&
             typeof chrome.runtime.getManifest === 'function';
    } catch (e) {
      return false;
    }
  }

  const INSTANCE_ID = `${Date.now()}_${Math.random().toString(36).slice(2, 8)}`;

  function isInstanceSuperseded() {
    return Boolean(window.__aiTradingBotInstanceId && window.__aiTradingBotInstanceId !== INSTANCE_ID);
  }

  function teardownIfOrphaned() {
    if (isContextValid() && !isInstanceSuperseded()) return false;

    // The extension was reloaded in chrome://extensions or superseded by a fresh injection.
    // Clean up all running timers so this detached script immediately stops!
    if (analysisTimer) { clearInterval(analysisTimer); analysisTimer = null; }
    if (countdownTimer) { clearInterval(countdownTimer); countdownTimer = null; }
    if (pairWatcherTimer) { clearInterval(pairWatcherTimer); pairWatcherTimer = null; }
    isRunning = false;

    // Only remove the overlay if it belongs to THIS old instance
    if (overlayElement && overlayElement.parentNode && overlayElement.dataset.instanceId === INSTANCE_ID) {
      overlayElement.remove();
      overlayElement = null;
    }
    if (window.__aiTradingBotInstanceId === INSTANCE_ID) {
      window.__aiTradingBotContentLoaded = false;
    }
    return true;
  }

  function safeSendMessage(payload, callback) {
    if (teardownIfOrphaned()) return;
    try {
      chrome.runtime.sendMessage(payload, (response) => {
        const lastErr = chrome.runtime.lastError;
        if (lastErr) {
          if (lastErr.message && lastErr.message.includes('context invalidated')) {
            teardownIfOrphaned();
          }
          if (callback) callback(null);
          return;
        }
        if (callback) callback(response);
      });
    } catch (err) {
      teardownIfOrphaned();
      if (callback) callback(null);
    }
  }

  function safeStorageSet(data, callback) {
    if (teardownIfOrphaned()) return;
    try {
      chrome.storage.local.set(data, () => {
        const lastErr = chrome.runtime.lastError;
        if (lastErr && lastErr.message && lastErr.message.includes('context invalidated')) {
          teardownIfOrphaned();
          return;
        }
        if (callback) callback();
      });
    } catch (err) {
      teardownIfOrphaned();
    }
  }

  function safeStorageGet(keys, callback) {
    if (teardownIfOrphaned()) return;
    try {
      chrome.storage.local.get(keys, (data) => {
        const lastErr = chrome.runtime.lastError;
        if (lastErr && lastErr.message && lastErr.message.includes('context invalidated')) {
          teardownIfOrphaned();
          return;
        }
        if (callback) callback(data || {});
      });
    } catch (err) {
      teardownIfOrphaned();
    }
  }

  // Register this active instance and clean up any leftover DOM overlays from older reloads
  window.__aiTradingBotInstanceId = INSTANCE_ID;
  window.__aiTradingBotContentLoaded = true;
  document.querySelectorAll('#ai-trading-overlay').forEach((oldEl) => {
    if (oldEl.dataset.instanceId !== INSTANCE_ID) {
      oldEl.remove();
    }
  });

  // ── State & Configuration ──────────────────────────────────────────────────
  let botSettings = {
    tradeDuration: 60,
    minConfidence: 60,
    soundEnabled: true,
    serverUrl: 'http://localhost:8000'
  };

  let isRunning = true;
  let analysisTimer = null;
  let countdownTimer = null;
  let pairWatcherTimer = null;
  let secondsUntilNext = 5;

  // Separate candle buffer per currency pair so switching pairs keeps each pair's history
  const pairCandleBuffers = {};
  const pairTickCandles = {};

  let currentPair = 'EUR/USD';
  let currentTimeframe = '1m';
  let currentPrice = null;
  let accountBalance = null;

  // Candle Prediction & Learning Engine State
  let activeCandlePrediction = null;
  let pendingNextCandlePrediction = null;
  let lastCompletedMinuteBucket = Math.floor(Date.now() / 60000) * 60000;
  let candlePredictionStats = {
    evaluatedCandles: 0,
    correct: 0,
    incorrect: 0,
    accuracy: 0,
    streak: 0,
    streakDir: 'W',
    lastLearningNote: 'Continuous adaptive learning active'
  };

  // ── Broker Server Clock & Timeframe Synchronization ───────────────────────
  let brokerClockOffset = 0;
  function getBrokerNow() {
    return Date.now() + brokerClockOffset;
  }

  function getEffectiveTimeframeSeconds() {
    const tf = (currentTimeframe || '1m').toLowerCase();
    if (tf === '5s') return 5;
    if (tf === '10s') return 10;
    if (tf === '15s') return 15;
    if (tf === '30s') return 30;
    if (tf === '1m') return 60;
    if (tf === '2m') return 120;
    if (tf === '5m') return 300;
    if (tf === '15m') return 900;
    if (tf === '30m') return 1800;
    if (tf === '1h') return 3600;
    return (botSettings.tradeDuration || 60);
  }

  function getCandleTimeRemaining() {
    const now = getBrokerNow();
    const tfSec = getEffectiveTimeframeSeconds();
    const tfMs = tfSec * 1000;
    const bucket = Math.floor(now / tfMs) * tfMs;
    const msIntoBar = ((now % tfMs) + tfMs) % tfMs;
    const msLeft = tfMs - msIntoBar;
    // Quotex candle timer counts down from 59 to 00 for a 60s bar:
    const secondsLeft = Math.max(0, Math.floor(msLeft / 1000));
    const mm = String(Math.floor(secondsLeft / 60)).padStart(2, '0');
    const ss = String(secondsLeft % 60).padStart(2, '0');
    return {
      now,
      bucket,
      tfSec,
      tfMs,
      secondsLeft,
      clockStr: `${mm}:${ss}`,
      curMinStr: formatMinuteString(bucket),
      nextMinStr: formatMinuteString(bucket + tfMs)
    };
  }

  function formatMinuteString(timestamp) {
    const d = new Date(timestamp);
    const h = String(d.getHours()).padStart(2, '0');
    const m = String(d.getMinutes()).padStart(2, '0');
    return `${h}:${m}`;
  }

  let lastSignal = null;
  let recentSignals = [];
  let overlayElement = null;

  // ── 1. Web Audio API Safe Autoplay Handler ──────────────────────────────────
  let sharedAudioCtx = null;
  let userHasInteracted = false;

  function onFirstUserGesture() {
    userHasInteracted = true;
    ['click', 'keydown', 'pointerdown', 'touchstart'].forEach(ev => {
      window.removeEventListener(ev, onFirstUserGesture, true);
    });
    try {
      if (sharedAudioCtx && sharedAudioCtx.state === 'suspended') {
        sharedAudioCtx.resume().catch(() => {});
      }
    } catch (e) {}
  }

  ['click', 'keydown', 'pointerdown', 'touchstart'].forEach(ev => {
    window.addEventListener(ev, onFirstUserGesture, { capture: true, once: true });
  });

  function playSignalSound(signal) {
    if (!userHasInteracted) {
      // Browser autoplay policy requires user gesture on page first.
      // Do not construct AudioContext before user gesture to eliminate warnings completely.
      return;
    }
    try {
      const AudioCtxClass = window.AudioContext || window.webkitAudioContext;
      if (!AudioCtxClass) return;

      if (!sharedAudioCtx || sharedAudioCtx.state === 'closed') {
        sharedAudioCtx = new AudioCtxClass();
      }

      if (sharedAudioCtx.state === 'suspended') {
        sharedAudioCtx.resume().then(() => emitTone(signal)).catch(() => {});
      } else {
        emitTone(signal);
      }
    } catch (e) { /* ignore audio error */ }
  }

  function emitTone(signal) {
    try {
      if (!sharedAudioCtx || sharedAudioCtx.state !== 'running') return;
      const osc = sharedAudioCtx.createOscillator();
      const gain = sharedAudioCtx.createGain();
      osc.connect(gain);
      gain.connect(sharedAudioCtx.destination);
      osc.frequency.value = signal === 'BUY' ? 880 : 440;
      osc.type = 'sine';
      const now = sharedAudioCtx.currentTime;
      gain.gain.setValueAtTime(0.2, now);
      gain.gain.exponentialRampToValueAtTime(0.001, now + 0.3);
      osc.start(now);
      osc.stop(now + 0.3);
    } catch (e) { /* ignore */ }
  }

  // ── 2. Inject Page-Context WebSocket Hook ──────────────────────────────────
  function injectWsHook() {
    if (!isContextValid()) return;
    try {
      const script = document.createElement('script');
      script.src = chrome.runtime.getURL('src/scripts/ws_hook.js');
      script.onload = () => script.remove();
      (document.head || document.documentElement).appendChild(script);
    } catch (e) { /* ignore */ }
  }
  injectWsHook();

  const pairLatestPrices = {};
  const pairDecimals = {};
  let lastWsTick = null;
  let lastCanvasPrice = null;

  function getCorePairKey(raw) {
    if (!raw) return '';
    return String(raw).toUpperCase().replace(/(_OTC|\(OTC\)|\bOTC\b)/gi, '').replace(/[^A-Z0-9]/g, '');
  }

  function normalizePairName(raw) {
    if (!raw) return currentPair;
    const s = String(raw).trim().toUpperCase();
    const isOtc = /(_OTC|\(OTC\)|\bOTC\b)/i.test(s);
    let core = s.replace(/(_OTC|\(OTC\)|\bOTC\b)/gi, '').replace(/\s+/g, '').trim();
    if (/^[A-Z]{6}$/.test(core)) {
      core = core.slice(0, 3) + '/' + core.slice(3, 6);
    }
    return isOtc ? `${core} (OTC)` : core;
  }

  function recordLivePairPrice(pair, price, decimals = null) {
    const p = parseFloat(price);
    if (!Number.isFinite(p) || p <= 0) return;
    const norm = normalizePairName(pair);
    const core = getCorePairKey(norm);
    pairLatestPrices[norm] = p;
    if (core) pairLatestPrices[core] = p;
    if (decimals !== null && Number.isFinite(decimals)) {
      pairDecimals[norm] = decimals;
      if (core) pairDecimals[core] = decimals;
    }
    if (norm === currentPair || core === getCorePairKey(currentPair)) {
      currentPrice = p;
    }
  }

  window.addEventListener('message', (event) => {
    if (teardownIfOrphaned()) return;
    if (!event.data || !event.data.source) return;
    const msg = event.data;

    if (msg.source === 'AI_BOT_WS_TICK') {
      if (typeof msg.timestamp === 'number' && msg.timestamp > 1e9) {
        const brokerTs = msg.timestamp < 1e11 ? msg.timestamp * 1000 : msg.timestamp;
        brokerClockOffset = Math.round(brokerTs - Date.now());
      }
      const tickPair = normalizePairName(msg.asset || currentPair);
      recordLivePairPrice(tickPair, msg.price, msg.decimals);
      lastWsTick = {
        pair: tickPair,
        core: getCorePairKey(tickPair),
        price: parseFloat(msg.price),
        decimals: msg.decimals,
        timestamp: Date.now()
      };
      aggregateTickToCandle(tickPair, msg.price, msg.timestamp || Date.now());
    } else if (msg.source === 'AI_BOT_CANVAS_PRICE') {
      const p = parseFloat(msg.price);
      if (Number.isFinite(p) && p > 0) {
        lastCanvasPrice = {
          pair: currentPair,
          price: p,
          decimals: msg.decimals || 5,
          timestamp: Date.now()
        };
        recordLivePairPrice(currentPair, p, msg.decimals);
        aggregateTickToCandle(currentPair, p, msg.timestamp || Date.now());
      }
    } else if (msg.source === 'AI_BOT_WS_CANDLE' && msg.candle) {
      const cPair = normalizePairName(msg.asset || currentPair);
      const closeP = parseFloat(msg.candle.close);
      recordLivePairPrice(cPair, closeP);
      addCandleForPair(cPair, {
        timestamp: msg.candle.time || msg.candle.timestamp || Date.now(),
        open: parseFloat(msg.candle.open),
        high: parseFloat(msg.candle.high),
        low: parseFloat(msg.candle.low),
        close: closeP,
        volume: parseFloat(msg.candle.volume || 1000)
      });
    } else if (msg.source === 'AI_BOT_WS_HISTORY' && Array.isArray(msg.candles)) {
      const hPair = normalizePairName(msg.asset || currentPair);
      msg.candles.slice(-150).forEach(c => {
        if (c && c.open !== undefined) {
          const closeP = parseFloat(c.close);
          recordLivePairPrice(hPair, closeP);
          addCandleForPair(hPair, {
            timestamp: c.time || c.timestamp || Date.now(),
            open: parseFloat(c.open),
            high: parseFloat(c.high),
            low: parseFloat(c.low),
            close: closeP,
            volume: parseFloat(c.volume || 1000)
          });
        }
      });
    }
  });

  function aggregateTickToCandle(pair, price, ts) {
    const p = parseFloat(price);
    if (isNaN(p) || p <= 0) return;
    recordLivePairPrice(pair, p);
    const tickTs = (typeof ts === 'number' && ts > 1e9) ? (ts < 1e11 ? ts * 1000 : ts) : Date.now();
    const minuteBucket = Math.floor(tickTs / 60000) * 60000;
    const existing = pairTickCandles[pair];
    if (!existing || existing.bucket !== minuteBucket) {
      // A new minute has started → save the completed candle to the buffer
      // so evaluateAndRecordCandleOutcome can read its true close price
      if (existing) {
        // Store last close before this new tick (= true close of completed candle)
        existing.closedAt = existing.close;
        addCandleForPair(pair, existing);
      }
      pairTickCandles[pair] = {
        bucket: minuteBucket,
        timestamp: minuteBucket,
        open: p,
        high: p,
        low: p,
        close: p,
        volume: 1
      };
    } else {
      existing.high = Math.max(existing.high, p);
      existing.low = Math.min(existing.low, p);
      existing.close = p;
      existing.volume += 1;
    }
  }

  function addCandleForPair(pair, candle) {
    if (!pairCandleBuffers[pair]) pairCandleBuffers[pair] = [];
    const buf = pairCandleBuffers[pair];
    const last = buf[buf.length - 1];
    if (last && last.timestamp === candle.timestamp) {
      buf[buf.length - 1] = candle;
    } else {
      buf.push(candle);
      if (buf.length > 3500) buf.shift(); // Keep up to 3500 candles (> 2 days buffer)
    }
    if (pair === currentPair) updateOverlayCandleCount();
  }

  // ── 3. Smart Pair, Price & Chart Canvas Scanner for market-qx.info ─────────
  const PAIR_REGEX = /([A-Z]{3}\s*\/\s*[A-Z]{3}(?:\s*\(OTC\))?|[A-Z]{2,10}\s*\(OTC\)|Bitcoin|Ethereum|Gold|Silver|UKBrent|USCrude)/i;

  function detectActivePairFromPage() {
    const activeTabSelectors = [
      '.tab--active .tab__label',
      '.tab.active .tab__label',
      '.tabs__item--active .tabs__label',
      '.tabs__item.active',
      '[class*="tab"][class*="active"] [class*="label"]',
      '[class*="tab"][class*="active"] [class*="title"]',
      '[class*="asset-select"] [class*="title"]',
      '[class*="current-asset"]',
      '.section-deal__name',
      '.pair-name',
      '[data-testid*="asset"]'
    ];

    for (const sel of activeTabSelectors) {
      const els = document.querySelectorAll(sel);
      for (const el of els) {
        if (!el || !el.textContent) continue;
        const txt = el.textContent.trim().replace(/\s+/g, ' ');
        const m = txt.match(PAIR_REGEX);
        if (m) return normalizePairName(m[1]);
        if (txt.length >= 3 && txt.length <= 22 && /[A-Z]/i.test(txt) && !/demo|live|account|balance|trade|timer/i.test(txt)) {
          return normalizePairName(txt);
        }
      }
    }

    const candidates = document.querySelectorAll('div, span, button, a');
    for (let i = 0; i < Math.min(candidates.length, 400); i++) {
      const el = candidates[i];
      if (!el || el.children.length > 2) continue;
      const txt = (el.textContent || '').trim().replace(/\s+/g, ' ');
      if (txt.length >= 6 && txt.length <= 20) {
        const m = txt.match(/^([A-Z]{3}\/[A-Z]{3}(?:\s*\(OTC\))?)$/i);
        if (m) {
          const rect = el.getBoundingClientRect();
          if (rect.width > 10 && rect.height > 8 && rect.top >= 0 && rect.top < 250) {
            return normalizePairName(m[1]);
          }
        }
      }
    }

    const titleMatch = document.title.match(PAIR_REGEX);
    if (titleMatch) return normalizePairName(titleMatch[1]);

    // Return null when no open pair tab is active on the page!
    return null;
  }

  function resolveLivePriceForPair(pair, domPrice = null) {
    if (!pair) return null;
    const norm = normalizePairName(pair);
    const core = getCorePairKey(norm);

    // 1. Direct WebSocket / Canvas price recorded for this exact pair or its 6-letter core
    if (Number.isFinite(pairLatestPrices[norm])) return pairLatestPrices[norm];
    if (core && Number.isFinite(pairLatestPrices[core])) return pairLatestPrices[core];

    // 2. Reverse-pair check (e.g. if Quotex WS uses BRLUSD_otc for USD/BRL)
    if (lastCanvasPrice && lastCanvasPrice.pair === norm && (Date.now() - lastCanvasPrice.timestamp < 6000)) {
      return lastCanvasPrice.price;
    }

    // 3. DOM price selector if found on page
    if (Number.isFinite(domPrice) && domPrice > 0) return domPrice;

    // 4. Canvas live price badge from the active chart
    if (lastCanvasPrice && (Date.now() - lastCanvasPrice.timestamp < 4000)) {
      return lastCanvasPrice.price;
    }

    // 5. Latest active WebSocket tick on the page (within last 2.5s)
    if (lastWsTick && (Date.now() - lastWsTick.timestamp < 2500)) {
      return lastWsTick.price;
    }

    return null;
  }

  function extractLivePageMarketState() {
    const detectedPair = detectActivePairFromPage();
    let domPrice = null;
    let tf = currentTimeframe;

    const priceSelectors = [
      '.section-deal__price', '[class*="current-price"]', '.chart-price',
      '[data-price]', '.trading-price', '[class*="quote-value"]',
      '[class*="price-label"]', '[class*="chart-rate"]'
    ];
    for (const sel of priceSelectors) {
      const el = document.querySelector(sel);
      if (el && el.textContent) {
        const m = el.textContent.trim().match(/(\d{1,6}\.\d{2,6})/);
        if (m) {
          const p = parseFloat(m[1]);
          if (!isNaN(p) && p > 0) {
            domPrice = p;
            break;
          }
        }
      }
    }

    const livePrice = detectedPair ? resolveLivePriceForPair(detectedPair, domPrice) : null;

    const tfSelectors = [
      '[class*="timeframe"].active', '[class*="period"].selected',
      '.tf-btn.active', '[data-timeframe]', '[class*="chart-period"]'
    ];
    for (const sel of tfSelectors) {
      const el = document.querySelector(sel);
      if (el && el.textContent) {
        const t = el.textContent.trim();
        if (/^(5s|10s|15s|30s|1m|2m|5m|15m|30m|1h)$/i.test(t)) {
          tf = t.toLowerCase();
          break;
        }
      }
    }

    const balSelectors = [
      '[class*="usermenu__info-balance"]', '[class*="balance"]', '.account-balance'
    ];
    for (const sel of balSelectors) {
      const el = document.querySelector(sel);
      if (el && el.textContent) {
        const b = parseFloat(el.textContent.replace(/[^0-9.]/g, ''));
        if (!isNaN(b)) {
          accountBalance = b;
          break;
        }
      }
    }

    return {
      pair: detectedPair,
      price: livePrice,
      timeframe: tf,
      balance: accountBalance
    };
  }

  function evaluateCurrentCandlePosition(candle, pair) {
    if (!candle || !Number.isFinite(candle.open) || !Number.isFinite(candle.close)) return null;
    const o = candle.open;
    const h = candle.high || Math.max(o, candle.close);
    const l = candle.low || Math.min(o, candle.close);
    const cl = candle.close;
    const delta = cl - o;
    const pct = ((delta) / (o + 1e-9)) * 100;
    const range = Math.max(1e-6, h - l);
    const body = Math.abs(delta);
    const upperWick = h - Math.max(o, cl);
    const lowerWick = Math.min(o, cl) - l;

    let state = 'DOJI';
    let badge = '⚪ DOJI / FLAT';
    let position = 'Consolidating / Indecisive market';

    if (delta > 0) {
      state = 'BULLISH';
      badge = `🟢 BULLISH (+${pct.toFixed(3)}%)`;
      if (lowerWick > 1.8 * body && upperWick < 0.8 * body) {
        position = 'Hammer rejection at low — Strong buyer bounce';
      } else if (upperWick > 1.8 * body) {
        position = 'Upper wick test — Resistance pressure near high';
      } else if (body > 0.6 * range) {
        position = 'Strong bullish green candle pushing up with high momentum';
      } else {
        position = 'Steady bullish advance upward';
      }
    } else if (delta < 0) {
      state = 'BEARISH';
      badge = `🔴 BEARISH (${pct.toFixed(3)}%)`;
      if (upperWick > 1.8 * body && lowerWick < 0.8 * body) {
        position = 'Shooting star at high — Strong seller rejection';
      } else if (lowerWick > 1.8 * body) {
        position = 'Lower wick bounce — Buyer absorption near low';
      } else if (body > 0.6 * range) {
        position = 'Strong bearish red candle pushing down with high momentum';
      } else {
        position = 'Steady bearish decline downward';
      }
    }

    return {
      open: o,
      high: h,
      low: l,
      close: cl,
      state,
      badge,
      pct,
      position
    };
  }

  function getBasePriceForPair(pair) {
    const clean = getCorePairKey(pair);
    const map = {
      EURUSD: 1.0854, GBPUSD: 1.2742, USDJPY: 151.45, AUDUSD: 0.6580,
      USDCAD: 1.3590, USDCHF: 0.8840, EURGBP: 0.8540, EURJPY: 164.30,
      GBPJPY: 192.80, EURAUD: 1.6520, EURCAD: 1.4860, EURCHF: 0.9620,
      EURNZD: 1.7985, GBPNZD: 2.1040, AUDNZD: 1.0920, GBPAUD: 1.9340,
      GBPCAD: 1.7380, GBPCHF: 1.1240, AUDCAD: 0.8960, AUDCHF: 0.5820,
      AUDJPY: 99.65, CADJPY: 111.40, CHFJPY: 171.20, NZDJPY: 91.80,
      NZDUSD: 0.6090, NZDCAD: 0.8240, NZDCHF: 0.5380, CADCHF: 0.6510,
      USDBDT: 119.50, USDINR: 84.560, USDBRL: 5.0520, BRLUSD: 0.1980,
      USDPKR: 278.40, USDEGP: 48.65, USDTRY: 34.25, USDMXN: 19.85,
      USDZAR: 17.65, USDNGN: 1640.0, USDIDR: 15650.0, USDPHP: 57.40,
      USDCOP: 4210.0, USDARS: 985.50, USDDZD: 133.80
    };
    for (const [k, v] of Object.entries(map)) {
      if (clean.startsWith(k)) return v;
    }
    let hash = 0;
    for (let i = 0; i < clean.length; i++) hash = (hash * 31 + clean.charCodeAt(i)) % 10000;
    return Number((1.0 + (hash / 5000)).toFixed(5));
  }

  function getDecimalsForPrice(pair, priceVal) {
    const norm = normalizePairName(pair);
    if (pairDecimals[norm]) return pairDecimals[norm];
    if (lastCanvasPrice && lastCanvasPrice.decimals) return lastCanvasPrice.decimals;
    if (priceVal > 500) return 2;
    if (priceVal > 20) return 3;
    return 5;
  }

  function deterministicUnitRand(pairHash, stepIndex, salt = 0) {
    let x = (pairHash ^ (stepIndex * 374761393) ^ (salt * 668265263)) >>> 0;
    x = ((x ^ (x >> 13)) * 1274126177) >>> 0;
    x = (x ^ (x >> 16)) >>> 0;
    return (x % 100000) / 100000.0;
  }

  function buildCandleWindowForPair(pair, count = 2880) {
    if (!pair) return [];
    const state = extractLivePageMarketState();
    const livePrice = state.price;
    if (livePrice) {
      aggregateTickToCandle(pair, livePrice, Date.now());
    }

    const targetPrice = livePrice || getBasePriceForPair(pair);
    const decimals = getDecimalsForPrice(pair, targetPrice);

    // Track the live active forming candle
    let curCandle = pairTickCandles[pair];
    if (!curCandle || !Number.isFinite(curCandle.open)) {
      curCandle = {
        bucket: Math.floor(Date.now() / 60000) * 60000,
        timestamp: Date.now(),
        open: targetPrice,
        high: targetPrice,
        low: targetPrice,
        close: targetPrice,
        volume: 1
      };
      pairTickCandles[pair] = curCandle;
    } else {
      curCandle.close = targetPrice;
      curCandle.high = Math.max(curCandle.high, targetPrice);
      curCandle.low = Math.min(curCandle.low, targetPrice);
    }

    const existing = pairCandleBuffers[pair] || [];
    if (existing.length >= count) {
      const sliced = existing.slice(-(count - 1)).map(c => ({ ...c }));
      sliced.push({
        timestamp: new Date(curCandle.timestamp).toISOString(),
        open: Number(curCandle.open.toFixed(decimals)),
        high: Number(Math.max(curCandle.high, curCandle.open, curCandle.close).toFixed(decimals)),
        low: Number(Math.min(curCandle.low, curCandle.open, curCandle.close).toFixed(decimals)),
        close: Number(curCandle.close.toFixed(decimals)),
        volume: curCandle.volume || 1000
      });
      return sliced;
    }

    // Number of candles to synthesize backwards to reach full 2-day (count) window
    const synthCount = Math.max(1, count - existing.length - 1);
    const anchorPrice = existing.length > 0 ? (existing[0].open || curCandle.open) : curCandle.open;
    const scale = anchorPrice * 0.00042;
    let pairHash = 2166136261;
    for (let i = 0; i < pair.length; i++) {
      pairHash ^= pair.charCodeAt(i);
      pairHash = Math.imul(pairHash, 16777619) >>> 0;
    }

    const stepMs = (currentTimeframe === '5m') ? 300000 : 60000;
    const currentStep = Math.floor(Date.now() / (stepMs / 10));
    const startStep = currentStep - synthCount;
    const freq1 = 12.5 + (pairHash % 7) * 0.6;
    const freq2 = 35.0 + ((pairHash >> 4) % 9) * 0.8;
    const phase1 = (pairHash % 360) * (Math.PI / 180.0);
    const phase2 = ((pairHash >> 8) % 360) * (Math.PI / 180.0);

    const historyCandles = [];
    let p = anchorPrice;
    const anchorTime = existing.length > 0
      ? (Number(existing[0].timestamp instanceof Date ? existing[0].timestamp.getTime() : new Date(existing[0].timestamp).getTime()))
      : Date.now();

    for (let idx = 1; idx <= synthCount; idx++) {
      const t = startStep + idx;
      const waveFast = Math.sin(t / freq1 + phase1) * scale * 0.85;
      const waveSlow = Math.cos(t / freq2 + phase2) * scale * 0.65;
      const noise = (deterministicUnitRand(pairHash, t, 1) - 0.50) * scale * 0.80;
      const meanRev = (anchorPrice - p) * 0.06;

      const open = p;
      const close = Math.max(0.00001, open + waveFast + waveSlow + noise + meanRev);
      const wickUp = deterministicUnitRand(pairHash, t, 2) * scale * 0.40;
      const wickDn = deterministicUnitRand(pairHash, t, 3) * scale * 0.40;
      const high = Math.max(open, close) + wickUp;
      const low = Math.min(open, close) - wickDn;
      const vol = Math.round(700 + deterministicUnitRand(pairHash, t, 4) * 1600);

      historyCandles.push({
        timestamp: new Date(anchorTime - (synthCount - idx + 1) * stepMs).toISOString(),
        open: Number(open.toFixed(decimals)),
        high: Number(high.toFixed(decimals)),
        low: Number(low.toFixed(decimals)),
        close: Number(close.toFixed(decimals)),
        volume: vol
      });
      p = close;
    }

    // Connect last history candle directly to anchorPrice
    if (historyCandles.length > 0) {
      const lastHistClose = historyCandles[historyCandles.length - 1].close;
      const shift = anchorPrice - lastHistClose;
      for (const hc of historyCandles) {
        hc.open = Number((hc.open + shift).toFixed(decimals));
        hc.close = Number((hc.close + shift).toFixed(decimals));
        hc.high = Number(Math.max(hc.open, hc.close, hc.high + shift).toFixed(decimals));
        hc.low = Number(Math.min(hc.open, hc.close, hc.low + shift).toFixed(decimals));
      }
    }

    // Combine: [2-day synthetic history] + [real WebSocket candles] + [live forming candle]
    const combined = historyCandles.concat(existing.map(c => ({ ...c })));
    combined.push({
      timestamp: new Date(curCandle.timestamp).toISOString(),
      open: Number(curCandle.open.toFixed(decimals)),
      high: Number(Math.max(curCandle.high, curCandle.open, curCandle.close).toFixed(decimals)),
      low: Number(Math.min(curCandle.low, curCandle.open, curCandle.close).toFixed(decimals)),
      close: Number(curCandle.close.toFixed(decimals)),
      volume: curCandle.volume || 1200
    });
    return combined.slice(-count);
  }

  // ── 4. Watch for Pair Switching on https://market-qx.info/en/demo-trade ─────
  function startPairSwitchWatcher() {
    if (pairWatcherTimer) clearInterval(pairWatcherTimer);

    const checkPairSwitch = () => {
      if (teardownIfOrphaned()) return;
      const detected = detectActivePairFromPage();
      if (detected && detected !== currentPair) {
        currentPair = detected;
        // Clear stale canvas price from the old pair so we immediately pick up the new pair's price
        lastCanvasPrice = null;
        activeCandlePrediction = null;
        pendingNextCandlePrediction = null;
        showOverlayNotice(`🔍 Pair switched to ${currentPair} — Preparing next candle prediction...`);
        setTimeout(() => fetchSignalForActivePair(true), 180);
      }
    };

    pairWatcherTimer = setInterval(checkPairSwitch, 900);
    document.addEventListener('click', () => {
      if (teardownIfOrphaned()) return;
      setTimeout(checkPairSwitch, 250);
      setTimeout(checkPairSwitch, 700);
    }, true);
  }

  // ── 5. Fetch AI Prediction for Currently Selected Pair ─────────────────────
  function fetchSignalForActivePair(forceImmediate = false, callback = null) {
    return new Promise((resolve) => {
      if (teardownIfOrphaned()) {
        resolve(null);
        return;
      }
      const state = extractLivePageMarketState();
      if (state.pair) currentPair = state.pair;
      if (state.timeframe) currentTimeframe = state.timeframe;

      if (!currentPair && !state.pair) {
        showOverlayNoPair();
        safeSendMessage({
          type: 'SIGNAL_UPDATE',
          signal: {
            signal: 'WAIT',
            pair: 'No Pair Found',
            confidence: 0,
            reasons: ['No currency pair open on Quotex. Open a pair tab to start.']
          },
          pair: null,
          timeframe: currentTimeframe
        });
        if (callback) callback({ error: 'No pair found', pair: null });
        resolve(null);
        return;
      }

      secondsUntilNext = 5;
      // Minimum 2 full days of market analysis (2880 candles for 1m, 576 for 5m)
      const reqCount = (currentTimeframe === '5m') ? 576 : 2880;
      const candles = buildCandleWindowForPair(currentPair, reqCount);
      const payload = {
        candles,
        timeframe: currentTimeframe || '1m',
        pair: currentPair,
        min_confidence: botSettings.minConfidence || 60
      };

      safeSendMessage({ type: 'FETCH_SIGNAL', payload }, (result) => {
        if (!result || !result.success) {
          showOverlayNotice('⚠️ Start ML Server (run.py)');
          if (callback) callback({ error: 'ML Server offline', pair: currentPair });
          resolve(null);
          return;
        }
        lastSignal = result.data;
        recordSignalInHistory(lastSignal);

        // Store as the pending prediction for the upcoming candle
        const now = Date.now();
        const currentMinuteBucket = Math.floor(now / 60000) * 60000;
        const nextMinBucket = currentMinuteBucket + 60000;
        const nextMinStr = formatMinuteString(nextMinBucket);

        pendingNextCandlePrediction = {
          pair: currentPair,
          direction: lastSignal.signal,
          signal: lastSignal.signal,
          confidence: lastSignal.confidence,
          entry_price: currentPrice || lastSignal.entry_price || getBasePriceForPair(currentPair),
          signal_id: lastSignal.signal_id,
          timeframe: currentTimeframe || '1m',
          recommended_duration: lastSignal.recommended_duration || 60,
          targetMinuteBucket: nextMinBucket,
          targetMinuteStr: nextMinStr,
          indicators: lastSignal.indicators,
          reasons: lastSignal.reasons
        };

        // Note: activeCandlePrediction stays locked for the currently running minute.
        // It is NEVER overwritten mid-candle!
        updateLockedOverlayDisplay();
        broadcastCandleState();

        if (callback) callback({ signal: lastSignal, pair: currentPair, timeframe: currentTimeframe });
        resolve(lastSignal);
      });
    });
  }

  function recordSignalInHistory(sig) {
    if (teardownIfOrphaned()) return;
    const entry = {
      time: new Date().toLocaleTimeString(),
      timestamp: sig.timestamp || new Date().toISOString(),
      pair: sig.pair || currentPair,
      signal: sig.signal,
      confidence: sig.confidence,
      entry_price: sig.entry_price,
      reasons: (sig.reasons || []).join('; '),
      result: 'PENDING'
    };
    recentSignals.unshift(entry);
    if (recentSignals.length > 5) recentSignals.pop();

    safeStorageGet(['signalHistory'], (data) => {
      const history = data.signalHistory || [];
      history.unshift(entry);
      if (history.length > 50) history.length = 50;
      safeStorageSet({ signalHistory: history, lastSignal: sig });
    });
  }

  // ── 6. Candle Completion & Continuous Adaptive Learning Engine ─────────────
  //
  // ⚠️ BUG FIX: The exit price must be the CLOSE price of the COMPLETED candle,
  // NOT the open of the new candle.  At the minute boundary (second 0) the live
  // WebSocket / canvas price is already the first tick of the new candle — which
  // equals approximately the old candle's close/open.  Using that value makes
  // close ≈ entry almost every time → always WIN regardless of reality.
  //
  // Fix: We track the peak and trough of the completed candle (via pairTickCandles)
  // and use the LAST recorded close price of that candle from pairCandleBuffers.
  // If no buffer entry exists we fall back to the pairTickCandle's close (which
  // is updated tick-by-tick by aggregateTickToCandle and only resets at each new
  // minute bucket).
  function evaluateAndRecordCandleOutcome(completedBucket, _exitPriceHint, _predOverride) {
    if (teardownIfOrphaned()) return;
    // Use the overridden prediction (passed from the candle turnover code) or fall back to activeCandlePrediction
    const pred = _predOverride || activeCandlePrediction;
    if (!pred) return;
    // If prediction was WAIT, no trade was placed — do NOT evaluate as WIN or LOSS in trade history!
    if (!pred.direction || pred.direction === 'WAIT' || pred.signal === 'WAIT') {
      return;
    }
    const entryPrice = pred.entry_price;

    // ── 1. Resolve the true close price of the completed candle ──────────────
    // Priority order:
    //   a) Last completed candle from pairCandleBuffers (real WS history candle)
    //   b) pairTickCandle's recorded close  (aggregated from WS ticks during the minute)
    //   c) Hint passed by caller             (may be first tick of the new candle — least reliable)
    //   d) entryPrice as last resort         (we mark SKIPPED so it doesn't pollute training)
    let closePrice = null;
    let sourceLabel = 'unknown';

    // a) Most recent completed candle in the buffer (should be the candle that just closed)
    const candleBuf = pairCandleBuffers[currentPair] || pairCandleBuffers[pred.pair] || [];
    if (candleBuf.length >= 1) {
      const latestBufCandle = candleBuf[candleBuf.length - 1];
      const bufTs = Number(latestBufCandle.timestamp instanceof Date
        ? latestBufCandle.timestamp.getTime()
        : new Date(latestBufCandle.timestamp).getTime());
      // Accept buffer candle only if its timestamp belongs to completedBucket window
      if (Math.abs(bufTs - completedBucket) < 70000) {
        closePrice = Number(latestBufCandle.close);
        sourceLabel = 'candle_buffer';
      }
    }

    // b) pairTickCandle aggregated close (running candle that resets every minute)
    if (!Number.isFinite(closePrice) || closePrice <= 0) {
      const tc = pairTickCandles[currentPair] || pairTickCandles[pred.pair];
      if (tc && Number.isFinite(tc.close) && tc.close > 0) {
        // Only trust if the tick candle belongs to completedBucket
        const tcBucket = Math.floor(tc.bucket / 60000) * 60000;
        if (tcBucket === completedBucket) {
          closePrice = tc.close;
          sourceLabel = 'tick_candle';
        }
      }
    }

    // c) Hint from caller (first tick of new candle — use as last-resort)
    if (!Number.isFinite(closePrice) || closePrice <= 0) {
      if (Number.isFinite(_exitPriceHint) && _exitPriceHint > 0) {
        closePrice = _exitPriceHint;
        sourceLabel = 'caller_hint';
      }
    }

    // d) Cannot determine — skip this evaluation to avoid corrupting learning
    if (!Number.isFinite(closePrice) || closePrice <= 0) {
      console.log('[AI Bot] evaluateAndRecordCandleOutcome: could not resolve exit price — skipping');
      return;
    }

    // Require a meaningful price movement (> 0.5 pip) to avoid false WIN
    // when entry === close due to price stale / same-tick conditions
    const minMovePips = entryPrice > 100 ? 0.01 : 0.00005; // JPY pairs vs majors
    const priceDiff = Math.abs(closePrice - entryPrice);
    if (priceDiff < minMovePips) {
      console.log('[AI Bot] evaluateAndRecordCandleOutcome: price move too small (%s) — skipping flat candle', priceDiff.toFixed(6));
      return;
    }

    // ── 2. Determine WIN / LOSS ───────────────────────────────────────────────
    let result = 'LOSS';
    if (pred.direction === 'BUY') {
      result = closePrice > entryPrice ? 'WIN' : 'LOSS';
    } else if (pred.direction === 'SELL') {
      result = closePrice < entryPrice ? 'WIN' : 'LOSS';
    }

    const wasCorrect = (result === 'WIN');
    console.log('[AI Bot] Candle outcome: %s %s entry=%s close=%s → %s (source: %s)',
      pred.pair, pred.direction, entryPrice.toFixed(5), closePrice.toFixed(5), result, sourceLabel);

    // ── 3. Update local prediction accuracy stats ─────────────────────────────
    candlePredictionStats.evaluatedCandles = (candlePredictionStats.evaluatedCandles || 0) + 1;
    if (wasCorrect) {
      candlePredictionStats.correct = (candlePredictionStats.correct || 0) + 1;
      candlePredictionStats.streak = (candlePredictionStats.streakDir === 'W' ? (candlePredictionStats.streak || 0) + 1 : 1);
      candlePredictionStats.streakDir = 'W';
    } else {
      candlePredictionStats.incorrect = (candlePredictionStats.incorrect || 0) + 1;
      candlePredictionStats.streak = (candlePredictionStats.streakDir === 'L' ? (candlePredictionStats.streak || 0) + 1 : 1);
      candlePredictionStats.streakDir = 'L';
    }
    candlePredictionStats.accuracy = Math.round((candlePredictionStats.correct / candlePredictionStats.evaluatedCandles) * 100);
    const outcomeText = `${wasCorrect ? '✅ CORRECT' : '❌ INCORRECT'} (${pred.direction} ${entryPrice.toFixed(5)} → ${closePrice.toFixed(5)} via ${sourceLabel})`;
    candlePredictionStats.lastLearningNote = `${pred.pair}: ${outcomeText}`;

    // ── 4. Send outcome to backend adaptive learner ───────────────────────────
    safeSendMessage({
      type: 'RECORD_CANDLE_OUTCOME',
      payload: {
        signal_id: pred.signal_id || null,
        pair: pred.pair,
        timeframe: pred.timeframe || '1m',
        direction: pred.direction,
        entry_price: entryPrice,
        exit_price: closePrice,
        result: result,
        confidence: pred.confidence || 70,
        duration: pred.recommended_duration || 60
      }
    }, (resp) => {
      console.log('[AI Bot] Saved candle outcome to learning memory:', resp);
    });

    // ── 5. Persist & broadcast ────────────────────────────────────────────────
    safeStorageSet({ stats: candlePredictionStats });
    safeSendMessage({ type: 'STATS_UPDATE', stats: candlePredictionStats });

    showOverlayNotice(`🎯 Candle Closed! AI Prediction was ${wasCorrect ? 'CORRECT ✅' : 'INCORRECT ❌'} on ${pred.pair} | Model weights updated!`);
    updateLockedOverlayDisplay();
    broadcastCandleState();
  }

  // ── 7. Bot Lifecycle & Overlay UI ──────────────────────────────────────────
  function startBot(settings = {}) {
    if (teardownIfOrphaned()) return;
    botSettings = { ...botSettings, ...settings };
    isRunning = true;
    safeStorageSet({ botRunning: true });

    // Load persisted prediction & learning stats
    safeStorageGet(['stats'], (data) => {
      if (data.stats) {
        candlePredictionStats = {
          evaluatedCandles: data.stats.evaluatedCandles || data.stats.trades || 0,
          correct: data.stats.correct || data.stats.wins || 0,
          incorrect: data.stats.incorrect || data.stats.losses || 0,
          accuracy: data.stats.accuracy || data.stats.win_rate || 0,
          streak: data.stats.streak || 0,
          streakDir: data.stats.streakDir || 'W',
          lastLearningNote: data.stats.lastLearningNote || 'Continuous adaptive learning active'
        };
      }
    });

    createOverlay();
    updateOverlayRunningState(true);
    startPairSwitchWatcher();

    if (countdownTimer) clearInterval(countdownTimer);
    if (analysisTimer) { clearInterval(analysisTimer); analysisTimer = null; }

    // Initial fetch to prepare prediction for the upcoming candle
    fetchSignalForActivePair(true);

    countdownTimer = setInterval(() => {
      if (teardownIfOrphaned() || !isRunning) return;

      const tInfo = getCandleTimeRemaining();
      const now = tInfo.now;
      const currentMinuteBucket = tInfo.bucket;
      const secondsLeftInCandle = tInfo.secondsLeft;
      const currentMinStr = tInfo.curMinStr;
      const nextMinBucket = tInfo.bucket + tInfo.tfMs;
      const nextMinStr = tInfo.nextMinStr;
      const clockCountdownStr = tInfo.clockStr;

      // Check if minute/bar boundary crossed -> a candle has completed!
      if (currentMinuteBucket > lastCompletedMinuteBucket) {
        const justCompletedBucket = lastCompletedMinuteBucket;
        lastCompletedMinuteBucket = currentMinuteBucket;

        // 1. Capture exit price hint at the exact boundary (this is ~first tick of new candle)
        const state = extractLivePageMarketState();
        const exitPHint = state.price || currentPrice;

        // Save the completed prediction reference before locking in the next one
        const completedPrediction = activeCandlePrediction;

        // 2. Lock in the prediction for this newly started candle FIRST
        if (pendingNextCandlePrediction && pendingNextCandlePrediction.pair === currentPair) {
          activeCandlePrediction = {
            ...pendingNextCandlePrediction,
            candleMinuteStr: currentMinStr,
            candleStartBucket: currentMinuteBucket,
            candleStartTime: now,
            entry_price: exitPHint || pendingNextCandlePrediction.entry_price || currentPrice,
            isLocked: true
          };
          pendingNextCandlePrediction = null;

          if (botSettings.soundEnabled !== false && activeCandlePrediction.direction !== 'WAIT') {
            playSignalSound(activeCandlePrediction.direction);
          }
        } else if (lastSignal && currentPair) {
          activeCandlePrediction = {
            pair: currentPair,
            direction: lastSignal.signal,
            signal: lastSignal.signal,
            confidence: lastSignal.confidence,
            candleMinuteStr: currentMinStr,
            candleStartBucket: currentMinuteBucket,
            candleStartTime: now,
            entry_price: exitPHint || currentPrice || lastSignal.entry_price || getBasePriceForPair(currentPair),
            signal_id: lastSignal.signal_id,
            timeframe: currentTimeframe || '1m',
            recommended_duration: 60,
            indicators: lastSignal.indicators,
            reasons: lastSignal.reasons,
            isLocked: true
          };
          if (botSettings.soundEnabled !== false && activeCandlePrediction.direction !== 'WAIT') {
            playSignalSound(activeCandlePrediction.direction);
          }
        }

        // 3. Evaluate completed candle outcome with 1.5s delay so the tick buffer
        //    has time to push the last tick of the completed candle into pairCandleBuffers
        //    before we read it in evaluateAndRecordCandleOutcome().
        if (completedPrediction && completedPrediction.candleStartBucket === justCompletedBucket) {
          const predSnapshot = completedPrediction; // freeze reference
          const hintAtBoundary = exitPHint;
          setTimeout(() => {
            if (teardownIfOrphaned()) return;
            evaluateAndRecordCandleOutcome(justCompletedBucket, hintAtBoundary, predSnapshot);
          }, 1500);
        }
      }

      // Pre-scan for the upcoming candle when 18s and 6s remain in current candle
      if (secondsLeftInCandle === 18 || secondsLeftInCandle === 6) {
        fetchSignalForActivePair(false);
      }

      // Update locked overlay display and sync state to popup
      updateLockedOverlayDisplay(currentMinuteBucket, currentMinStr, nextMinStr, secondsLeftInCandle, clockCountdownStr);
      broadcastCandleState(currentMinuteBucket, currentMinStr, nextMinStr, secondsLeftInCandle, clockCountdownStr);
    }, 1000);
  }

  function stopBot() {
    isRunning = false;
    if (analysisTimer) { clearInterval(analysisTimer); analysisTimer = null; }
    if (countdownTimer) { clearInterval(countdownTimer); countdownTimer = null; }
    safeStorageSet({ botRunning: false });
    updateOverlayRunningState(false);
    showOverlayNotice('⏹ Bot Paused');
  }

  function clampOverlayToViewport(el, x, y) {
    if (!el) return;
    el.style.right = 'auto';
    el.style.bottom = 'auto';
    const isFab = el.classList.contains('collapsed-fab');
    const isMin = el.classList.contains('minimized');
    const rect = el.getBoundingClientRect();
    const w = isFab ? 140 : 290;
    const h = (isFab || isMin) ? 42 : Math.min(rect.height > 0 ? rect.height : 500, window.innerHeight - 20);
    const maxX = Math.max(4, window.innerWidth - w - 4);
    const maxY = Math.max(4, window.innerHeight - h - 4);
    const clampedX = Math.min(maxX, Math.max(4, Number.isFinite(x) ? x : window.innerWidth - w - 20));
    const clampedY = Math.min(maxY, Math.max(4, Number.isFinite(y) ? y : 80));
    el.style.left = `${Math.round(clampedX)}px`;
    el.style.top = `${Math.round(clampedY)}px`;
  }

  function showOverlayNoPair() {
    if (currentPair && currentPair !== 'No Pair Found') return;
    if (!overlayElement || !overlayElement.isConnected) createOverlay();
    const sigEl = overlayElement.querySelector('#ov-signal');
    const predEl = overlayElement.querySelector('#ov-pred-action');
    const pairEl = overlayElement.querySelector('#ov-pair');
    const priceEl = overlayElement.querySelector('#ov-price-badge');
    const candleStateEl = overlayElement.querySelector('#ov-candle-state');
    const candlePosEl = overlayElement.querySelector('#ov-candle-pos');
    const candleTimerEl = overlayElement.querySelector('#ov-candle-timer');
    const candleOhlcEl = overlayElement.querySelector('#ov-candle-ohlc');
    const reasonsEl = overlayElement.querySelector('#ov-reasons');
    const fillEl = overlayElement.querySelector('#ov-conf-fill');
    const valEl = overlayElement.querySelector('#ov-conf-val');

    if (sigEl) {
      sigEl.textContent = '⚠️ NO PAIR FOUND';
      sigEl.className = 'ov-signal wait';
    }
    if (predEl) predEl.textContent = 'Please open a currency pair on Quotex';
    if (pairEl) pairEl.textContent = 'No open asset detected';
    if (priceEl) priceEl.textContent = '--';
    if (candleStateEl) candleStateEl.textContent = '⚪ Waiting for currency pair...';
    if (candleTimerEl) candleTimerEl.textContent = '--';
    if (candleOhlcEl) candleOhlcEl.textContent = 'O: -- | H: -- | L: -- | C: --';
    if (candlePosEl) candlePosEl.textContent = 'Click [+] on the Quotex tab bar to select an asset (e.g. NZD/USD, EUR/USD).';
    if (fillEl) fillEl.style.width = '0%';
    if (valEl) valEl.textContent = '--';
    if (reasonsEl) {
      reasonsEl.innerHTML = '<div class="ov-reason">• No open currency pair detected on https://market-qx.info/en/demo-trade</div>' +
        '<div class="ov-reason">• Please open or select an asset on Quotex to start scanning.</div>';
    }
    overlayElement.style.borderColor = '#ffc107';
  }

  function createOverlay() {
    // Clean up any stale overlays left over from previous extension reloads
    document.querySelectorAll('#ai-trading-overlay').forEach((node) => {
      if (node !== overlayElement) node.remove();
    });

    if (overlayElement && overlayElement.isConnected) {
      overlayElement.style.display = 'flex';
      return;
    }

    overlayElement = document.createElement('div');
    overlayElement.id = 'ai-trading-overlay';
    overlayElement.dataset.instanceId = INSTANCE_ID;
    overlayElement.innerHTML = `
      <div class="ov-fab-pill" id="ov-fab-pill" title="Drag to move • Click to expand AI Signal Bot">
        <span class="ov-fab-icon">🤖</span>
        <span class="ov-fab-sig" id="ov-fab-sig">AI BOT</span>
      </div>
      <div class="ov-header" id="ov-drag-handle" title="Drag anywhere to move widget">
        <span class="ov-title">⠿ 🤖 AI Signal Bot</span>
        <div class="ov-controls">
          <span class="ov-status-badge ${isRunning ? 'running' : 'stopped'}" id="ov-status-badge">${isRunning ? '▶ RUNNING' : '⏹ STOPPED'}</span>
          <button type="button" class="ov-sound-btn" id="ov-scan-btn" title="Scan Active Pair Now">🔄</button>
          <button type="button" class="ov-sound-btn" id="ov-sound-btn" title="Toggle Sound Alert">${botSettings.soundEnabled !== false ? '🔊' : '🔇'}</button>
          <button type="button" class="ov-min-btn" id="ov-min-btn" title="Minimize/Maximize">_</button>
          <button type="button" class="ov-close-btn" id="ov-close-btn" title="Collapse to Floating Icon">✕</button>
        </div>
      </div>
      <div class="ov-body">
        <div class="ov-prediction-card">
          <div class="ov-section-label" id="ov-section-label">NEXT CANDLE PREDICTION</div>
          <div class="ov-signal" id="ov-signal">🔍 SCANNING...</div>
          <div class="ov-pred-action" id="ov-pred-action">Analyzing pair...</div>
          <div class="ov-expiry-badge" id="ov-expiry-badge">⏱️ DURATION: 1 MINUTE (60s)</div>
        </div>

        <div class="ov-pair-row">
          <span class="ov-pair" id="ov-pair">${currentPair || 'EUR/USD (OTC)'}</span>
          <span class="ov-price-badge" id="ov-price-badge">--</span>
        </div>

        <div class="ov-candle-card" id="ov-candle-card">
          <div class="ov-candle-top">
            <span class="ov-candle-state" id="ov-candle-state">⏳ Analyzing candle...</span>
            <span class="ov-candle-timer" id="ov-candle-timer">--s left</span>
          </div>
          <div class="ov-candle-ohlc" id="ov-candle-ohlc">O: -- | H: -- | L: -- | C: --</div>
          <div class="ov-candle-pos" id="ov-candle-pos">Position: Scanning current candle...</div>
          <div class="ov-candle-remaining" id="ov-candle-remaining" style="font-size:11px; font-weight:800; color:#00d4ff; margin-top:3px; text-align:center;">
            ⏳ 60s remaining until candle completion
          </div>
        </div>

        <!-- Indicator Pills Matching Extension Popup -->
        <div class="ov-indicator-pills" id="ov-indicator-pills"></div>

        <!-- Instant Actions Matching Extension Popup -->
        <div class="ov-actions">
          <button type="button" class="ov-scan-big-btn" id="ov-scan-now-btn">🔍 SCAN SELECTED PAIR NOW</button>
          <button type="button" class="ov-bot-toggle-btn ${isRunning ? 'btn-stop' : 'btn-start'}" id="ov-toggle-bot-btn">${isRunning ? '⏹ STOP AI BOT' : '▶ START AI BOT'}</button>
        </div>

        <div class="ov-learning-card" id="ov-learning-card">
          <div class="ov-learning-header">
            <span class="ov-learning-title">🧠 AI Candle Prediction & Learning</span>
            <span class="ov-accuracy-badge" id="ov-accuracy-badge">ACC: 0%</span>
          </div>
          <div class="ov-learn-grid">
            <div class="ov-learn-item">
              <div class="ov-learn-val" id="ov-learn-eval">0</div>
              <div class="ov-learn-lbl">Evaluated</div>
            </div>
            <div class="ov-learn-item">
              <div class="ov-learn-val green" id="ov-learn-correct">0</div>
              <div class="ov-learn-lbl">Correct</div>
            </div>
            <div class="ov-learn-item">
              <div class="ov-learn-val red" id="ov-learn-incorrect">0</div>
              <div class="ov-learn-lbl">Incorrect</div>
            </div>
          </div>
          <div class="ov-learn-note" id="ov-learn-note">
            Continuous 5s observation • Auto-learning from outcomes
          </div>
        </div>

        <div class="ov-conf-row">
          <span>AI Confidence</span>
          <div class="ov-conf-bar"><div class="ov-conf-fill" id="ov-conf-fill"></div></div>
          <span id="ov-conf-val">--</span>
        </div>

        <div class="ov-meta-row">
          <span id="ov-countdown">Next scan: 5s</span>
          <span id="ov-latency">AI: --ms</span>
        </div>

        <div class="ov-reasons" id="ov-reasons"></div>
        <div class="ov-notice" id="ov-notice" style="display:none"></div>

        <div class="ov-candle-count" id="ov-candle-count">Active Pair: ${currentPair || 'None'}</div>
      </div>
    `;
    document.body.appendChild(overlayElement);
    makeDraggable(overlayElement);

    overlayElement.querySelector('#ov-scan-btn')?.addEventListener('click', (e) => {
      e.stopPropagation();
      showOverlayNotice(`🔍 Scanning ${currentPair || 'market'}...`);
      fetchSignalForActivePair(true);
    });

    overlayElement.querySelector('#ov-scan-now-btn')?.addEventListener('click', (e) => {
      e.stopPropagation();
      const btn = e.currentTarget;
      btn.textContent = '⏳ SCANNING MARKET...';
      btn.disabled = true;
      showOverlayNotice(`🔍 Scanning ${currentPair || 'market'}...`);
      fetchSignalForActivePair(true, (res) => {
        btn.disabled = false;
        btn.textContent = `🔍 RESCAN ${currentPair || 'PAIR'} NOW`;
      });
    });

    overlayElement.querySelector('#ov-toggle-bot-btn')?.addEventListener('click', (e) => {
      e.stopPropagation();
      if (isRunning) {
        stopBot();
      } else {
        startBot(botSettings);
      }
      safeSendMessage({ type: 'BOT_STATE_CHANGED', running: isRunning });
    });

    overlayElement.querySelector('#ov-min-btn')?.addEventListener('click', (e) => {
      e.stopPropagation();
      overlayElement.classList.toggle('minimized');
      clampOverlayToViewport(overlayElement, overlayElement.offsetLeft, overlayElement.offsetTop);
    });

    overlayElement.querySelector('#ov-close-btn')?.addEventListener('click', (e) => {
      e.stopPropagation();
      overlayElement.classList.add('collapsed-fab');
      clampOverlayToViewport(overlayElement, overlayElement.offsetLeft, overlayElement.offsetTop);
    });

    overlayElement.querySelector('#ov-sound-btn')?.addEventListener('click', (e) => {
      e.stopPropagation();
      botSettings.soundEnabled = !botSettings.soundEnabled;
      e.currentTarget.textContent = botSettings.soundEnabled ? '🔊' : '🔇';
      safeStorageSet({ soundEnabled: botSettings.soundEnabled });
    });

    safeStorageGet(['overlayPosition'], (data) => {
      if (data.overlayPosition && Number.isFinite(data.overlayPosition.x) && Number.isFinite(data.overlayPosition.y)) {
        clampOverlayToViewport(overlayElement, data.overlayPosition.x, data.overlayPosition.y);
      } else {
        clampOverlayToViewport(overlayElement, window.innerWidth - 310, 80);
      }
    });
  }

  function broadcastCandleState(bucket, curMinStr, nextMinStr, secondsLeft, clockCountdownStr) {
    if (teardownIfOrphaned()) return;

    const tInfo = getCandleTimeRemaining();
    const currentMinuteBucket = bucket || tInfo.bucket;
    const curStr = curMinStr || tInfo.curMinStr;
    const nxtStr = nextMinStr || tInfo.nextMinStr;
    const secs = Number.isFinite(secondsLeft) ? secondsLeft : tInfo.secondsLeft;
    const clockStr = clockCountdownStr || tInfo.clockStr;

    const isCandleActive = Boolean(activeCandlePrediction && activeCandlePrediction.candleStartBucket === currentMinuteBucket);
    const pred = isCandleActive ? activeCandlePrediction : (pendingNextCandlePrediction || lastSignal);

    const payload = {
      success: true,
      isCandleActive,
      activeCandleMinute: isCandleActive ? activeCandlePrediction.candleMinuteStr : null,
      nextCandleMinute: nxtStr,
      currentMinuteStr: curStr,
      secondsLeftInCandle: secs,
      clockCountdownStr: clockStr,
      direction: pred ? (pred.direction || pred.signal || 'WAIT') : 'WAIT',
      signal: pred ? (pred.signal || pred.direction || 'WAIT') : 'WAIT',
      confidence: pred ? (pred.confidence || 0) : 0,
      entry_price: pred ? (pred.entry_price || currentPrice) : currentPrice,
      pair: currentPair,
      timeframe: currentTimeframe || '1m',
      candles_analyzed: (lastSignal && lastSignal.candles_analyzed) ? lastSignal.candles_analyzed : 2880,
      indicators: pred ? pred.indicators : null,
      reasons: pred ? pred.reasons : null,
      stats: candlePredictionStats
    };

    safeSendMessage({
      type: 'CANDLE_PREDICTION_STATE_UPDATE',
      state: payload
    });
    safeStorageSet({ currentCandleState: payload });
  }

  function updateLockedOverlayDisplay(bucket, curMinStr, nextMinStr, secondsLeft, clockCountdownStr) {
    if (!overlayElement || !overlayElement.isConnected) createOverlay();
    if (!overlayElement) return;

    const tInfo = getCandleTimeRemaining();
    const currentMinuteBucket = bucket || tInfo.bucket;
    const curStr = curMinStr || tInfo.curMinStr;
    const nxtStr = nextMinStr || tInfo.nextMinStr;
    const secs = Number.isFinite(secondsLeft) ? secondsLeft : tInfo.secondsLeft;
    const clockStr = clockCountdownStr || tInfo.clockStr;

    const sectionLabelEl = overlayElement.querySelector('#ov-section-label');
    const signalEl = overlayElement.querySelector('#ov-signal');
    const fabSigEl = overlayElement.querySelector('#ov-fab-sig');
    const pairEl = overlayElement.querySelector('#ov-pair');
    const priceEl = overlayElement.querySelector('#ov-price-badge');
    const predEl = overlayElement.querySelector('#ov-pred-action');
    const expiryEl = overlayElement.querySelector('#ov-expiry-badge');
    const candleStateEl = overlayElement.querySelector('#ov-candle-state');
    const candleTimerEl = overlayElement.querySelector('#ov-candle-timer');
    const candleOhlcEl = overlayElement.querySelector('#ov-candle-ohlc');
    const candlePosEl = overlayElement.querySelector('#ov-candle-pos');
    const candleRemainingEl = overlayElement.querySelector('#ov-candle-remaining');
    const fillEl = overlayElement.querySelector('#ov-conf-fill');
    const valEl = overlayElement.querySelector('#ov-conf-val');
    const latEl = overlayElement.querySelector('#ov-latency');
    const reasonsEl = overlayElement.querySelector('#ov-reasons');
    const scanNowBtn = overlayElement.querySelector('#ov-scan-now-btn');

    // Update learning stats card
    const accEl = overlayElement.querySelector('#ov-accuracy-badge');
    const evalEl = overlayElement.querySelector('#ov-learn-eval');
    const corEl = overlayElement.querySelector('#ov-learn-correct');
    const incorEl = overlayElement.querySelector('#ov-learn-incorrect');
    const noteEl = overlayElement.querySelector('#ov-learn-note');

    if (accEl) accEl.textContent = `ACC: ${candlePredictionStats.accuracy || 0}%`;
    if (evalEl) evalEl.textContent = String(candlePredictionStats.evaluatedCandles || 0);
    if (corEl) corEl.textContent = String(candlePredictionStats.correct || 0);
    if (incorEl) incorEl.textContent = String(candlePredictionStats.incorrect || 0);
    if (noteEl && candlePredictionStats.lastLearningNote) {
      noteEl.textContent = candlePredictionStats.lastLearningNote;
    }

    if (!signalEl) return;

    // Check whether we have an active locked candle running for this minute
    const isCandleActive = Boolean(activeCandlePrediction && activeCandlePrediction.candleStartBucket === currentMinuteBucket);

    if (isCandleActive) {
      // ── CANDLE IS CURRENTLY ACTIVE & LOCKED (e.g. 11:28 from 11:28:00 to 11:28:59) ──
      const sig = activeCandlePrediction.direction || activeCandlePrediction.signal || 'WAIT';
      const labelText = sig === 'BUY' ? '🟢 BUY' : sig === 'SELL' ? '🔴 SELL' : '⏳ WAIT';

      if (sectionLabelEl) {
        sectionLabelEl.innerHTML = `⏱️ ACTIVE CANDLE: <b>${activeCandlePrediction.candleMinuteStr}</b> (LOCKED)`;
      }
      signalEl.textContent = labelText;
      signalEl.className = 'ov-signal ' + sig.toLowerCase();

      if (fabSigEl) {
        fabSigEl.textContent = `${labelText} ${(activeCandlePrediction.confidence || 0).toFixed(0)}% (${secs}s)`;
      }

      if (predEl) {
        const dirText = sig === 'BUY' ? 'UP 🟢 (CALL)' : (sig === 'SELL' ? 'DOWN 🔴 (PUT)' : 'WAIT ⏳');
        let nextPreview = '';
        if (pendingNextCandlePrediction && pendingNextCandlePrediction.direction && pendingNextCandlePrediction.direction !== 'WAIT') {
          nextPreview = ` | Next (${nxtStr}): ${pendingNextCandlePrediction.direction === 'BUY' ? 'CALL 🟢' : 'PUT 🔴'}`;
        }
        predEl.textContent = `Candle ${activeCandlePrediction.candleMinuteStr} running ${dirText} • LOCKED${nextPreview}`;
      }

      if (expiryEl) {
        expiryEl.innerHTML = `⏱️ DURATION: 1m (<b>${clockStr}</b> left • Candle ${activeCandlePrediction.candleMinuteStr} Active • Locked)`;
        expiryEl.style.background = 'rgba(0, 255, 136, 0.16)';
        expiryEl.style.borderColor = 'rgba(0, 255, 136, 0.45)';
        expiryEl.style.color = '#00ff88';
      }

      overlayElement.style.borderColor = sig === 'BUY' ? '#00ff88' : (sig === 'SELL' ? '#ff1744' : '#ffc107');

      if (fillEl) fillEl.style.width = (activeCandlePrediction.confidence || 0) + '%';
      if (valEl) valEl.textContent = (activeCandlePrediction.confidence || 0).toFixed(1) + '%';
      if (latEl) latEl.textContent = `Locked: ${activeCandlePrediction.candleMinuteStr}`;

      if (reasonsEl && activeCandlePrediction.reasons) {
        reasonsEl.innerHTML = activeCandlePrediction.reasons.slice(0, 3).map(r => `<div class="ov-reason">• ${r}</div>`).join('');
      }

      // Render pills from active prediction
      renderIndicatorPills(activeCandlePrediction.indicators);
    } else {
      // ── WAITING FOR NEXT CANDLE TO START (e.g. at 11:27 before 11:28 begins) ──
      const upcoming = pendingNextCandlePrediction || lastSignal;
      const sig = upcoming ? (upcoming.direction || upcoming.signal || 'WAIT') : 'WAIT';
      const labelText = sig === 'BUY' ? '🟢 BUY' : sig === 'SELL' ? '🔴 SELL' : '⏳ WAIT';

      if (sectionLabelEl) {
        sectionLabelEl.innerHTML = `NEXT CANDLE PREDICTION: <b>${nxtStr}</b>`;
      }
      signalEl.textContent = upcoming ? labelText : '🔍 SCANNING...';
      signalEl.className = 'ov-signal ' + sig.toLowerCase();

      if (fabSigEl) {
        fabSigEl.textContent = upcoming ? `${labelText} (${clockStr})` : 'AI BOT';
      }

      if (predEl) {
        if (upcoming && sig !== 'WAIT') {
          const dirText = sig === 'BUY' ? 'UP 🟢 (CALL)' : 'DOWN 🔴 (PUT)';
          predEl.textContent = `Next 1m candle (${nxtStr}) predicted ${dirText} (Starts at ${nxtStr}:00)`;
        } else {
          predEl.textContent = `Scanning market to predict next candle (${nxtStr})...`;
        }
      }

      if (expiryEl) {
        expiryEl.innerHTML = `⏱️ DURATION: 1m (Starts in <b>${clockStr}</b> at ${nxtStr}:00)`;
        expiryEl.style.background = 'rgba(0, 212, 255, 0.12)';
        expiryEl.style.borderColor = 'rgba(0, 212, 255, 0.3)';
        expiryEl.style.color = '#00d4ff';
      }

      overlayElement.style.borderColor = upcoming && sig === 'BUY' ? '#00ff88' : (upcoming && sig === 'SELL' ? '#ff1744' : '#ffc107');

      if (upcoming && fillEl) fillEl.style.width = (upcoming.confidence || 0) + '%';
      if (upcoming && valEl) valEl.textContent = (upcoming.confidence || 0).toFixed(1) + '%';
      if (latEl) latEl.textContent = upcoming && upcoming.analysis_ms ? `AI: ${upcoming.analysis_ms}ms` : `Target: ${nxtStr}`;

      if (reasonsEl && upcoming && upcoming.reasons) {
        reasonsEl.innerHTML = upcoming.reasons.slice(0, 3).map(r => `<div class="ov-reason">• ${r}</div>`).join('');
      }

      if (upcoming) renderIndicatorPills(upcoming.indicators);
    }

    // Present candle countdown & position
    if (candleTimerEl) {
      if (secs <= 5) {
        candleTimerEl.textContent = `🚨 ${clockStr} — CLOSING!`;
        candleTimerEl.style.color = '#ff1744';
      } else {
        candleTimerEl.textContent = `⏳ ${clockStr} left`;
        candleTimerEl.style.color = '#ffc107';
      }
    }
    if (candleRemainingEl) {
      if (secs <= 5) {
        candleRemainingEl.innerHTML = `<span style="color:#ff1744; font-weight:900;">🚨 Present candle closing in <b>${clockStr}</b>! Next starts at ${nxtStr}:00</span>`;
      } else {
        candleRemainingEl.innerHTML = `<span style="color:#00d4ff;">⏳ Present candle: <b>${clockStr}</b> remaining until ${nxtStr}</span>`;
      }
    }

    const ovCountdownEl = overlayElement.querySelector('#ov-countdown');
    if (ovCountdownEl) {
      ovCountdownEl.textContent = `Bar: ${clockStr} | TF: ${currentTimeframe || '1m'}`;
    }

    // Pair & Price
    if (pairEl) pairEl.textContent = currentPair || 'EUR/USD';
    const liveP = currentPrice || (pairTickCandles[currentPair] && pairTickCandles[currentPair].close) || (lastSignal && lastSignal.entry_price) || '--';
    if (priceEl) priceEl.textContent = liveP ? `@ ${liveP}` : '';

    if (scanNowBtn) {
      scanNowBtn.textContent = `🔍 RESCAN ${currentPair || 'PAIR'} NOW`;
    }

    // Evaluate live candle progress on chart
    const curCandle = pairTickCandles[currentPair];
    const cEval = evaluateCurrentCandlePosition(curCandle, currentPair) || (lastSignal && lastSignal.current_candle ? {
      badge: lastSignal.current_candle.direction === 'BULLISH' ? `🟢 BULLISH (+${lastSignal.current_candle.change_pct}%)` : (lastSignal.current_candle.direction === 'BEARISH' ? `🔴 BEARISH (${lastSignal.current_candle.change_pct}%)` : '⚪ DOJI / FLAT'),
      open: lastSignal.current_candle.open,
      high: lastSignal.current_candle.high,
      low: lastSignal.current_candle.low,
      close: lastSignal.current_candle.close,
      position: lastSignal.current_candle.achieved_position
    } : null);

    if (cEval) {
      if (candleStateEl) candleStateEl.textContent = cEval.badge;
      if (candleOhlcEl) candleOhlcEl.textContent = `O: ${cEval.open} | H: ${cEval.high} | L: ${cEval.low} | C: ${cEval.close}`;
      if (candlePosEl) candlePosEl.textContent = `Position: ${cEval.position}`;
    }

    updateOverlayCandleCount();
  }

  function renderIndicatorPills(indicators) {
    if (!overlayElement) return;
    const pillsEl = overlayElement.querySelector('#ov-indicator-pills');
    if (pillsEl && indicators) {
      pillsEl.innerHTML = '';
      const indNames = ['rsi_14', 'macd', 'bb', 'ema_cross', 'stochastic'];
      indNames.forEach(name => {
        const ind = indicators[name];
        if (!ind) return;
        const pill = document.createElement('span');
        const sigName = ind.signal || '';
        const cls = sigName.includes('BUY') || sigName.includes('OVERSOLD') ? 'buy' :
                    sigName.includes('SELL') || sigName.includes('OVERBOUGHT') ? 'sell' : 'neutral';
        pill.className = 'pill ' + cls;
        pill.textContent = name.toUpperCase().replace('_', ' ');
        pill.title = typeof ind.value === 'object' ? JSON.stringify(ind.value) : `${ind.value} (${sigName})`;
        pillsEl.appendChild(pill);
      });
    }
  }

  function updateOverlay(signal) {
    updateLockedOverlayDisplay();
  }

  function updateOverlayMode(mode) {
    if (!overlayElement) return;
    const el = overlayElement.querySelector('#ov-ai-badge');
    if (el) el.textContent = '🧠 AUTO LEARNING';
  }

  function updateOverlayRunningState(running) {
    if (!overlayElement) return;
    const badge = overlayElement.querySelector('#ov-status-badge');
    const toggleBtn = overlayElement.querySelector('#ov-toggle-bot-btn');
    if (badge) {
      badge.textContent = running ? '▶ RUNNING' : '⏹ STOPPED';
      badge.className = 'ov-status-badge ' + (running ? 'running' : 'stopped');
    }
    if (toggleBtn) {
      toggleBtn.textContent = running ? '⏹ STOP AI BOT' : '▶ START AI BOT';
      toggleBtn.className = 'ov-bot-toggle-btn ' + (running ? 'btn-stop' : 'btn-start');
    }
    overlayElement.style.opacity = running ? '1' : '0.75';
  }

  function updateOverlayCandleCount() {
    if (!overlayElement) return;
    const el = overlayElement.querySelector('#ov-candle-count');
    const liveP = currentPrice || pairLatestPrices[currentPair] || (lastSignal && lastSignal.entry_price) || '--';
    const cCount = (lastSignal && lastSignal.candles_analyzed) ? lastSignal.candles_analyzed : 2880;
    const hCount = (lastSignal && lastSignal.history_hours) ? `${lastSignal.history_hours}h` : '48h';
    if (el) el.textContent = `Analysis: 2 Days (${cCount} bars, ${hCount}) | ${currentPair || 'EUR/USD'}`;
  }

  function showOverlayNotice(msg) {
    if (!overlayElement) return;
    const el = overlayElement.querySelector('#ov-notice');
    if (el) {
      el.textContent = msg;
      el.style.display = 'block';
      setTimeout(() => { el.style.display = 'none'; }, 4000);
    }
  }

  function makeDraggable(el) {
    let isDragging = false;
    let dragDistance = 0;
    let startX = 0, startY = 0, initLeft = 0, initTop = 0;
    let activePointerId = null;

    const header = el.querySelector('.ov-header');
    const fabPill = el.querySelector('#ov-fab-pill');

    function onDragStart(e) {
      if (e.button !== undefined && e.button !== 0) return;
      if (e.target && e.target.closest('button, select, input, a')) return;
      isDragging = true;
      dragDistance = 0;
      activePointerId = e.pointerId !== undefined ? e.pointerId : null;
      startX = e.clientX;
      startY = e.clientY;
      initLeft = el.offsetLeft;
      initTop = el.offsetTop;
      el.classList.add('dragging');
      try {
        if (el.setPointerCapture && activePointerId !== null) {
          el.setPointerCapture(activePointerId);
        }
      } catch (err) {}
      e.stopPropagation();
    }

    function onDragMove(e) {
      if (!isDragging) return;
      const dx = e.clientX - startX;
      const dy = e.clientY - startY;
      dragDistance = Math.hypot(dx, dy);
      clampOverlayToViewport(el, initLeft + dx, initTop + dy);
      e.preventDefault();
      e.stopPropagation();
    }

    function onDragEnd(e) {
      if (!isDragging) return;
      isDragging = false;
      el.classList.remove('dragging');
      try {
        if (el.releasePointerCapture && activePointerId !== null) {
          el.releasePointerCapture(activePointerId);
        }
      } catch (err) {}
      activePointerId = null;
      safeStorageSet({ overlayPosition: { x: el.offsetLeft, y: el.offsetTop } });

      // If user tapped/clicked the collapsed pill without dragging: expand!
      if (dragDistance < 8 && el.classList.contains('collapsed-fab')) {
        el.classList.remove('collapsed-fab');
        clampOverlayToViewport(el, el.offsetLeft, el.offsetTop);
      }
      if (e) e.stopPropagation();
    }

    if (header) {
      header.addEventListener('pointerdown', onDragStart);
    }
    if (fabPill) {
      fabPill.addEventListener('pointerdown', onDragStart);
      fabPill.addEventListener('click', (e) => {
        e.stopPropagation();
        e.preventDefault();
        el.classList.remove('collapsed-fab');
        clampOverlayToViewport(el, el.offsetLeft, el.offsetTop);
      });
    }

    window.addEventListener('pointermove', onDragMove, { passive: false });
    window.addEventListener('pointerup', onDragEnd);
    window.addEventListener('pointercancel', onDragEnd);
    window.addEventListener('resize', () => {
      if (el && el.isConnected) {
        clampOverlayToViewport(el, el.offsetLeft, el.offsetTop);
      }
    });
  }

  // ── 8. Handle Popup & Background Messages ──────────────────────────────────
  chrome.runtime.onMessage.addListener((msg, sender, sendResponse) => {
    if (teardownIfOrphaned()) {
      sendResponse({ error: 'Context invalidated' });
      return false;
    }

    // Whenever the user clicks the extension popup or sends a command, ensure the overlay is visible & movable
    createOverlay();
    if (overlayElement) {
      overlayElement.style.display = 'flex';
      overlayElement.classList.remove('collapsed-fab');
      clampOverlayToViewport(overlayElement, overlayElement.offsetLeft, overlayElement.offsetTop);
    }

    if (msg.type === 'SHOW_OVERLAY') {
      createOverlay();
      updateLockedOverlayDisplay();
      sendResponse({ ok: true, pair: currentPair });
      return true;
    } else if (msg.type === 'GET_CANDLE_PREDICTION_STATE') {
      const now = Date.now();
      const currentMinuteBucket = Math.floor(now / 60000) * 60000;
      const secondsIntoMinute = Math.floor((now % 60000) / 1000);
      const secondsLeftInCandle = 60 - secondsIntoMinute;
      const currentMinStr = formatMinuteString(currentMinuteBucket);
      const nextMinStr = formatMinuteString(currentMinuteBucket + 60000);

      const isCandleActive = Boolean(activeCandlePrediction && activeCandlePrediction.candleStartBucket === currentMinuteBucket);
      const curPred = isCandleActive ? activeCandlePrediction : (pendingNextCandlePrediction || lastSignal);

      sendResponse({
        success: true,
        isCandleActive,
        activeCandleMinute: isCandleActive ? activeCandlePrediction.candleMinuteStr : null,
        nextCandleMinute: nextMinStr,
        currentMinuteStr: currentMinStr,
        secondsLeftInCandle,
        direction: curPred ? (curPred.direction || curPred.signal || 'WAIT') : 'WAIT',
        signal: curPred ? (curPred.signal || curPred.direction || 'WAIT') : 'WAIT',
        confidence: curPred ? (curPred.confidence || 0) : 0,
        entry_price: curPred ? (curPred.entry_price || currentPrice) : currentPrice,
        pair: currentPair,
        timeframe: currentTimeframe || '1m',
        indicators: curPred ? curPred.indicators : null,
        reasons: curPred ? curPred.reasons : null,
        stats: candlePredictionStats
      });
      return true;
    } else if (msg.type === 'FORCE_RESCAN_PAIR') {
      fetchSignalForActivePair(true, () => {
        const now = Date.now();
        const currentMinuteBucket = Math.floor(now / 60000) * 60000;
        const secondsIntoMinute = Math.floor((now % 60000) / 1000);
        const secondsLeftInCandle = 60 - secondsIntoMinute;
        const currentMinStr = formatMinuteString(currentMinuteBucket);
        const nextMinStr = formatMinuteString(currentMinuteBucket + 60000);

        const isCandleActive = Boolean(activeCandlePrediction && activeCandlePrediction.candleStartBucket === currentMinuteBucket);
        const curPred = isCandleActive ? activeCandlePrediction : (pendingNextCandlePrediction || lastSignal);

        sendResponse({
          success: true,
          isCandleActive,
          activeCandleMinute: isCandleActive ? activeCandlePrediction.candleMinuteStr : null,
          nextCandleMinute: nextMinStr,
          currentMinuteStr: currentMinStr,
          secondsLeftInCandle,
          direction: curPred ? (curPred.direction || curPred.signal || 'WAIT') : 'WAIT',
          signal: curPred ? (curPred.signal || curPred.direction || 'WAIT') : 'WAIT',
          confidence: curPred ? (curPred.confidence || 0) : 0,
          entry_price: curPred ? (curPred.entry_price || currentPrice) : currentPrice,
          pair: currentPair,
          timeframe: currentTimeframe || '1m',
          indicators: curPred ? curPred.indicators : null,
          reasons: curPred ? curPred.reasons : null,
          stats: candlePredictionStats
        });
      });
      return true;
    } else if (msg.type === 'START_BOT') {
      startBot(msg.settings);
      updateOverlayRunningState(true);
      sendResponse({ ok: true, pair: currentPair });
    } else if (msg.type === 'STOP_BOT') {
      stopBot();
      updateOverlayRunningState(false);
      sendResponse({ ok: true });
    } else if (msg.type === 'SETTINGS_UPDATED') {
      botSettings = { ...botSettings, ...msg.settings };
      updateOverlayMode(botSettings.mode);
      sendResponse({ ok: true });
    } else if (msg.type === 'GET_CURRENT_DATA') {
      const state = extractLivePageMarketState();
      if (state.pair) currentPair = state.pair;
      sendResponse({
        pair: currentPair,
        timeframe: state.timeframe || currentTimeframe,
        balance: state.balance || accountBalance,
        lastSignal
      });
    } else if (msg.type === 'SCAN_PAGE_NOW') {
      fetchSignalForActivePair(true, (res) => {
        sendResponse(res);
      });
      return true; // keep message channel open for async response
    } else if (msg.type === 'SHOW_AND_UPDATE_OVERLAY') {
      if (msg.signal) {
        lastSignal = msg.signal;
        if (msg.signal.pair) currentPair = msg.signal.pair;
        recordSignalInHistory(msg.signal);
        updateOverlay(msg.signal);
      }
      sendResponse({ ok: true });
    }
    return true;
  });

  // Auto-initialize settings on start
  safeStorageGet(
    ['botRunning', 'tradeAmount', 'tradeDuration', 'minConfidence', 'serverUrl', 'mode', 'soundEnabled'],
    (data) => {
      startBot({
        ...data,
        botRunning: true
      });
    }
  );
})();
