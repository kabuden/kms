const $ = (sel) => document.querySelector(sel);
const dirClass = (d) => d === "up" ? "up" : d === "down" ? "down" : "flat";
const dirLabel = (d) => d === "up" ? "▲ 상승" : d === "down" ? "▼ 하락" : "● 보합";
const pct = (v) => v === null || v === undefined ? "–" : `${v > 0 ? "+" : ""}${v}%`;

async function getJSON(url) {
  const r = await fetch(url);
  return r.json();
}
async function postJSON(url, body) {
  const r = await fetch(url, {
    method: "POST", headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body || {}),
  });
  return r.json();
}

async function refreshAll() {
  await Promise.all([loadOverview(), loadLatest(), loadAgents(), loadLogs(), loadSchedule()]);
}

async function loadOverview() {
  const o = await getJSON("/api/overview");
  const c = o.confidence || {};
  $("#m-cycles").textContent = o.cycles ?? "0";
  $("#m-ens-acc").textContent = o.ensemble_accuracy !== null
    ? `${Math.round(o.ensemble_accuracy * 100)}%` : "–";
  $("#m-roll-acc").textContent = c.rolling_accuracy !== undefined
    ? `${Math.round(c.rolling_accuracy * 100)}%` : "–";
  $("#m-calib").textContent = c.calibrated_confidence !== undefined
    ? `${Math.round(c.calibrated_confidence * 100)}%` : "–";

  const banner = $("#trust-banner");
  if (c.trade_ready) {
    banner.className = "banner ready";
    banner.textContent = `✅ 실거래 검증 단계 도달 — ${c.detail || ""}`;
  } else {
    banner.className = "banner learning";
    banner.textContent = `🧪 학습/검증 단계 — ${c.detail
      || `사이클 ${o.cycles}/${o.min_cycles_for_trust}, 목표정확도 ${Math.round(o.min_accuracy_for_trust*100)}%`}`;
  }

  // 뉴스 반영 효과: 수정 예측 정확도 vs 1차 예측 정확도
  const nv = $("#news-value-note");
  if (o.news_value !== null && o.news_value !== undefined) {
    const sign = o.news_value > 0 ? "+" : "";
    const verdict = o.news_value > 0 ? "뉴스가 적중도를 높임 👍"
      : o.news_value < 0 ? "뉴스가 오히려 적중도를 낮춤 👎" : "뉴스 효과 중립";
    nv.textContent = `뉴스 반영 효과: 1차 ${Math.round((o.baseline_accuracy||0)*100)}% → `
      + `수정 ${Math.round((o.ensemble_accuracy||0)*100)}% (${sign}${Math.round(o.news_value*100)}%p) · ${verdict}`;
  } else {
    nv.textContent = "";
  }

  const tb = $("#predictor-table tbody");
  tb.innerHTML = "";
  for (const p of o.predictors) {
    const acc = p.accuracy !== null ? `${Math.round(p.accuracy * 100)}%` : "–";
    tb.insertAdjacentHTML("beforeend",
      `<tr><td>${p.predictor}</td><td>${p.hits}/${p.total}</td><td>${acc}</td></tr>`);
  }
}

function actualDir(v) {
  return v > 0.2 ? "up" : v < -0.2 ? "down" : "flat";
}

async function loadLatest() {
  const d = await getJSON("/api/latest");
  $("#latest-date").textContent = d.cycle_date ? `(${d.cycle_date})` : "";
  $("#news-date").textContent = d.cycle_date ? `(${d.cycle_date})` : "";
  renderNews(d.news);
  const tb = $("#latest-table tbody");
  tb.innerHTML = "";
  if (!d.rows || !d.rows.length) {
    tb.innerHTML = `<tr><td colspan="8" class="muted">아직 예측이 없습니다. '오늘 하루 실행'을 눌러주세요.</td></tr>`;
    $("#detail").innerHTML = "";
    return;
  }
  for (const row of d.rows) {
    const e = row.ensemble;                 // 수정(뉴스반영) 예측
    const b = row.baseline;                 // 1차 예측
    const actual = row.actual_return_pct;
    const hit = actual === null || actual === undefined ? "–"
      : (actualDir(actual) === e.direction ? "✅" : "❌");
    const baseCell = b
      ? `<span class="${dirClass(b.direction)}">${dirLabel(b.direction)} ${pct(b.expected_return_pct)}</span>`
      : "–";
    const delta = row.delta_pct;
    const deltaCell = delta === null || delta === undefined ? "–"
      : `<span class="${delta > 0 ? "up" : delta < 0 ? "down" : "flat"}">${pct(delta)}</span>`
        + (row.direction_changed ? ' <span class="pill">방향전환</span>' : "");
    tb.insertAdjacentHTML("beforeend",
      `<tr><td>${row.name}</td><td>${row.market}</td>
       <td>${baseCell}</td>
       <td class="${dirClass(e.direction)}"><b>${dirLabel(e.direction)} ${pct(e.expected_return_pct)}</b></td>
       <td>${deltaCell}</td>
       <td>${Math.round(e.confidence * 100)}%</td>
       <td>${pct(actual)}</td><td>${hit}</td></tr>`);
  }
  renderDetail(d.rows);
}

