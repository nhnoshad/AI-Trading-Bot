// AI Trading Bot - Popup Controller (Auto-Scans https://market-qx.info/en/demo-trade on Open)

let currentMode = 'MANUAL';
let botRunning = true;
let stats = { trades: 0, wins: 0, losses: 0, pnl: 0, streak: 0, streakDir: 'W' };
let currentCandleState = null;

function formatMinuteString(ts) {
  const d = new Date(ts);
  const hh = String(d.getHours()).padStart(2, '0');
  const mm = String(d.getMinutes()).padStart(2, '0');
  return `${hh}:${mm}`;
}

function isContextValid() {
  try {
    return typeof chrome !== 'undefined' &&
           Boolean(chrome?.runtime?.id) &&
           typeof chrome.runtime.getManifest === 'function';
  } catch (e) {
    return false;
  }
}

function safeStorageGet(keys, callback) {
  if (!isContextValid()) return;
  try {
    chrome.storage.local.get(keys, (data) => {
      if (chrome.runtime.lastError) return;
      if (callback) callback(data || {});
    });
  } catch (e) {}
}

function safeStorageSet(data, callback) {
  if (!isContextValid()) return;
  try {
    chrome.storage.local.set(data, () => {
      if (chrome.runtime.lastError) return;
      if (callback) callback();
    });
  } catch (e) {}
}

document.addEventListener('DOMContentLoaded', async () => {
  if (!isContextValid()) return;
  await loadSettings();
  await loadStats();
  setupEventListeners();
  await testConnection();

  // Instant render from storage first to eliminate blank/flicker delay
  safeStorageGet(['currentCandleState', 'lastSignal'], (data) => {
    if (data.currentCandleState) {
      renderCandlePredictionState(data.currentCandleState);
    } else if (data.lastSignal) {
      renderSignal(data.lastSignal);
    }
  });

  // Query live locked candle prediction state directly from active Quotex tab
  await syncWithActiveTab(false);
  sendMessageToContent({ type: 'SHOW_OVERLAY' });

  // Live 1-second countdown synchronized with wall-clock minutes and locked candle state
  setInterval(() => {
    const now = Date.now();
    const currentMinuteBucket = Math.floor(now / 60000) * 60000;
    const secondsIntoMinute = Math.floor((now % 60000) / 1000);
    const secondsLeft = 60 - secondsIntoMinute;
    const currentMinStr = formatMinuteString(currentMinuteBucket);
    const nextMinStr = formatMinuteString(currentMinuteBucket + 60000);

    const labelEl = document.getElementById('signalLabel');
    const expEl = document.getElementById('signalExpiry');
    const cPosEl = document.getElementById('signalCandlePos');
    const predActionEl = document.getElementById('signalPredAction');

    // Minute turnover detection: refresh prediction state if candle completed
    if (currentCandleState && currentCandleState.currentMinuteStr && currentCandleState.currentMinuteStr !== currentMinStr) {
      currentCandleState.currentMinuteStr = currentMinStr;
      syncWithActiveTab(false);
      return;
    }

    if (currentCandleState && currentCandleState.isCandleActive && currentCandleState.activeCandleMinute) {
      // ── ACTIVE LOCKED CANDLE IN PROGRESS (e.g. 11:28:00 - 11:28:59) ──
      if (labelEl) {
        labelEl.innerHTML = `⏱️ ACTIVE CANDLE: <b>${currentCandleState.activeCandleMinute}</b> (LOCKED)`;
        labelEl.style.color = '#00ff88';
      }
      if (expEl) {
        expEl.innerHTML = `⏱️ Duration: <b>${secondsLeft}s left</b> (Candle ${currentCandleState.activeCandleMinute} Active • Locked)`;
        expEl.style.background = 'rgba(0, 255, 136, 0.16)';
        expEl.style.borderColor = 'rgba(0, 255, 136, 0.45)';
        expEl.style.color = '#00ff88';
      }
    } else {
      // ── PREDICTION FOR NEXT CANDLE (e.g. at 11:27 before 11:28 starts) ──
      if (labelEl) {
        labelEl.innerHTML = `NEXT CANDLE PREDICTION: <b>${nextMinStr}</b>`;
        labelEl.style.color = '#00d4ff';
      }
      if (expEl) {
        expEl.innerHTML = `⏱️ Duration: 1m (Starts in <b>${secondsLeft}s</b> at ${nextMinStr}:00)`;
        expEl.style.background = 'rgba(0, 212, 255, 0.12)';
        expEl.style.borderColor = 'rgba(0, 212, 255, 0.3)';
        expEl.style.color = '#00d4ff';
      }
    }

    if (cPosEl) {
      if (secondsLeft <= 5) {
        cPosEl.innerHTML = `<span style="color:#ff1744; font-weight:700;">🚨 Present candle closing in <b>${secondsLeft}s</b>! Next starts at ${nextMinStr}:00</span>`;
      } else {
        cPosEl.innerHTML = `<span>⏳ Present candle: <b>${secondsLeft}s</b> left until ${nextMinStr}</span>`;
      }
    }
  }, 1000);
});

