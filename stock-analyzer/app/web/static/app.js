const $ = (sel) => document.querySelector(sel);
const dirClass = (d) => d === "up" ? "up" : d === "down" ? "down" : "flat";
const dirLabel = (d) => d === "up" ? "▲ 상승" : d === "down" ? "▼ 하락" : "● 보합";
const pct = (v) => v === null || v === undefined ? "–" : `${v > 0 ? "+" : ""}${v}%`;
const price = (v) => {
  if (v === null || v === undefined) return "–";
  return v >= 1000 ? Math.round(v).toLocaleString() : v.toLocaleString();
};

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
  await Promise.all([loadOverview(), loadLatest(), loadAgents(), loadLogs(),
                     loadSchedule(), loadReports(), loadPortfolio(),
                     loadDiscoveries()]);
}

// ── 일일 리포트 ──
function mdToHtml(md) {
  const esc = (s) => s.replace(/&/g, "&amp;").replace(/</g, "&lt;").replace(/>/g, "&gt;");
  const inline = (s) => esc(s)
    .replace(/\*\*(.+?)\*\*/g, "<b>$1</b>")
    .replace(/_(.+?)_/g, "<i>$1</i>");
  const out = [];
  let inList = false;
  const closeList = () => { if (inList) { out.push("</ul>"); inList = false; } };
  for (const raw of md.split("\n")) {
    const line = raw.trimEnd();
    if (!line.trim()) { closeList(); continue; }
    if (line.startsWith("### ")) { closeList(); out.push(`<h4>${inline(line.slice(4))}</h4>`); }
    else if (line.startsWith("## ")) { closeList(); out.push(`<h3>${inline(line.slice(3))}</h3>`); }
    else if (line.startsWith("# ")) { closeList(); out.push(`<h2>${inline(line.slice(2))}</h2>`); }
    else if (line.startsWith("> ")) { closeList(); out.push(`<blockquote>${inline(line.slice(2))}</blockquote>`); }
    else if (line.startsWith("---")) { closeList(); out.push("<hr>"); }
    else if (line.startsWith("- ")) {
      if (!inList) { out.push("<ul>"); inList = true; }
      out.push(`<li>${inline(line.slice(2))}</li>`);
    } else { closeList(); out.push(`<p>${inline(line)}</p>`); }
  }
  closeList();
  return out.join("");
}

async function loadReports() {
  const d = await getJSON("/api/reports");
  const sel = $("#report-select");
  const reports = d.reports || [];
  if (!reports.length) {
    sel.innerHTML = "";
    $("#report-body").innerHTML = `<p class="muted">아직 작성된 리포트가 없습니다. 사이클 ④(평가)가 끝나면 생성됩니다.</p>`;
    $("#report-download").style.display = "none";
    return;
  }
  sel.innerHTML = reports.map(r => {
    const s = r.summary || {};
    const acc = s.next_close_total ? ` · 적중 ${s.next_close_hits}/${s.next_close_total}` : "";
    return `<option value="${r.cycle_date}">${r.cycle_date} (${s.weekday || ""})${acc}</option>`;
  }).join("");
  await loadReport(reports[0].cycle_date);
}

async function loadReport(date) {
  const r = await getJSON("/api/report?date=" + encodeURIComponent(date));
  $("#report-date").textContent = `(${r.cycle_date})`;
  $("#report-body").innerHTML = mdToHtml(r.markdown || "");
  const dl = $("#report-download");
  dl.href = "data:text/markdown;charset=utf-8," + encodeURIComponent(r.markdown || "");
  dl.setAttribute("download", `report-${r.cycle_date}.md`);
  dl.style.display = "inline-block";
}

