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
  await Promise.all([loadOverview(), loadLatest(), loadAgents(), loadLogs()]);
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

  const tb = $("#predictor-table tbody");
  tb.innerHTML = "";
  for (const p of o.predictors) {
    const acc = p.accuracy !== null ? `${Math.round(p.accuracy * 100)}%` : "–";
    tb.insertAdjacentHTML("beforeend",
      `<tr><td>${p.predictor}</td><td>${p.hits}/${p.total}</td><td>${acc}</td></tr>`);
  }
}

async function loadLatest() {
  const d = await getJSON("/api/latest");
  $("#latest-date").textContent = d.cycle_date ? `(${d.cycle_date})` : "";
  const tb = $("#latest-table tbody");
  tb.innerHTML = "";
  if (!d.rows || !d.rows.length) {
    tb.innerHTML = `<tr><td colspan="7" class="muted">아직 예측이 없습니다. '새 사이클 실행'을 눌러주세요.</td></tr>`;
    $("#detail").innerHTML = "";
    return;
  }
  for (const row of d.rows) {
    const e = row.ensemble;
    const actual = row.actual_return_pct;
    const hit = actual === null || actual === undefined ? "–"
      : ((actual > 0.2 ? "up" : actual < -0.2 ? "down" : "flat") === e.direction ? "✅" : "❌");
    tb.insertAdjacentHTML("beforeend",
      `<tr><td>${row.name}</td><td>${row.market}</td>
       <td class="${dirClass(e.direction)}">${dirLabel(e.direction)}</td>
       <td class="${dirClass(e.direction)}">${pct(e.expected_return_pct)}</td>
       <td>${Math.round(e.confidence * 100)}%</td>
       <td>${pct(actual)}</td><td>${hit}</td></tr>`);
  }
  renderDetail(d.rows);
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