function setupEventListeners() {
  document.getElementById('btnScanNow')?.addEventListener('click', () => syncWithActiveTab(true));
  document.getElementById('btnStart')?.addEventListener('click', startBot);
  document.getElementById('btnStop')?.addEventListener('click', stopBot);
  document.getElementById('btnTestConn')?.addEventListener('click', testConnection);
  document.getElementById('btnExportCsv')?.addEventListener('click', exportSignalsToCSV);
  document.getElementById('linkDashboard')?.addEventListener('click', (e) => {
    e.preventDefault();
    openDashboard();
  });

  document.getElementById('tradeDuration')?.addEventListener('change', saveSettings);
  document.getElementById('serverUrl')?.addEventListener('change', saveSettings);
  document.getElementById('minConfidence')?.addEventListener('input', (e) => {
    const valEl = document.getElementById('minConfidenceVal');
    if (valEl) valEl.textContent = e.target.value + '%';
    saveSettings();
  });
}

// ── Synchronize with Page Context & Active Locked Candle ───────────────────
async function syncWithActiveTab(forceRescan = false) {
  if (!isContextValid()) return;

  const scanBtn = document.getElementById('btnScanNow');
  const sigVal = document.getElementById('signalValue');
  const sigPair = document.getElementById('signalPair');

  if (scanBtn && forceRescan) {
    scanBtn.textContent = '⏳ SCANNING MARKET...';
    scanBtn.disabled = true;
  }

  try {
    const tabs = await chrome.tabs.query({ active: true, currentWindow: true });
    const tab = tabs[0];

    if (!tab || !tab.id) {
      safeStorageGet(['currentCandleState', 'lastSignal'], (data) => {
        if (data.currentCandleState) {
          renderCandlePredictionState(data.currentCandleState);
        } else if (data.lastSignal) {
          renderSignal(data.lastSignal);
        }
      });
      return;
    }

    const msgType = forceRescan ? 'FORCE_RESCAN_PAIR' : 'GET_CANDLE_PREDICTION_STATE';
    let response = await sendMessagePromise(tab.id, { type: msgType });

    // If content script was not injected or orphaned, inject it fresh
    if ((!response || !response.success) && tab.url && !tab.url.startsWith('chrome://')) {
      try {
        await chrome.scripting.insertCSS({
          target: { tabId: tab.id },
          files: ['src/overlay/overlay.css']
        });
        await chrome.scripting.executeScript({
          target: { tabId: tab.id },
          files: ['src/scripts/content.js']
        });
        await new Promise(r => setTimeout(r, 350));
        response = await sendMessagePromise(tab.id, { type: msgType });
      } catch (injectErr) {}
    }

    if (response && response.success) {
      renderCandlePredictionState(response);
      return;
    }

    // Fallback: check storage
    safeStorageGet(['currentCandleState', 'lastSignal'], (data) => {
      if (data.currentCandleState) {
        renderCandlePredictionState(data.currentCandleState);
      } else if (data.lastSignal) {
        renderSignal(data.lastSignal);
      }
    });
  } catch (err) {
    console.warn('Sync error:', err);
  } finally {
    if (scanBtn) scanBtn.disabled = false;
  }
}

async function scanActivePagePair() {
  await syncWithActiveTab(true);
}

function sendMessagePromise(tabId, msg) {
  return new Promise((resolve) => {
    if (!isContextValid()) {
      resolve(null);
      return;
    }
    try {
      chrome.tabs.sendMessage(tabId, msg, (resp) => {
        if (chrome.runtime.lastError) {
          resolve(null);
        } else {
          resolve(resp);
        }
      });
    } catch (e) {
      resolve(null);
    }
  });
}