document.addEventListener("change", (e) => {
  if (e.target && e.target.id === "report-select") loadReport(e.target.value);
});

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
    tb.innerHTML = `<tr><td colspan="8" class="muted">아직 예측이 없습니다. 스케줄이 자동으로 실행됩니다.</td></tr>`;
    $("#detail").innerHTML = "";
    return;
  }
  for (const row of d.rows) {
    const e = row.ensemble;
    const b = row.first;
    const actual = row.actual_return_pct;
    const hasActual = actual !== null && actual !== undefined;
    const hit = !hasActual ? "–" : (actualDir(actual) === e.direction ? "✅" : "❌");
    const baseCell = b
      ? `<span class="${dirClass(b.direction)}">${dirLabel(b.direction)} ${pct(b.expected_return_pct)}</span>`
      : "–";
    const delta = row.delta_pct;
    const deltaCell = delta === null || delta === undefined ? "–"
      : `<span class="${delta > 0 ? "up" : delta < 0 ? "down" : "flat"}">${pct(delta)}</span>`
        + (row.direction_changed ? ' <span class="pill">방향전환</span>' : "");
    // 정확도 지수(상대오차 기반) + 절대오차 병기. 절대오차가 같아도
    // 큰 변동을 맞힌 예측은 정확도가 더 높게 나온다.
    let accCell;
    if (!hasActual || row.accuracy_score === null || row.accuracy_score === undefined) {
      accCell = '<span class="muted">대기</span>';
    } else {
      const accPct = Math.round(row.accuracy_score * 100);
      const absErr = Math.abs(e.expected_return_pct - actual).toFixed(2);
      const accCls = accPct >= 80 ? "up" : accPct >= 50 ? "flat" : "down";
      accCell = `<span class="${accCls}"><b>${accPct}%</b></span> `
        + `<span class="muted">(${absErr}%p)</span>`;
    }
    const ownedStar = row.owned ? ' <span class="owned-star" title="보유 종목">⭐</span>' : "";
    // 예측값(신뢰도): 신뢰도는 예측값에 딸린 속성이므로 같은 칸에 묶는다.
    const officialCell = `<b>${dirLabel(e.direction)} ${pct(e.expected_return_pct)}</b>`
      + ` <span class="muted">(신뢰 ${Math.round(e.confidence * 100)}%)</span>`;
    tb.insertAdjacentHTML("beforeend",
      `<tr><td>${row.name}${ownedStar}</td><td>${row.market}</td>
       <td>${baseCell}</td>
       <td class="${dirClass(e.direction)}">${officialCell}</td>
       <td>${deltaCell}</td>
       <td>${pct(actual)}</td><td>${accCell}</td><td>${hit}</td></tr>`);
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
    const pointBlocks = (row.points || []).map(pt => {
      const preds = (pt.predictors || []).map(p =>
        `<tr><td>${p.predictor}</td>
          <td class="${dirClass(p.direction)}">${dirLabel(p.direction)}</td>
          <td>${pct(p.expected_return_pct)}</td>
          <td>${Math.round(p.confidence*100)}%</td>
          <td class="muted">${p.rationale || ""}</td></tr>`).join("");
      return `<div class="point-block">
        <div class="point-head">
          <b>${pt.label}</b>
          <span class="${dirClass(pt.direction)}">${dirLabel(pt.direction)} ${pct(pt.expected_return_pct)}</span>
          <span class="muted">신뢰 ${Math.round(pt.confidence*100)}% · 기준가 ${price(pt.base_price)} · ${pt.note}</span>
        </div>
        <table><thead><tr><th>예측에이전트</th><th>방향</th><th>기대</th><th>신뢰</th><th>근거</th></tr></thead>
        <tbody>${preds}</tbody></table>
      </div>`;
    }).join("");

    const hz = (row.horizons || []).map(h => {
      const actualCell = h.actual_price === null || h.actual_price === undefined
        ? '<span class="muted">대기</span>'
        : `${price(h.actual_price)} ${h.hit === 1 ? "✅" : h.hit === 0 ? "❌" : ""}`;
      return `<tr>
        <td>${h.label}</td>
        <td class="muted">${h.target_date}</td>
        <td><b>${price(h.target_price)}</b></td>
        <td class="${dirClass(h.direction)}">${dirLabel(h.direction)} ${pct(h.expected_return_pct)}</td>
        <td>${Math.round(h.confidence*100)}%</td>
        <td>${actualCell}</td>
      </tr>`;
    }).join("");
    const hzTable = hz
      ? `<div class="horizon-block">
          <div class="point-head"><b>📅 기간별 목표주가</b>
            <span class="muted">공식(미국개장후) 예측 기준 · 기준가 ${price(row.base_price)}</span></div>
          <table><thead><tr><th>기간</th><th>목표일</th><th>목표주가</th><th>예상 변화</th><th>신뢰</th><th>실제</th></tr></thead>
          <tbody>${hz}</tbody></table>
        </div>`
      : "";

    box.insertAdjacentHTML("beforeend",
      `<details class="detail-symbol">
        <summary>${row.name} (${row.symbol}) — 공식 ${dirLabel(row.ensemble.direction)} ${pct(row.ensemble.expected_return_pct)}
          · 다음종가 목표 ${price((row.horizons||[]).find(h=>h.horizon==="close")?.target_price)}</summary>
        ${hzTable}
        <div class="points-evolution">${pointBlocks}</div>
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
    ? `(${d.today} · 거래일 · 현재 ${d.now_kst} KST)`
    : `(${d.today} · 비거래일)`;

  const grid = $("#schedule-slots");
  grid.innerHTML = (d.points || []).map(s => {
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
    const roleTag = s.role === "evaluate" ? "평가·발전" : "예측";
    return `<div class="slot-card ${cls}">
      <div class="slot-time">${s.kst} KST</div>
      <div class="slot-icon">${icon}</div>
      <div class="slot-label">${s.label}</div>
      <div class="slot-hint muted">${roleTag} · ${hint}</div>
      <button class="slot-btn" onclick="runSlot(${s.point})"
        ${s.done ? "disabled" : ""}>즉시 실행</button>
    </div>`;
  }).join("");

  const logBox = $("#schedule-log");
  logBox.innerHTML = (d.recent_log || []).map(l => {
    const icon = l.status === "ok" ? "✅" : l.status === "manual" ? "🖱️" : "❌";
    return `<div class="log-row">
      <span class="who">${icon} 시점 ${l.slot}</span>
      <span class="muted">[${l.cycle_date}] ${l.ran_at ? l.ran_at.slice(0,16).replace('T',' ') + ' UTC' : ''}</span>
      <br>${l.detail}</div>`;
  }).join("") || `<p class="muted">아직 실행 기록이 없습니다.</p>`;
}

async function runSlot(point) {
  const statusEl = $("#run-status");
  if (statusEl) statusEl.textContent = `시점 ${point} 실행 중…`;
  document.querySelectorAll(".slot-btn").forEach(b => b.disabled = true);
  try {
    const r = await postJSON("/api/run-slot", { point });
    if (statusEl) statusEl.textContent = r.ok ? `시점 ${point} 완료` : `오류: ${r.error}`;
  } finally {
    await refreshAll();
  }
}

// ── 투자 제안 ──
async function loadPortfolio() {
  const d = await getJSON("/api/portfolio");
  const statusEl = $("#portfolio-status");
  const noteEl = $("#portfolio-note");

  if (!d.ready) {
    if (statusEl) statusEl.textContent = `(데이터 부족 — ${d.n_cycles}사이클)`;
    if (noteEl) noteEl.textContent = d.note;
    $("#us-buy").innerHTML = `<p class="muted">사이클이 쌓이면 자동으로 표시됩니다.</p>`;
    $("#kr-buy").innerHTML = `<p class="muted">사이클이 쌓이면 자동으로 표시됩니다.</p>`;
    $("#avoid-list").innerHTML = "";
    return;
  }

  const readyBadge = d.trade_ready
    ? `<span class="up">✅ 검증 완료</span>`
    : `<span class="flat">🧪 학습 단계</span>`;
  if (statusEl) statusEl.innerHTML = `${readyBadge} · ${d.cycle_date} · 정확도 ${Math.round(d.rolling_accuracy*100)}%`;
  if (noteEl) noteEl.textContent = d.note;

  const renderBuy = (list) => {
    if (!list || !list.length) return `<p class="muted">매수 후보 없음 (신뢰도 45% 미달 또는 하락 예측)</p>`;
    return list.map(c => {
      const barW = Math.min(100, c.weight_pct / 30 * 100).toFixed(0);
      const star = c.owned ? ' <span class="owned-star" title="보유 종목">⭐</span>' : "";
      return `<div class="portfolio-card">
        <div class="pc-header">
          <span class="pc-name">${c.name}${star}</span>
          <span class="pc-weight ${d.trade_ready ? "up" : "flat"}">${c.weight_pct}%</span>
        </div>
        <div class="pc-detail">
          <span class="up">▲ ${pct(c.expected_return_pct)}</span>
          <span class="muted">신뢰 ${Math.round(c.confidence*100)}%</span>
          <span class="muted">기준가 ${price(c.base_price)}</span>
        </div>
        <div class="alloc-bar-wrap"><div class="alloc-bar" style="width:${barW}%"></div></div>
      </div>`;
    }).join("");
  };

  const renderAvoid = (list) => {
    if (!list || !list.length) return `<p class="muted">회피 후보 없음</p>`;
    return list.map(c =>
      `<span class="pill down">${c.name}${c.owned ? " ⭐" : ""} ▼ ${pct(c.expected_return_pct)} (신뢰 ${Math.round(c.confidence*100)}%)</span>`
    ).join(" ");
  };

  $("#us-buy").innerHTML = renderBuy(d.us_buy);
  $("#kr-buy").innerHTML = renderBuy(d.kr_buy);
  $("#avoid-list").innerHTML = renderAvoid(d.avoid);
}

// ── 신규 종목 발견 ──
async function loadDiscoveries() {
  const d = await getJSON("/api/discoveries");
  const list = d.discoveries || [];
  const countEl = $("#discovery-count");
  if (countEl) countEl.textContent = list.length ? `(${list.length}건)` : "(없음)";
  const box = $("#discovery-list");
  if (!box) return;
  if (!list.length) {
    box.innerHTML = `<p class="muted">뉴스에서 새로운 종목이 감지되면 여기에 표시됩니다.</p>`;
    return;
  }
  const marketLabel = { US: "🇺🇸", KR: "🇰🇷" };
  box.innerHTML = list.map(c => `
    <div class="discovery-card" id="dc-${c.symbol.replace(/[^a-zA-Z0-9]/g,'_')}">
      <div class="dc-info">
        <div class="dc-name">${marketLabel[c.market] || ""} ${c.name} <span class="muted">(${c.symbol})</span></div>
        <div class="dc-meta">뉴스 언급 ${c.mentions}회 · 마지막 ${(c.last_seen||"").slice(0,10)} · ${c.reason || ""}</div>
      </div>
      <button class="dc-btn" onclick="dismissDiscovery('${c.symbol}')">무시</button>
    </div>`).join("");
}

async function dismissDiscovery(symbol) {
  await postJSON("/api/discoveries/dismiss", { symbol });
  const id = "dc-" + symbol.replace(/[^a-zA-Z0-9]/g, "_");
  const el = document.getElementById(id);
  if (el) el.remove();
  const box = $("#discovery-list");
  const remaining = box ? box.querySelectorAll(".discovery-card").length : 0;
  if (box && !remaining) {
    box.innerHTML = `<p class="muted">뉴스에서 새로운 종목이 감지되면 여기에 표시됩니다.</p>`;
  }
  const countEl = $("#discovery-count");
  if (countEl) countEl.textContent = remaining ? `(${remaining}건)` : "(없음)";
}

refreshAll();
