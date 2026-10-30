// AI Trading Bot - Background Service Worker

const DEFAULT_SETTINGS = {
  serverUrl: 'http://localhost:8000',
  tradeAmount: 10,
  tradeDuration: 60,
  minConfidence: 65,
  dailyLossLimit: 50,
  dailyProfitTarget: 100,
  mode: 'MANUAL',
  botRunning: false,
  soundEnabled: true
};

chrome.runtime.onInstalled.addListener(async () => {
  try {
    const existing = await chrome.storage.local.get(Object.keys(DEFAULT_SETTINGS));
    const toSet = {};
    for (const [k, v] of Object.entries(DEFAULT_SETTINGS)) {
      if (existing[k] === undefined) toSet[k] = v;
    }
    if (Object.keys(toSet).length > 0) {
      await chrome.storage.local.set(toSet);
    }
  } catch (e) {}
});

chrome.runtime.onMessage.addListener((msg, sender, sendResponse) => {
  if (msg.type === 'FETCH_SIGNAL') {
    handleFetchSignal(msg.payload).then(sendResponse).catch(err => {
      sendResponse({ success: false, error: err.message });
    });
    return true;
  }
  if (msg.type === 'LOG_TRADE') {
    handleLogTrade(msg.payload).then(sendResponse).catch(err => {
      sendResponse({ success: false, error: err.message });
    });
    return true;
  }
  if (msg.type === 'RECORD_CANDLE_OUTCOME') {
    handleRecordCandleOutcome(msg.payload).then(sendResponse).catch(err => {
      sendResponse({ success: false, error: err.message });
    });
    return true;
  }
  if (msg.type === 'GET_STATS') {
    handleGetStats().then(sendResponse).catch(err => {
      sendResponse({ success: false, error: err.message });
    });
    return true;
  }
  return false;
});

async function handleFetchSignal(payload) {
  try {
    const settings = await chrome.storage.local.get(['serverUrl', 'minConfidence']);
    const serverUrl = settings.serverUrl || DEFAULT_SETTINGS.serverUrl;
    const minConf = settings.minConfidence || DEFAULT_SETTINGS.minConfidence;

    const response = await fetch(`${serverUrl}/api/predict`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(payload)
    });
    if (!response.ok) throw new Error(`HTTP ${response.status}`);
    const data = await response.json();
    try {
      await chrome.storage.local.set({ lastSignal: data });
    } catch (e) {}

    // Trigger desktop notification for strong BUY / SELL signals
    if (data.signal !== 'WAIT' && data.confidence >= minConf) {
      try {
        chrome.notifications.create({
          type: 'basic',
          iconUrl: chrome.runtime.getURL('src/assets/icon128.png'),
          title: `🤖 AI Signal: ${data.signal} (${data.pair})`,
          message: `Confidence: ${data.confidence}% | ${(data.reasons || [])[0] || 'Strong setup'}`
        });
      } catch (e) {}
    }
    return { success: true, data };
  } catch (e) {
    return { success: false, error: e.message };
  }
}

async function handleLogTrade(payload) {
  try {
    const settings = await chrome.storage.local.get(['serverUrl']);
    const serverUrl = settings.serverUrl || DEFAULT_SETTINGS.serverUrl;
    const response = await fetch(`${serverUrl}/api/log-trade`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(payload)
    });
    const data = await response.json();
    return { success: true, data };
  } catch (e) {
    return { success: false, error: e.message };
  }
}

async function handleRecordCandleOutcome(payload) {
  try {
    const settings = await chrome.storage.local.get(['serverUrl']);
    const serverUrl = settings.serverUrl || DEFAULT_SETTINGS.serverUrl;
    const response = await fetch(`${serverUrl}/api/record-candle-outcome`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(payload)
    });
    if (!response.ok) throw new Error(`HTTP ${response.status}`);
    const data = await response.json();
    return { success: true, data };
  } catch (e) {
    return { success: false, error: e.message };
  }
}

async function handleGetStats() {
  try {
    const settings = await chrome.storage.local.get(['serverUrl']);
    const serverUrl = settings.serverUrl || DEFAULT_SETTINGS.serverUrl;
    const response = await fetch(`${serverUrl}/api/stats`);
    const data = await response.json();
    return { success: true, data };
  } catch (e) {
    return { success: false, error: e.message };
  }
}