async function requestBackendPredictionForPair(pair, livePrice = null) {
  const settings = getSettings();
  const candles = generatePairSpecificCandles(pair, 120, livePrice);
  try {
    const resp = await fetch(`${settings.serverUrl}/api/predict`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        candles,
        timeframe: '1m',
        pair,
        min_confidence: settings.minConfidence
      })
    });
    if (!resp.ok) return null;
    const data = await resp.json();
    safeStorageSet({ lastSignal: data });
    return data;
  } catch (e) {
    return null;
  }
}

function getFallbackPriceForPair(pair) {
  const clean = String(pair).toUpperCase().replace(/(_OTC|\(OTC\)|\bOTC\b)/gi, '').replace(/[^A-Z0-9]/g, '');
  const map = {
    EURUSD: 1.0854, GBPUSD: 1.2742, USDJPY: 151.45, AUDUSD: 0.6580,
    USDCAD: 1.3590, USDCHF: 0.8840, EURGBP: 0.8540, EURJPY: 164.30,
    GBPJPY: 192.80, EURAUD: 1.6520, EURCAD: 1.4860, EURCHF: 0.9620,
    EURNZD: 1.7985, GBPNZD: 2.1040, AUDNZD: 1.0920, GBPAUD: 1.9340,
    GBPCAD: 1.7380, GBPCHF: 1.1240, AUDCAD: 0.8960, AUDCHF: 0.5820,
    AUDJPY: 99.65, CADJPY: 111.40, CHFJPY: 171.20, NZDJPY: 91.80,
    NZDUSD: 0.6090, NZDCAD: 0.8240, NZDCHF: 0.5380, CADCHF: 0.6510,
    USDBDT: 119.50, USDINR: 84.560, USDBRL: 5.0520, BRLUSD: 0.1980,
    USDPKR: 278.40, USDEGP: 48.65, USDTRY: 34.25
  };
  for (const [k, v] of Object.entries(map)) {
    if (clean.startsWith(k)) return v;
  }
  return 1.0850;
}

function generatePairSpecificCandles(pair, count = 120, livePrice = null) {
  let pairHash = 2166136261;
  for (let i = 0; i < pair.length; i++) {
    pairHash ^= pair.charCodeAt(i);
    pairHash = Math.imul(pairHash, 16777619) >>> 0;
  }
  const unitRand = (step, salt) => {
    let x = (pairHash ^ (step * 374761393) ^ (salt * 668265263)) >>> 0;
    x = ((x ^ (x >> 13)) * 1274126177) >>> 0;
    x = (x ^ (x >> 16)) >>> 0;
    return (x % 100000) / 100000.0;
  };

  const targetPrice = (Number.isFinite(livePrice) && livePrice > 0) ? livePrice : getFallbackPriceForPair(pair);
  const decimals = targetPrice > 500 ? 2 : (targetPrice > 20 ? 3 : 5);
  const scale = targetPrice * 0.00042;
  const currentStep = Math.floor(Date.now() / 6000);
  const startStep = currentStep - count;
  const phase1 = (pairHash % 360) * (Math.PI / 180.0);
  const phase2 = ((pairHash >> 8) % 360) * (Math.PI / 180.0);
  const freq1 = 8.5 + (pairHash % 7) * 0.6;
  const freq2 = 21.0 + ((pairHash >> 4) % 9) * 0.8;

  let p = targetPrice;
  const rawCandles = [];
  for (let idx = 1; idx <= count; idx++) {
    const t = startStep + idx;
    const waveFast = Math.sin(t / freq1 + phase1) * scale * 0.85;
    const waveSlow = Math.cos(t / freq2 + phase2) * scale * 0.65;
    const noise = (unitRand(t, 1) - 0.50) * scale * 0.90;
    const meanRev = (targetPrice - p) * 0.06;
    const o = p;
    const c = Math.max(0.00001, o + waveFast + waveSlow + noise + meanRev);
    rawCandles.push({
      open: o,
      high: Math.max(o, c) + unitRand(t, 2) * scale * 0.45,
      low: Math.min(o, c) - unitRand(t, 3) * scale * 0.45,
      close: c,
      volume: Math.round(700 + unitRand(t, 4) * 1600)
    });
    p = c;
  }

  const shift = targetPrice - rawCandles[rawCandles.length - 1].close;
  return rawCandles.map((c, idx) => {
    const isLast = idx === rawCandles.length - 1;
    const o = Number((c.open + shift).toFixed(decimals));
    const cl = isLast ? Number(targetPrice.toFixed(decimals)) : Number((c.close + shift).toFixed(decimals));
    return {
      open: o,
      high: Number(Math.max(o, cl, c.high + shift).toFixed(decimals)),
      low: Number(Math.min(o, cl, c.low + shift).toFixed(decimals)),
      close: cl,
      volume: c.volume
    };
  });
}