function renderNews(news) {
  const box = $("#news-digest");
  if (!news || !Object.keys(news).length) {
    box.innerHTML = `<p class="muted">수집된 뉴스가 없습니다.</p>`;
    return;
  }
  const label = { US: "🇺🇸 미국", KR: "🇰🇷 한국" };
  box.innerHTML = Object.entries(news).map(([market, d]) => {
    const tone = d.avg_sentiment > 0.05 ? "up" : d.avg_sentiment < -0.05 ? "down" : "flat";
    const heads = (d.headlines || []).map(h =>
      `<li><span class="${h.sentiment > 0 ? "up" : h.sentiment < 0 ? "down" : "flat"}">●</span>
       ${h.title} <span class="muted">(${h.source})</span></li>`).join("");
    return `<div class="news-block">
      <h3>${label[market] || market} · ${d.count}건 ·
        평균감성 <span class="${tone}">${d.avg_sentiment > 0 ? "+" : ""}${d.avg_sentiment}</span></h3>
      <ul>${heads}</ul></div>`;
  }).join("");
}

function renderDetail(rows) {
  const box = $("#detail");
  box.innerHTML = "";
  for (const row of rows) {
    const preds = (row.predictors || []).map(p =>
      `<tr><td>${p.predictor}</td>
        <td class="${dirClass(p.direction)}">${dirLabel(p.direction)}</td>
        <td>${pct(p.expected_return_pct)}</td>
        <td>${Math.round(p.confidence*100)}%</td>
        <td class="muted">${p.rationale || ""}</td></tr>`).join("");
    box.insertAdjacentHTML("beforeend",
      `<details class="detail-symbol">
        <summary>${row.name} (${row.symbol}) — 앙상블 ${dirLabel(row.ensemble.direction)} ${pct(row.ensemble.expected_return_pct)}</summary>
        <table><thead><tr><th>예측에이전트</th><th>방향</th><th>기대</th><th>신뢰</th><th>근거</th></tr></thead>
        <tbody>${preds}</tbody></table>
      </details>`);
  }
}

async function loadAgents() {
  const a = await getJSON("/api/agents");
  const box = $("#roster");
  const group = (title, arr) =>
    `<div class="agent-group"><h3>${title}</h3>` +
    arr.map(x => `<div class="agent"><b>${x.name}</b> — ${x.description}</div>`).join("") +
    `</div>`;
  box.innerHTML =
    group("📰 수집 에이전트 (2)", a.collectors) +
    group("🧠 예측 에이전트 (5)", a.predictors) +
    group("🔧 발전 에이전트 (3)", a.improvers);
}

async function loadLogs() {
  const d = await getJSON("/api/improver-logs");
  const box = $("#improver-logs");
  box.innerHTML = (d.logs || []).map(l =>
    `<div class="log-row"><span class="who">${l.improver}</span>
     <span class="muted">[${l.cycle_date}] ${l.action}</span><br>${l.detail}</div>`
  ).join("") || `<p class="muted">로그가 없습니다.</p>`;
}

async function loadSchedule() {
  const d = await getJSON("/api/schedule");
  const today = $("#schedule-today");
  today.textContent = d.is_trading_day
    ? `(${d.today} · 거래일 · 현재 ${d.now_utc} UTC)`
    : `(${d.today} · 비거래일)`;

  const grid = $("#schedule-slots");
  grid.innerHTML = (d.slots || []).map(s => {
    let icon, cls, hint;
    if (!d.is_trading_day) {
      icon = "🔕"; cls = "slot-off"; hint = "비거래일";
    } else if (s.done) {
      icon = "✅"; cls = "slot-done"; hint = "완료";
    } else if (s.past_due) {
      icon = "⏳"; cls = "slot-running"; hint = "실행 중/대기";
    } else {
      icon = "🔜"; cls = "slot-pending"; hint = "예정";
    }
    return `<div class="slot-card ${cls}">
      <div class="slot-time">${s.scheduled_utc} UTC</div>
      <div class="slot-icon">${icon}</div>
      <div class="slot-label">${s.label}</div>
      <div class="slot-hint muted">${hint}</div>
      <button class="slot-btn" onclick="runSlot(${s.slot})"
        ${s.done ? "disabled" : ""}>즉시 실행</button>
    </div>`;
  }).join("");

  const logBox = $("#schedule-log");
  logBox.innerHTML = (d.recent_log || []).map(l => {
    const icon = l.status === "ok" ? "✅" : l.status === "manual" ? "🖱️" : "❌";
    return `<div class="log-row">
      <span class="who">${icon} 슬롯 ${l.slot}</span>
      <span class="muted">[${l.cycle_date}] ${l.ran_at ? l.ran_at.slice(0,16).replace('T',' ') + ' UTC' : ''}</span>
      <br>${l.detail}</div>`;
  }).join("") || `<p class="muted">아직 실행 기록이 없습니다.</p>`;
}

async function runSlot(slot) {
  const statusEl = $("#run-status");
  statusEl.textContent = `슬롯 ${slot} 실행 중…`;
  const btns = document.querySelectorAll(".slot-btn");
  btns.forEach(b => b.disabled = true);
  try {
    const r = await postJSON("/api/run-slot", { slot });
    statusEl.textContent = r.ok ? `슬롯 ${slot} 완료` : `오류: ${r.error}`;
  } finally {
    await refreshAll();
  }
}

async function runCycle(n) {
  const btn = $("#btn-run"), btn10 = $("#btn-run10");
  btn.disabled = btn10.disabled = true;
  for (let i = 0; i < n; i++) {
    $("#run-status").textContent = `사이클 실행 중… (${i + 1}/${n})`;
    await postJSON("/api/run-cycle", {});
  }
  $("#run-status").textContent = `완료: ${n} 사이클 실행됨`;
  btn.disabled = btn10.disabled = false;
  await refreshAll();
}

$("#btn-run").addEventListener("click", () => runCycle(1));
$("#btn-run10").addEventListener("click", () => runCycle(10));
refreshAll();
