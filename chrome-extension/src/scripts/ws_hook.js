// Page-context WebSocket & Canvas Live Price Interceptor for https://market-qx.info/en/trade & Quotex
(function() {
  'use strict';
  // Stealth hook gate using unguessable internal symbol to avoid window property pollution
  const HOOK_GATE = Symbol.for('__qx_sock_gate__');
  if (window[HOOK_GATE]) return;
  try {
    Object.defineProperty(window, HOOK_GATE, {
      value: true,
      writable: false,
      configurable: false,
      enumerable: false
    });
  } catch (e) {
    window[HOOK_GATE] = true;
  }

  let privateActiveWsAsset = null;
  const hookedSockets = new WeakSet();
  const parsedEvents = new WeakSet();

  function emitTick(asset, price, timestamp, rawPriceStr) {
    const p = parseFloat(price);
    if (!Number.isFinite(p) || p <= 0 || p > 1e7) return;
    const ts = (typeof timestamp === 'number' && timestamp > 1e9)
      ? (timestamp < 1e11 ? Math.round(timestamp * 1000) : Math.round(timestamp))
      : Date.now();

    let decimals = null;
    if (typeof rawPriceStr === 'string' && rawPriceStr.includes('.')) {
      decimals = rawPriceStr.split('.')[1].length;
    }

    window.postMessage({
      source: 'AI_BOT_WS_TICK',
      asset: asset || null,
      timestamp: ts,
      price: p,
      decimals
    }, '*');
  }

  function handleRawData(raw) {
    if (!raw) return;
    if (typeof raw === 'string') {
      parseWsPayload(raw);
    } else if (raw instanceof ArrayBuffer) {
      const text = new TextDecoder('utf-8').decode(new Uint8Array(raw));
      parseWsPayload(text);
    } else if (ArrayBuffer.isView(raw)) {
      const text = new TextDecoder('utf-8').decode(new Uint8Array(raw.buffer, raw.byteOffset, raw.byteLength));
      parseWsPayload(text);
    } else if (typeof Blob !== 'undefined' && raw instanceof Blob) {
      raw.text().then((text) => {
        try { parseWsPayload(text); } catch (e) {}
      }).catch(() => {});
    }
  }

  // 1. Hook WebSocket Constructor (stealth proxy with native toString)
  const OriginalWebSocket = window.WebSocket;
  function HookedWebSocket(url, protocols) {
    const ws = protocols ? new OriginalWebSocket(url, protocols) : new OriginalWebSocket(url);
    hookedSockets.add(ws);
    ws.addEventListener('message', (event) => {
      try {
        parsedEvents.add(event);
        handleRawData(event.data);
      } catch (e) {}
    });
    return ws;
  }
  HookedWebSocket.prototype = OriginalWebSocket.prototype;
  Object.assign(HookedWebSocket, OriginalWebSocket);
  try {
    HookedWebSocket.toString = function() { return 'function WebSocket() { [native code] }'; };
  } catch (e) {}
  window.WebSocket = HookedWebSocket;

  // 2. Hook MessageEvent.prototype.data getter (catches ALREADY-OPEN WebSockets on existing tabs!)
  try {
    const origDataDesc = Object.getOwnPropertyDescriptor(MessageEvent.prototype, 'data');
    if (origDataDesc && typeof origDataDesc.get === 'function') {
      Object.defineProperty(MessageEvent.prototype, 'data', {
        configurable: true,
        enumerable: true,
        get: function() {
          const val = origDataDesc.get.call(this);
          try {
            if (!parsedEvents.has(this) && (this.target instanceof OriginalWebSocket || this.currentTarget instanceof OriginalWebSocket)) {
              parsedEvents.add(this);
              handleRawData(val);
            }
          } catch (e) {}
          return val;
        }
      });
    }
  } catch (e) {}

  // 3. Hook WebSocket.prototype.send (catches active asset subscriptions & attaches listener if needed)
  try {
    const origSend = OriginalWebSocket.prototype.send;
    OriginalWebSocket.prototype.send = function(data) {
      try {
        if (!hookedSockets.has(this)) {
          hookedSockets.add(this);
          this.addEventListener('message', (event) => {
            try {
              if (!parsedEvents.has(event)) {
                parsedEvents.add(event);
                handleRawData(event.data);
              }
            } catch (e) {}
          });
        }
        if (typeof data === 'string') {
          const m = data.match(/"asset"\s*:\s*"([^"]+)"/i);
          if (m && m[1]) {
            privateActiveWsAsset = m[1];
          }

          // Intercept User Live Trade Orders (High-Priority AI Learning)
          if (/orders\/open|deal\/open|"command"\s*:\s*"open"|"action"\s*:\s*"(call|put|buy|sell)"/i.test(data)) {
            try {
              let tradeDir = null;
              if (/"action"\s*:\s*"(call|buy|up)"/i.test(data) || /"dir"\s*:\s*"(call|buy|up)"/i.test(data)) tradeDir = 'BUY';
              else if (/"action"\s*:\s*"(put|sell|down)"/i.test(data) || /"dir"\s*:\s*"(put|sell|down)"/i.test(data)) tradeDir = 'SELL';

              const amtMatch = data.match(/"amount"\s*:\s*([0-9.]+)/i);
              const amount = amtMatch ? parseFloat(amtMatch[1]) : 1.0;
              const assetMatch = data.match(/"asset"\s*:\s*"([^"]+)"/i);
              const tradeAsset = assetMatch ? assetMatch[1] : privateActiveWsAsset;

              if (tradeDir) {
                window.postMessage({
                  source: 'AI_BOT_USER_TRADE_ENTERED',
                  asset: tradeAsset,
                  direction: tradeDir,
                  amount: amount,
                  timestamp: Date.now()
                }, '*');
              }
            } catch (e) {}
          }
        }
      } catch (e) {}
      return origSend.apply(this, arguments);
    };
  } catch (e) {}

  // 4. Parse Socket.IO / Quotex WebSocket JSON Payloads
  function parseWsPayload(raw) {
    if (!raw || typeof raw !== 'string') return;
    const idxBracket = raw.indexOf('[');
    const idxBrace = raw.indexOf('{');
    let startIdx = -1;
    if (idxBracket !== -1 && idxBrace !== -1) startIdx = Math.min(idxBracket, idxBrace);
    else if (idxBracket !== -1) startIdx = idxBracket;
    else if (idxBrace !== -1) startIdx = idxBrace;
    if (startIdx === -1) return;

    const clean = raw.slice(startIdx);
    let parsed;
    try { parsed = JSON.parse(clean); } catch { return; }

    extractFromNode(parsed, privateActiveWsAsset || null);
  }

  function isLikelyTimestamp(n) {
    return typeof n === 'number' && n > 1500000000 && n < 4000000000000;
  }

  function isLikelyPrice(n) {
    return typeof n === 'number' && Number.isFinite(n) && n > 0.00001 && n < 1000000;
  }

  function extractFromNode(node, inheritedAsset) {
    if (!node) return;

    if (Array.isArray(node)) {
      if (node.length === 0) return;

      // Pattern A: Socket.IO event wrapper ["quotes/stream", payload] or ["history/list/v2", payload]
      if (typeof node[0] === 'string' && node.length >= 2 && (Array.isArray(node[1]) || typeof node[1] === 'object')) {
        // Check if node itself is a single tick tuple: ["EURNZD_otc", 1728801234.56, 1.79842, 0]
        if (typeof node[1] === 'number' && typeof node[2] === 'number') {
          const assetName = node[0];
          const ts = isLikelyTimestamp(node[1]) ? node[1] : (isLikelyTimestamp(node[2]) ? node[2] : Date.now());
          const pr = isLikelyTimestamp(node[1]) ? node[2] : node[1];
          if (isLikelyPrice(pr)) {
            emitTick(assetName, pr, ts);
          }
          return;
        }
        // Extract asset if present in event payload
        let assetFromEvent = inheritedAsset;
        if (typeof node[1] === 'object' && node[1] !== null) {
          if (typeof node[1].asset === 'string') assetFromEvent = node[1].asset;
          else if (typeof node[1].symbol === 'string') assetFromEvent = node[1].symbol;
          else if (Array.isArray(node[1]) && typeof node[1][0] === 'string' && node[1][0].length >= 3 && !isLikelyPrice(node[1][0])) {
            assetFromEvent = node[1][0];
          }
        }
        extractFromNode(node[1], assetFromEvent);
        return;
      }

      // Pattern B: Tick tuple ["EURNZD_otc", 1728801234.56, 1.79842, 0]
      if (node.length >= 3 && typeof node[0] === 'string' && typeof node[1] === 'number' && typeof node[2] === 'number') {
        const assetName = node[0];
        const ts = isLikelyTimestamp(node[1]) ? node[1] : (isLikelyTimestamp(node[2]) ? node[2] : Date.now());
        const pr = isLikelyTimestamp(node[1]) ? node[2] : node[1];
        if (isLikelyPrice(pr)) {
          emitTick(assetName, pr, ts);
        }
        return;
      }

      // Pattern C: 2-element history point [timestamp, price]
      if (node.length === 2 && isLikelyTimestamp(node[0]) && isLikelyPrice(node[1])) {
        emitTick(inheritedAsset, node[1], node[0]);
        return;
      }

      // Pattern D: Array candle [timestamp, open, close, high, low] or [timestamp, open, high, low, close]
      if (node.length >= 5 && isLikelyTimestamp(node[0]) && isLikelyPrice(node[1]) && isLikelyPrice(node[2]) && isLikelyPrice(node[3]) && isLikelyPrice(node[4])) {
        const ts = node[0] < 1e11 ? Math.round(node[0] * 1000) : Math.round(node[0]);
        const v1 = node[1], v2 = node[2], v3 = node[3], v4 = node[4];
        const high = Math.max(v1, v2, v3, v4);
        const low = Math.min(v1, v2, v3, v4);
        const open = v1;
        // In Quotex array candles [ts, open, close, high, low], index 2 is close (or index 4 if OHLC)
        const close = (v3 === high || v4 === low) ? v2 : v4;
        window.postMessage({
          source: 'AI_BOT_WS_CANDLE',
          asset: inheritedAsset,
          candle: { timestamp: ts, open, high, low, close, volume: node[5] || 1000 }
        }, '*');
        emitTick(inheritedAsset, close, ts);
        return;
      }

      // Check if this is a batch of history candles: [[ts, o, c, h, l], ...]
      if (node.length > 5 && Array.isArray(node[0]) && node[0].length >= 5) {
        const batchCandles = [];
        const slice = node.length > 150 ? node.slice(-150) : node;
        for (let i = 0; i < slice.length; i++) {
          const item = slice[i];
          if (Array.isArray(item) && item.length >= 5 && isLikelyTimestamp(item[0])) {
            const ts = item[0] < 1e11 ? Math.round(item[0] * 1000) : Math.round(item[0]);
            const v1 = item[1], v2 = item[2], v3 = item[3], v4 = item[4];
            const high = Math.max(v1, v2, v3, v4);
            const low = Math.min(v1, v2, v3, v4);
            const open = v1;
            const close = (v3 === high || v4 === low) ? v2 : v4;
            batchCandles.push({ timestamp: ts, open, high, low, close, volume: item[5] || 1000 });
          }
        }
        if (batchCandles.length > 0) {
          window.postMessage({
            source: 'AI_BOT_WS_HISTORY',
            asset: inheritedAsset,
            candles: batchCandles
          }, '*');
          const lastCandle = batchCandles[batchCandles.length - 1];
          emitTick(inheritedAsset, lastCandle.close, lastCandle.timestamp);
          return;
        }
      }

      // Otherwise it's a list of items (e.g. batch of ticks or individual objects)
      // Process up to last 150 items so large history arrays stay fast
      const slice = node.length > 150 ? node.slice(-150) : node;
      for (let i = 0; i < slice.length; i++) {
        extractFromNode(slice[i], inheritedAsset);
      }
      return;
    }

    if (typeof node === 'object') {
      const asset = node.asset || node.symbol || node.pair || node.instrument || inheritedAsset;
      if (asset) privateActiveWsAsset = asset;

      if (node.open !== undefined && node.close !== undefined && node.high !== undefined && node.low !== undefined) {
        const c = {
          timestamp: node.time || node.timestamp || Date.now(),
          open: parseFloat(node.open),
          high: parseFloat(node.high),
          low: parseFloat(node.low),
          close: parseFloat(node.close),
          volume: parseFloat(node.volume || 1000)
        };
        window.postMessage({
          source: 'AI_BOT_WS_CANDLE',
          asset,
          candle: c
        }, '*');
        emitTick(asset, c.close, c.timestamp);
      } else if (node.price !== undefined || node.rate !== undefined || node.quote !== undefined) {
        const p = node.price ?? node.rate ?? node.quote;
        emitTick(asset, p, node.time || node.timestamp || Date.now());
      }

      if (Array.isArray(node.candles)) extractFromNode(node.candles, asset);
      if (Array.isArray(node.history)) extractFromNode(node.history, asset);
      if (Array.isArray(node.data)) extractFromNode(node.data, asset);
      if (Array.isArray(node.quotes)) extractFromNode(node.quotes, asset);
      if (Array.isArray(node.deals)) extractFromNode(node.deals, asset);
    }
  }

  // 5. Hook CanvasRenderingContext2D.prototype.fillText to read live price badge drawn on Quotex chart Y-axis
  try {
    const origFillText = CanvasRenderingContext2D.prototype.fillText;
    const PRICE_TEXT_RE = /^\s*(\d{1,6}\.\d{2,6})\s*$/;
    let lastCanvasPost = 0;

    CanvasRenderingContext2D.prototype.fillText = function(text, x, y) {
      try {
        if (typeof text === 'string' && text.length >= 4 && text.length <= 12) {
          const canvas = this.canvas;
          // Main chart canvas is large and Y-axis price labels are drawn on the right side (x > 70% of width)
          if (canvas && canvas.width > 350 && canvas.height > 200 && x > canvas.width * 0.68) {
            const m = text.match(PRICE_TEXT_RE);
            if (m) {
              const priceStr = m[1];
              const p = parseFloat(priceStr);
              if (isLikelyPrice(p)) {
                const fill = String(this.fillStyle || '').toLowerCase();
                // Quotex draws the active live price badge in bright white (#ffffff / #fff / rgb(255,255,255))
                // or bright contrasting color, while regular grid lines use muted grey
                const isBrightBadge = (
                  fill === '#ffffff' ||
                  fill === '#fff' ||
                  fill === 'rgb(255, 255, 255)' ||
                  fill === '#000000' ||
                  !priceStr.endsWith('0')
                );
                const now = Date.now();
                if (isBrightBadge && now - lastCanvasPost > 250) {
                  lastCanvasPost = now;
                  const decimals = priceStr.includes('.') ? priceStr.split('.')[1].length : 5;
                  window.postMessage({
                    source: 'AI_BOT_CANVAS_PRICE',
                    price: p,
                    decimals,
                    timestamp: now
                  }, '*');
                }
              }
            }
          }
        }
      } catch (e) {}
      return origFillText.apply(this, arguments);
    };
  } catch (e) {}
})();
