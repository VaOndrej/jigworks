// Renders the exchange and sends requests. Every number is computed by the Python backend and
// arrives as a string; nothing here calculates balances, fills, fees or PnL.
(() => {
  "use strict";
  const $ = (id) => document.getElementById(id);
  const TF_MS = { "1m": 60e3, "5m": 300e3, "15m": 900e3, "1h": 3600e3, "4h": 14400e3, "1d": 86400e3 };

  const app = {
    tf: "1m",
    side: "buy",
    maxOn: false,
    state: null,
    ws: null,
    priceLines: [],
    refPrice: null,
  };

  // ---- helpers ---------------------------------------------------------------------------------
  const num = (s) => (s === null || s === undefined || s === "" ? NaN : Number(s));
  const fmt = (s, dp) => (Number.isNaN(num(s)) ? "-" : num(s).toFixed(dp));
  const signed = (s, dp) => (num(s) > 0 ? "+" : "") + fmt(s, dp);
  const time = (ms) => new Date(ms).toISOString().slice(11, 19);
  const el = (tag, props = {}, ...kids) => {
    const node = document.createElement(tag);
    for (const [k, v] of Object.entries(props)) {
      if (k === "class") node.className = v;
      else if (k === "text") node.textContent = v;
      else if (k.startsWith("on")) node.addEventListener(k.slice(2), v);
      else node.setAttribute(k, v);
    }
    for (const kid of kids) node.append(kid);
    return node;
  };
  const api = async (method, path, body) => {
    const r = await fetch(path, {
      method,
      headers: body ? { "content-type": "application/json" } : {},
      body: body ? JSON.stringify(body) : undefined,
      credentials: "same-origin",
    });
    let data = null;
    try { data = await r.json(); } catch (_) { /* empty body */ }
    return { ok: r.ok, status: r.status, data };
  };

  // ---- chart -----------------------------------------------------------------------------------
  const LW = window.LightweightCharts;
  let chart = null, internal = null, reference = null, markers = null;
  if (LW) {
    chart = LW.createChart($("chart"), {
      autoSize: true,
      layout: { background: { type: "solid", color: "#161c24" }, textColor: "#dbe3ee" },
      grid: { vertLines: { color: "#212a37" }, horzLines: { color: "#212a37" } },
      timeScale: { timeVisible: true, secondsVisible: false },
      rightPriceScale: { borderColor: "#263040" },
    });
    internal = chart.addSeries(LW.CandlestickSeries, {
      upColor: "#26a69a", downColor: "#ef5350", borderVisible: false, wickUpColor: "#26a69a", wickDownColor: "#ef5350",
      priceFormat: { type: "price", precision: 2, minMove: 0.01 },
    });
    reference = chart.addSeries(LW.LineSeries, {
      color: "#f0b90b", lineWidth: 1, title: "Binance", priceLineVisible: true,
      priceFormat: { type: "price", precision: 2, minMove: 0.01 },
    });
    markers = LW.createSeriesMarkers(internal, []);
  } else {
    $("chart").append(el("div", {
      class: "missing",
      text: "The charting library is not installed (static/vendor/lightweight-charts). Trading still works.",
    }));
  }
  const toCandle = (c) => ({
    time: Math.floor(c.open_time_ms / 1000), open: num(c.open), high: num(c.high), low: num(c.low), close: num(c.close),
  });
  const toPoint = (c) => ({ time: Math.floor(c.open_time_ms / 1000), value: num(c.close) });

  async function loadCandles() {
    const [a, b] = await Promise.all([
      api("GET", `/api/candles?tf=${app.tf}`),
      api("GET", `/api/reference/candles?tf=${app.tf}`),
    ]);
    if (!chart) return;
    internal.setData((a.data || []).map(toCandle));
    reference.setData((b.data || []).map(toPoint));
    chart.timeScale().fitContent();
    drawMarkers();
  }

  function drawMarkers() {
    if (!markers || !app.state) return;
    const ms = TF_MS[app.tf];
    const list = app.state.fills.map((f) => ({
      time: Math.floor(Math.floor(f.ms / ms) * ms / 1000),
      position: f.side === "buy" ? "belowBar" : "aboveBar",
      color: f.side === "buy" ? "#26a69a" : "#ef5350",
      shape: f.side === "buy" ? "arrowUp" : "arrowDown",
      text: `${f.side} ${fmt(f.qty, 5)}`,
    }));
    list.sort((x, y) => x.time - y.time);
    markers.setMarkers(list);
  }

  function drawPriceLines() {
    if (!internal) return;
    for (const line of app.priceLines) internal.removePriceLine(line);
    app.priceLines = [];
    for (const o of app.state ? app.state.open_orders : []) {
      const price = o.type === "stop" ? o.stop_price : o.price;
      if (!price || o.status === "new") continue;
      const color = o.role === "sl" ? "#ef5350" : o.role === "tp" ? "#26a69a" : "#4c8dff";
      const tag = o.role === "sl" ? "SL" : o.role === "tp" ? "TP" : `${o.side.toUpperCase()} ${o.type}`;
      app.priceLines.push(internal.createPriceLine({
        price: num(price), color, lineWidth: 1, lineStyle: LW.LineStyle.Dashed,
        axisLabelVisible: true, title: `${tag} ${fmt(o.qty, 5)}`,
      }));
    }
  }

  // ---- ladder ----------------------------------------------------------------------------------
  function renderBook(book) {
    const maxQty = Math.max(1e-9, ...[...book.asks, ...book.bids].map(([, q]) => num(q)));
    const row = (cls, testid, [p, q]) => {
      const r = el("div", {
        class: `row ${cls}`, "data-testid": testid,
        onclick: () => { $("t-price").value = p; if ($("t-type").value === "market") { $("t-type").value = "limit"; syncTicket(); } },
      }, el("span", { text: fmt(p, 2) }), el("span", { text: fmt(q, 5) }));
      const bar = el("i", { class: "depth" });
      bar.style.width = `${Math.round((num(q) / maxQty) * 100)}%`;
      r.prepend(bar);
      return r;
    };
    $("asks").replaceChildren(...book.asks.map((l) => row("ask-row", "ladder-ask-row", l)));
    $("bids").replaceChildren(...book.bids.map((l) => row("bid-row", "ladder-bid-row", l)));
    const spread = book.asks.length && book.bids.length ? num(book.asks[0][0]) - num(book.bids[0][0]) : NaN;
    $("spread").textContent = Number.isNaN(spread) ? "-" : `spread ${spread.toFixed(2)}`;
  }

  // ---- summary and tabs ------------------------------------------------------------------------
  function paint(node, s) { node.classList.toggle("pos", num(s) > 0); node.classList.toggle("neg", num(s) < 0); }

  function renderState() {
    const s = app.state;
    if (!s) return;
    const a = s.account;
    $("s-equity").textContent = fmt(a.equity, 2);
    $("s-available").textContent = fmt(a.available_usd, 2);
    $("s-btc").textContent = fmt(a.btc, 5);
    $("s-realized").textContent = fmt(a.realized_pnl, 2);
    $("s-unrealized").textContent = fmt(a.unrealized_pnl, 2);
    $("s-return").textContent = `${signed(a.return_pct, 2)}%`;
    $("s-fees").textContent = fmt(a.fees_paid, 2);
    for (const [id, v] of [["s-realized", a.realized_pnl], ["s-unrealized", a.unrealized_pnl], ["s-return", a.return_pct]]) paint($(id), v);

    const p = s.position;
    const posRows = [el("tr", {}, ...["Qty (BTC)", "Avg cost", "Mark", "Unrealized PnL", ""].map((t) => el("th", { text: t })))];
    posRows.push(el("tr", {},
      el("td", { text: fmt(p.qty, 5) }), el("td", { text: num(p.qty) > 0 ? fmt(p.avg_cost, 2) : "-" }),
      el("td", { text: fmt(p.mark, 2) }), el("td", { text: fmt(p.unrealized, 2) }),
      el("td", {}, el("button", {
        "data-testid": "position-close", text: "Close position", onclick: closePosition,
        ...(num(p.qty) > 0 ? {} : { disabled: "" }),
      }))));
    $("position-table").replaceChildren(...posRows);

    const head = (cols) => el("tr", {}, ...cols.map((t) => el("th", { text: t })));
    const sideCell = (o) => el("td", { class: o.side === "buy" ? "buy-text" : "sell-text", text: o.side });
    const priceOf = (o) => (o.type === "stop" ? o.stop_price : o.price);
    $("open-table").replaceChildren(
      head(["Id", "Side", "Type", "Role", "Qty", "Filled", "Price", "Status", ""]),
      ...s.open_orders.map((o) => el("tr", {},
        el("td", { text: o.order_id }), sideCell(o), el("td", { text: o.type }), el("td", { text: o.role }),
        el("td", { text: fmt(o.qty, 5) }), el("td", { text: fmt(o.filled_qty, 5) }),
        el("td", { text: o.type === "market" ? "market" : fmt(priceOf(o), 2) }), el("td", { text: o.status }),
        el("td", {}, el("button", { "data-testid": "order-cancel", text: "Cancel", onclick: () => cancelOrder(o.order_id) })))));
    $("history-table").replaceChildren(
      head(["Time", "Id", "Side", "Type", "Role", "Qty", "Filled", "Price", "Status", "Reason"]),
      ...s.history.map((o) => el("tr", {},
        el("td", { text: time(o.created_ms) }), el("td", { text: o.order_id }), sideCell(o), el("td", { text: o.type }),
        el("td", { text: o.role }), el("td", { text: fmt(o.qty, 5) }), el("td", { text: fmt(o.filled_qty, 5) }),
        el("td", { text: o.type === "market" ? "market" : fmt(priceOf(o), 2) }),
        el("td", { text: o.status }), el("td", { text: o.reason || "" }))));
    drawPriceLines();
    drawMarkers();
  }

  async function loadState() {
    const r = await api("GET", "/api/state");
    if (r.ok) { app.state = r.data; renderState(); }
  }

  // ---- ticket ----------------------------------------------------------------------------------
  function syncTicket() {
    const type = $("t-type").value;
    $("row-price").hidden = type !== "limit";
    $("row-stop").hidden = type !== "stop";
    $("row-sltp").hidden = !(app.side === "buy" && type !== "stop");
    $("row-ro").hidden = app.side !== "sell";
    for (const id of ["t-qty", "t-usd"]) $(id).disabled = app.maxOn;
    $("t-max").setAttribute("aria-pressed", String(app.maxOn));
    const submit = $("t-submit");
    submit.textContent = `${app.side === "buy" ? "Buy" : "Sell"} BTC`;
    submit.className = `submit ${app.side}`;
    $("side-buy").classList.toggle("active", app.side === "buy");
    $("side-sell").classList.toggle("active", app.side === "sell");
  }

  function ticketBody() {
    const type = $("t-type").value;
    const body = { side: app.side, type };
    const qty = $("t-qty").value.trim(), usd = $("t-usd").value.trim();
    if (app.maxOn) body.max = true;
    else if (qty) body.qty = qty;
    else if (usd) body.quote_amount = usd;
    if (type === "limit" && $("t-price").value.trim()) body.price = $("t-price").value.trim();
    if (type === "stop" && $("t-stop").value.trim()) body.stop_price = $("t-stop").value.trim();
    if (app.side === "buy" && type !== "stop") {
      if ($("t-sl").value.trim()) body.sl = $("t-sl").value.trim();
      if ($("t-tp").value.trim()) body.tp = $("t-tp").value.trim();
    }
    if (app.side === "sell" && $("t-ro").checked) body.reduce_only = true;
    return body;
  }

  async function submitOrder() {
    $("t-error").textContent = "";
    const r = await api("POST", "/api/orders", ticketBody());
    if (!r.ok) {
      $("t-error").textContent = ((r.data && r.data.reason) || `error ${r.status}`).replaceAll("_", " ");
    }
    await loadState();
  }

  async function cancelOrder(id) {
    await api("DELETE", `/api/orders/${id}`);
    await loadState();
  }

  async function closePosition() {
    const r = await api("POST", "/api/position/close");
    $("t-error").textContent = r.ok ? "" : ((r.data && r.data.reason) || "error").replaceAll("_", " ");
    await loadState();
  }

  async function resetAccount() {
    const r = await api("POST", "/api/account/reset");
    if (r.ok) { app.state = r.data.state; renderState(); }
  }

  // ---- websocket -------------------------------------------------------------------------------
  function badge(status, ageMs) {
    const b = $("feed-status");
    b.textContent = ageMs === null || ageMs === undefined ? status : `${status} · ${Math.round(ageMs / 1000)}s`;
    b.className = `badge ${status}`;
  }

  function onMessage(m) {
    switch (m.type) {
      case "reference":
        app.refPrice = m.price;
        $("ref-price").textContent = fmt(m.price, 2);
        badge(m.status, 0);
        break;
      case "trade":
        $("last-price").textContent = fmt(m.price, 2);
        break;
      case "book":
        renderBook(m);
        break;
      case "candle":
        if (m.tf !== app.tf || !chart) break;
        if (m.source === "internal") internal.update(toCandle(m));
        else reference.update(toPoint(m));
        break;
      case "state":
        app.state = m;
        renderState();
        break;
      default:
        break;
    }
  }

  function connect() {
    const ws = new WebSocket(`${location.protocol === "https:" ? "wss:" : "ws:"}//${location.host}/ws`);
    app.ws = ws;
    ws.onopen = () => {
      ws.send(JSON.stringify({ type: "subscribe", tf: app.tf }));
      loadAll();
    };
    ws.onmessage = (e) => onMessage(JSON.parse(e.data));
    ws.onclose = () => setTimeout(connect, 1000);
  }

  async function loadAll() {
    const [book] = await Promise.all([api("GET", "/api/book?depth=20"), loadState(), loadCandles()]);
    if (book.ok) renderBook(book.data);
    const t = await api("GET", "/api/trades?limit=1");
    if (t.ok && t.data.length) $("last-price").textContent = fmt(t.data[0].price, 2);
  }

  async function pollHealth() {
    const r = await api("GET", "/healthz");
    if (r.ok) {
      badge(r.data.status, r.data.last_tick_age_ms);
      if (r.data.reference_price) $("ref-price").textContent = fmt(r.data.reference_price, 2);
    }
  }

  // ---- wiring ----------------------------------------------------------------------------------
  $("side-buy").onclick = () => { app.side = "buy"; syncTicket(); };
  $("side-sell").onclick = () => { app.side = "sell"; syncTicket(); };
  $("t-type").onchange = syncTicket;
  $("t-max").onclick = () => {
    app.maxOn = !app.maxOn;
    if (app.maxOn) { $("t-qty").value = ""; $("t-usd").value = ""; }
    syncTicket();
  };
  $("t-qty").oninput = () => { $("t-usd").value = ""; };
  $("t-usd").oninput = () => { $("t-qty").value = ""; };
  $("t-submit").onclick = submitOrder;
  $("reset").onclick = resetAccount;
  for (const b of document.querySelectorAll("#tf-bar button")) {
    b.onclick = () => {
      app.tf = b.dataset.tf;
      for (const x of document.querySelectorAll("#tf-bar button")) x.classList.toggle("active", x === b);
      if (app.ws && app.ws.readyState === WebSocket.OPEN) app.ws.send(JSON.stringify({ type: "subscribe", tf: app.tf }));
      loadCandles();
    };
  }
  for (const b of document.querySelectorAll(".tabs nav button")) {
    b.onclick = () => {
      for (const x of document.querySelectorAll(".tabs nav button")) x.classList.toggle("active", x === b);
      for (const p of document.querySelectorAll(".panel")) p.hidden = p.id !== `panel-${b.dataset.tab}`;
    };
  }

  syncTicket();
  connect();
  pollHealth();
  setInterval(pollHealth, 2000);
})();