// ── Settings & Stats ────────────────────────────────────────────────────────
async function loadSettings() {
  safeStorageGet([
    'tradeDuration', 'minConfidence', 'serverUrl', 'botRunning', 'lastSignal'
  ], (data) => {
    if (data.tradeDuration) document.getElementById('tradeDuration').value = data.tradeDuration;
    if (data.minConfidence) {
      document.getElementById('minConfidence').value = data.minConfidence;
      document.getElementById('minConfidenceVal').textContent = data.minConfidence + '%';
    }
    if (data.serverUrl) document.getElementById('serverUrl').value = data.serverUrl;
    botRunning = data.botRunning !== undefined ? data.botRunning : true;
    updateBotStatusUI();
    if (data.lastSignal) renderSignal(data.lastSignal);
  });
}

async function saveSettings() {
  const s = getSettings();
  safeStorageSet(s);
  sendMessageToContent({ type: 'SETTINGS_UPDATED', settings: s });
}

function getSettings() {
  return {
    tradeDuration: parseInt(document.getElementById('tradeDuration')?.value, 10) || 60,
    minConfidence: parseInt(document.getElementById('minConfidence')?.value, 10) || 60,
    serverUrl: document.getElementById('serverUrl')?.value.trim() || 'http://localhost:8000'
  };
}

async function loadStats() {
  safeStorageGet(['stats'], (data) => {
    if (data.stats) {
      stats = data.stats;
      renderStats();
    }
  });
}

function renderStats() {
  const evaluatedCount = stats.evaluatedCandles || stats.trades || 0;
  const correctCount = stats.correct || stats.wins || 0;
  const incorrectCount = stats.incorrect || stats.losses || 0;
  const accuracy = (stats.accuracy !== undefined) ? stats.accuracy : (evaluatedCount > 0 ? Math.round((correctCount / evaluatedCount) * 100) : 0);

  const tEl = document.getElementById('statTrades');
  if (tEl) tEl.textContent = evaluatedCount;
  const wEl = document.getElementById('statWins');
  if (wEl) wEl.textContent = correctCount;
  const lEl = document.getElementById('statLosses');
  if (lEl) lEl.textContent = incorrectCount;
  const wrEl = document.getElementById('statWinRate');
  if (wrEl) wrEl.textContent = accuracy + '%';

  const pnlEl = document.getElementById('statPnl');
  if (pnlEl) {
    pnlEl.textContent = 'Active';
    pnlEl.className = 'stat-val green';
  }
  const streakEl = document.getElementById('statStreak');
  if (streakEl) {
    streakEl.textContent = stats.streak > 0 ? `${stats.streakDir || 'W'}${stats.streak}` : '-';
    streakEl.className = 'stat-val ' + (stats.streakDir === 'W' ? 'green' : 'red');
  }

  const noteEl = document.getElementById('statLearningNote');
  if (noteEl && stats.lastLearningNote) {
    noteEl.textContent = stats.lastLearningNote;
  }
}

function renderCandlePredictionState(state) {
  if (!state) return;
  currentCandleState = state;

  const card = document.getElementById('signalCard');
  const labelEl = document.getElementById('signalLabel');
  const val = document.getElementById('signalValue');
  const fill = document.getElementById('confidenceFill');
  const conf = document.getElementById('confidenceValue');
  const reasonsBox = document.getElementById('signalReasons');
  const predActionEl = document.getElementById('signalPredAction');
  const expiryEl = document.getElementById('signalExpiry');
  const candleStateEl = document.getElementById('signalCandleState');
  const candleOhlcEl = document.getElementById('signalCandleOhlc');
  const candlePosEl = document.getElementById('signalCandlePos');
  const pairEl = document.getElementById('signalPair');
  const scanBtn = document.getElementById('btnScanNow');

  if (!card || !val) return;

  if (!state.pair || state.pair === 'No Pair Found' || state.pair === 'No pair detected') {
    card.className = 'signal-card wait';
    if (labelEl) {
      labelEl.textContent = 'NO ACTIVE PAIR';
      labelEl.style.color = '#ffc107';
    }
    val.textContent = '⚠️ NO PAIR';
    val.className = 'signal-value wait';
    if (predActionEl) predActionEl.textContent = 'Please open a currency pair on Quotex';
    if (expiryEl) {
      expiryEl.textContent = '⏱️ Duration: --';
      expiryEl.style.background = 'rgba(255,193,7,0.12)';
      expiryEl.style.borderColor = 'rgba(255,193,7,0.3)';
      expiryEl.style.color = '#ffc107';
    }
    if (pairEl) pairEl.textContent = 'No active pair detected on Quotex';
    if (candleStateEl) candleStateEl.textContent = '⚪ Waiting for currency pair...';
    if (candleOhlcEl) candleOhlcEl.textContent = 'O: -- | H: -- | L: -- | C: --';
    if (candlePosEl) candlePosEl.textContent = 'Open Quotex trading chart to start analyzing.';
    if (fill) fill.style.width = '0%';
    if (conf) conf.textContent = '--';
    if (reasonsBox) reasonsBox.innerHTML = '<div>• No active currency pair tab open on Quotex</div>';
    return;
  }

  const now = Date.now();
  const currentMinuteBucket = Math.floor(now / 60000) * 60000;
  const secondsLeft = Number.isFinite(state.secondsLeftInCandle)
    ? state.secondsLeftInCandle
    : (60 - (Math.floor(now / 1000) % 60));
  const curMinStr = state.currentMinuteStr || formatMinuteString(currentMinuteBucket);
  const nxtMinStr = state.nextCandleMinute || formatMinuteString(currentMinuteBucket + 60000);

  const sigName = (state.direction || state.signal || 'WAIT').toUpperCase();
  card.className = 'signal-card ' + sigName.toLowerCase();
  val.textContent = sigName === 'BUY' ? '🟢 BUY' : sigName === 'SELL' ? '🔴 SELL' : '⏳ WAIT';
  val.className = 'signal-value ' + sigName.toLowerCase();

  const confidence = Number(state.confidence || 0);
  if (fill) fill.style.width = `${Math.min(100, Math.max(0, confidence))}%`;
  if (conf) conf.textContent = `${confidence.toFixed(1)}%`;

  if (pairEl) {
    const pTxt = state.entry_price ? ` @ ${Number(state.entry_price).toFixed(4)}` : '';
    pairEl.textContent = `${state.pair}${pTxt} | 1m`;
  }

  if (scanBtn) {
    scanBtn.textContent = `🔍 RESCAN ${state.pair} NOW`;
    scanBtn.disabled = false;
  }

  if (state.isCandleActive && state.activeCandleMinute) {
    // ── 1. ACTIVE CANDLE RUNNING (LOCKED FOR THIS MINUTE) ──
    if (labelEl) {
      labelEl.innerHTML = `⏱️ ACTIVE CANDLE: <b>${state.activeCandleMinute}</b> (LOCKED)`;
      labelEl.style.color = '#00ff88';
    }
    if (predActionEl) {
      const dirText = sigName === 'BUY' ? 'UP 🟢 (CALL)' : (sigName === 'SELL' ? 'DOWN 🔴 (PUT)' : 'WAIT ⏳');
      predActionEl.textContent = `Candle ${state.activeCandleMinute} running ${dirText} • LOCKED (Fixed)`;
    }
    if (expiryEl) {
      expiryEl.innerHTML = `⏱️ Duration: <b>${secondsLeft}s left</b> (Candle ${state.activeCandleMinute} Active • Locked)`;
      expiryEl.style.background = 'rgba(0, 255, 136, 0.16)';
      expiryEl.style.borderColor = 'rgba(0, 255, 136, 0.45)';
      expiryEl.style.color = '#00ff88';
    }
  } else {
    // ── 2. PREDICTION FOR NEXT CANDLE ──
    if (labelEl) {
      labelEl.innerHTML = `NEXT CANDLE PREDICTION: <b>${nxtMinStr}</b>`;
      labelEl.style.color = '#00d4ff';
    }
    if (predActionEl) {
      if (sigName === 'BUY') predActionEl.textContent = `Next 1m candle (${nxtMinStr}) predicted UP 🟢 (CALL)`;
      else if (sigName === 'SELL') predActionEl.textContent = `Next 1m candle (${nxtMinStr}) predicted DOWN 🔴 (PUT)`;
      else predActionEl.textContent = `Market consolidates — Wait for breakout ⏳`;
    }
    if (expiryEl) {
      expiryEl.innerHTML = `⏱️ Duration: 1m (Starts in <b>${secondsLeft}s</b> at ${nxtMinStr}:00)`;
      expiryEl.style.background = 'rgba(0, 212, 255, 0.12)';
      expiryEl.style.borderColor = 'rgba(0, 212, 255, 0.3)';
      expiryEl.style.color = '#00d4ff';
    }
  }

  // Current Candle Position countdown
  if (candlePosEl) {
    if (secondsLeft <= 5) {
      candlePosEl.innerHTML = `<span style="color:#ff1744; font-weight:700;">🚨 Present candle closing in <b>${secondsLeft}s</b>! Next starts at ${nxtMinStr}:00</span>`;
    } else {
      candlePosEl.innerHTML = `<span>⏳ Present candle: <b>${secondsLeft}s</b> left until ${nxtMinStr}</span>`;
    }
  }
  if (candleStateEl) {
    if (sigName === 'BUY') {
      candleStateEl.textContent = `🟢 Bullish Bias Detected (Target: ${nxtMinStr})`;
    } else if (sigName === 'SELL') {
      candleStateEl.textContent = `🔴 Bearish Bias Detected (Target: ${nxtMinStr})`;
    } else {
      candleStateEl.textContent = `⚪ Neutral Market Bias`;
    }
  }

  // Indicator pills
  const pillsEl = document.getElementById('indicatorPills');
  if (pillsEl && state.indicators) {
    pillsEl.innerHTML = '';
    ['rsi_14', 'macd', 'bb', 'ema_cross', 'stochastic'].forEach(name => {
      const ind = state.indicators[name];
      if (!ind) return;
      const pill = document.createElement('span');
      const sig = (ind.signal || '').toUpperCase();
      const cls = sig.includes('BUY') || sig.includes('OVERSOLD') ? 'buy' :
                  sig.includes('SELL') || sig.includes('OVERBOUGHT') ? 'sell' : 'neutral';
      pill.className = 'pill ' + cls;
      pill.textContent = name.toUpperCase().replace('_', ' ');
      pill.title = typeof ind.value === 'object' ? JSON.stringify(ind.value) : `${ind.value} (${sig})`;
      pillsEl.appendChild(pill);
    });
  }

  // Reasons box
  if (reasonsBox && Array.isArray(state.reasons)) {
    reasonsBox.innerHTML = state.reasons.slice(0, 3).map(r => `<div>• ${r}</div>`).join('');
  }

  // Stats
  if (state.stats) {
    stats = state.stats;
    renderStats();
  }
}

function renderSignal(signal) {
  if (!signal) return;
  const now = Date.now();
  const currentMinuteBucket = Math.floor(now / 60000) * 60000;
  const state = {
    isCandleActive: false,
    activeCandleMinute: null,
    nextCandleMinute: formatMinuteString(currentMinuteBucket + 60000),
    currentMinuteStr: formatMinuteString(currentMinuteBucket),
    secondsLeftInCandle: 60 - (Math.floor(now / 1000) % 60),
    direction: signal.signal || signal.direction || 'WAIT',
    signal: signal.signal || signal.direction || 'WAIT',
    confidence: signal.confidence || 0,
    entry_price: signal.entry_price || null,
    pair: signal.pair || 'EURUSD',
    timeframe: signal.timeframe || '1m',
    indicators: signal.indicators || null,
    reasons: signal.reasons || null,
    stats: stats
  };
  renderCandlePredictionState(state);
}

async function startBot() {
  botRunning = true;
  const s = getSettings();
  safeStorageSet({ ...s, botRunning: true });
  updateBotStatusUI();
  sendMessageToContent({ type: 'START_BOT', settings: s });
  await syncWithActiveTab(false);
}

async function stopBot() {
  botRunning = false;
  safeStorageSet({ botRunning: false });
  updateBotStatusUI();
  sendMessageToContent({ type: 'STOP_BOT' });
}

function updateBotStatusUI() {
  const badge = document.getElementById('botStatus');
  const startBtn = document.getElementById('btnStart');
  const stopBtn = document.getElementById('btnStop');
  if (botRunning) {
    if (badge) {
      badge.textContent = '▶ RUNNING';
      badge.className = 'status-badge running';
    }
    if (startBtn) startBtn.disabled = true;
    if (stopBtn) stopBtn.disabled = false;
  } else {
    if (badge) {
      badge.textContent = '⏹ STOPPED';
      badge.className = 'status-badge';
    }
    if (startBtn) startBtn.disabled = false;
    if (stopBtn) stopBtn.disabled = true;
  }
}

async function testConnection() {
  const url = document.getElementById('serverUrl')?.value.trim() || 'http://localhost:8000';
  const connDot = document.getElementById('connDot');
  const connStatus = document.getElementById('connStatus');
  try {
    const resp = await fetch(url + '/api/health');
    if (resp.ok) {
      const data = await resp.json();
      if (connDot) connDot.className = 'conn-dot connected';
      if (connStatus) connStatus.textContent = `Online | Trained Model v${data.model_version}`;
    } else {
      throw new Error('HTTP ' + resp.status);
    }
  } catch (e) {
    if (connDot) connDot.className = 'conn-dot';
    if (connStatus) connStatus.textContent = 'Offline (Run start_backend.bat)';
  }
}

async function exportSignalsToCSV() {
  const url = document.getElementById('serverUrl')?.value.trim() || 'http://localhost:8000';
  let signals = [];
  try {
    const resp = await fetch(url + '/api/signals?limit=50');
    if (resp.ok) {
      const json = await resp.json();
      signals = json.signals || [];
    }
  } catch (e) {}

  if (signals.length === 0) {
    safeStorageGet(['signalHistory'], (local) => {
      signals = local.signalHistory || [];
      triggerCsvDownload(signals);
    });
    return;
  }
  triggerCsvDownload(signals);
}

function triggerCsvDownload(signals) {
  if (!signals || signals.length === 0) {
    alert('No signals recorded yet.');
    return;
  }
  const headers = ['Timestamp', 'Pair', 'Direction', 'Confidence_%', 'Entry_Price', 'Outcome', 'Reasons'];
  const rows = signals.map(s => [
    s.timestamp || s.time || '',
    s.pair || 'EURUSD',
    s.signal || '',
    s.confidence || '',
    s.entry_price || '',
    s.verified_outcome || s.result || 'PENDING',
    `"${(Array.isArray(s.reasons) ? s.reasons.join('; ') : (s.reasons || '')).replace(/"/g, '""')}"`
  ]);
  const csvContent = [headers.join(','), ...rows.map(r => r.join(','))].join('\n');
  const blob = new Blob([csvContent], { type: 'text/csv;charset=utf-8;' });
  const blobUrl = URL.createObjectURL(blob);
  const a = document.createElement('a');
  a.href = blobUrl;
  a.download = `ai_trading_signals_${new Date().toISOString().slice(0, 10)}.csv`;
  a.click();
  URL.revokeObjectURL(blobUrl);
}

function openDashboard() {
  const s = getSettings();
  const url = `${s.serverUrl || 'http://localhost:8000'}/dashboard`;
  if (isContextValid()) {
    chrome.tabs.create({ url });
  } else {
    window.open(url, '_blank');
  }
}

async function sendMessageToContent(msg) {
  if (!isContextValid()) return;
  try {
    const tabs = await chrome.tabs.query({ active: true, currentWindow: true });
    if (tabs[0]) {
      chrome.tabs.sendMessage(tabs[0].id, msg, () => {
        if (chrome.runtime.lastError) {}
      });
    }
  } catch (e) {}
}

if (isContextValid()) {
  chrome.runtime.onMessage.addListener((msg) => {
    if (!isContextValid()) return;
    if (msg.type === 'CANDLE_PREDICTION_STATE_UPDATE' && msg.state) {
      renderCandlePredictionState(msg.state);
    }
    if (msg.type === 'SIGNAL_UPDATE' && msg.signal) {
      if (!currentCandleState || !currentCandleState.isCandleActive) {
        renderSignal(msg.signal);
      }
      safeStorageSet({ lastSignal: msg.signal });
    }
    if (msg.type === 'STATS_UPDATE' && msg.stats) {
      stats = msg.stats;
      renderStats();
    }
    if (msg.type === 'BOT_STATE_CHANGED') {
      botRunning = Boolean(msg.running);
      updateBotStatusUI();
    }
  });
}
