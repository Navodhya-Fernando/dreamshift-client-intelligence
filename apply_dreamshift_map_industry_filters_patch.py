#!/usr/bin/env python3
from __future__ import annotations

import hashlib
import shutil
from datetime import datetime
from pathlib import Path


def replace_once(text: str, old: str, new: str, label: str) -> str:
    if old not in text:
        raise SystemExit(
            f"Could not find expected {label} block. "
            "The dashboard may not be on the dark-glass version yet."
        )
    return text.replace(old, new, 1)


def replace_between(
    text: str,
    start: str,
    end: str,
    replacement: str,
    label: str,
) -> str:
    start_index = text.find(start)
    if start_index < 0:
        raise SystemExit(f"Could not find start of {label}.")
    end_index = text.find(end, start_index)
    if end_index < 0:
        raise SystemExit(f"Could not find end of {label}.")
    return text[:start_index] + replacement + "\n\n" + text[end_index:]


def main() -> int:
    root = Path.cwd().resolve()
    html_path = root / "app" / "templates" / "dashboard.html"
    css_path = root / "app" / "static" / "styles.css"
    js_path = root / "app" / "static" / "app.js"

    for path in (html_path, css_path, js_path):
        if not path.exists():
            raise SystemExit(
                f"Missing {path}. Run this script from the standalone "
                "dashboard project root."
            )

    stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    backup_dir = root / ".patch_backups" / f"map_industry_filters_{stamp}"
    for path in (html_path, css_path, js_path):
        destination = backup_dir / path.relative_to(root)
        destination.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(path, destination)

    html = html_path.read_text(encoding="utf-8")
    css = css_path.read_text(encoding="utf-8")
    js = js_path.read_text(encoding="utf-8")

    html = html.replace(
        "/static/styles.css?v=20260802b",
        "/static/styles.css?v=20260802c",
    )
    html = html.replace(
        "/static/app.js?v=20260802b",
        "/static/app.js?v=20260802c",
    )

    html = replace_once(
        html,
        """        <div class="hero-side">
          <div class="hero-pill">Dark UI • Glassmorphism • Interactive Charts</div>
          <div class="hero-actions">""",
        """        <div class="hero-side">
          <div class="hero-actions">""",
        "hero label",
    )

    html = replace_once(
        html,
        """      <section class="active-filters glass-soft" id="activeFilters"></section>""",
        """      <section class="filter-toolbar glass-soft" id="activeFilters">
        <div class="inline-filter-grid">
          <label class="inline-filter">
            <span>State</span>
            <select id="quickFilterState"></select>
          </label>
          <label class="inline-filter">
            <span>Industry</span>
            <select id="quickFilterIndustry"></select>
          </label>
          <label class="inline-filter">
            <span>Role family</span>
            <select id="quickFilterRoleFamily"></select>
          </label>
          <label class="inline-filter">
            <span>Visa</span>
            <select id="quickFilterVisa"></select>
          </label>
        </div>
        <div class="inline-filter-actions">
          <button id="moreFiltersBtn" class="ghost-btn compact">More filters</button>
          <button id="inlineResetFiltersBtn" class="ghost-btn compact">Clear all</button>
        </div>
        <div id="activeFilterChips" class="active-filter-chips"></div>
      </section>""",
        "inline filter toolbar",
    )

    html = replace_once(
        html,
        """          <article class="card glass tall">
            <div class="card-head">
              <div>
                <span class="eyebrow">Portfolio mix</span>
                <h3>Top industries</h3>
              </div>
            </div>
            <div id="industryTreemap" class="chart chart-lg"></div>
          </article>""",
        """          <article class="card glass tall industry-card">
            <div class="card-head industry-card-head">
              <div>
                <span class="eyebrow">Portfolio mix</span>
                <h3>Industry concentration</h3>
                <p class="card-subtitle">Ranked by the currently filtered DreamShift client portfolio.</p>
              </div>
              <div class="chart-controls">
                <label>
                  <span>Measure</span>
                  <select id="industryMetricMode">
                    <option value="count">Client count</option>
                    <option value="percentage">Portfolio share</option>
                  </select>
                </label>
                <label>
                  <span>Display</span>
                  <select id="industryTopLimit">
                    <option value="6">Top 6</option>
                    <option value="10" selected>Top 10</option>
                    <option value="15">Top 15</option>
                  </select>
                </label>
              </div>
            </div>
            <div id="industryInsightStrip" class="industry-insight-strip"></div>
            <div id="industryRankChart" class="chart chart-lg"></div>
            <div id="industryNarrative" class="industry-narrative"></div>
          </article>""",
        "industry chart card",
    )

    css_append = r"""

/* -------------------------------------------------------------------------
   V3.1: interactive Australia map, ranked industry intelligence and inline
   filters. These rules intentionally override the original tile/treemap UI.
   ------------------------------------------------------------------------- */
.filter-toolbar {
  display:grid;
  grid-template-columns:minmax(0,1fr) auto;
  align-items:end;
  gap:14px 16px;
  padding:14px 16px;
  min-height:unset;
}
.inline-filter-grid {
  display:grid;
  grid-template-columns:repeat(4,minmax(150px,1fr));
  gap:12px;
}
.inline-filter {
  display:flex;
  flex-direction:column;
  gap:7px;
}
.inline-filter > span,
.chart-controls label > span {
  color:rgba(255,255,255,.55);
  font-size:.66rem;
  font-weight:700;
  letter-spacing:.13em;
  text-transform:uppercase;
}
.inline-filter select,
.chart-controls select {
  height:42px;
  padding:0 38px 0 13px;
  border-radius:13px;
  border:1px solid rgba(255,255,255,.12);
  background:rgba(255,255,255,.06);
  color:#fff;
  font-size:.84rem;
  font-weight:600;
  outline:none;
}
.inline-filter select:focus,
.chart-controls select:focus {
  border-color:rgba(246,185,0,.62);
  box-shadow:0 0 0 3px rgba(246,185,0,.12);
}
.inline-filter-actions {
  display:flex;
  gap:9px;
  align-items:center;
  padding-bottom:1px;
}
.ghost-btn.compact {
  min-height:42px;
  padding:0 14px;
  white-space:nowrap;
}
.active-filter-chips {
  grid-column:1 / -1;
  display:flex;
  flex-wrap:wrap;
  gap:8px;
  min-height:0;
}
.active-filter-chips:empty { display:none; }

.au-layout {
  grid-template-columns:minmax(0,1.22fr) minmax(255px,.78fr);
  align-items:center;
}
.state-map {
  display:block;
  position:relative;
  min-height:352px;
  border-radius:20px;
  overflow:hidden;
  background:
    radial-gradient(circle at 56% 42%, rgba(246,185,0,.11), transparent 38%),
    linear-gradient(145deg, rgba(255,255,255,.045), rgba(255,255,255,.018));
  border:1px solid rgba(255,255,255,.075);
}
.au-map-svg {
  width:100%;
  height:352px;
  display:block;
  filter:drop-shadow(0 22px 28px rgba(0,0,0,.27));
}
.au-state-shape {
  stroke:rgba(255,255,255,.62);
  stroke-width:3;
  vector-effect:non-scaling-stroke;
  cursor:pointer;
  transition:filter .22s ease, opacity .22s ease, stroke .22s ease;
}
.au-state-shape:hover,
.au-state-shape.active {
  filter:brightness(1.22) drop-shadow(0 0 13px rgba(246,185,0,.42));
  stroke:#ffe500;
  opacity:1;
}
.au-map-label {
  pointer-events:none;
  fill:#fff;
  font-family:'Poppins',sans-serif;
  font-size:15px;
  font-weight:800;
  text-anchor:middle;
  paint-order:stroke;
  stroke:rgba(36,16,26,.78);
  stroke-width:4px;
  stroke-linejoin:round;
}
.au-map-count {
  pointer-events:none;
  fill:rgba(255,255,255,.84);
  font-family:'Poppins',sans-serif;
  font-size:11px;
  font-weight:600;
  text-anchor:middle;
  paint-order:stroke;
  stroke:rgba(36,16,26,.72);
  stroke-width:3px;
}
.map-tooltip {
  position:absolute;
  z-index:5;
  pointer-events:none;
  opacity:0;
  transform:translate(-50%,-112%);
  padding:9px 11px;
  border-radius:12px;
  background:rgba(20,8,17,.94);
  border:1px solid rgba(246,185,0,.35);
  box-shadow:0 14px 34px rgba(0,0,0,.38);
  color:#fff;
  font-size:.76rem;
  white-space:nowrap;
  transition:opacity .15s ease;
}
.map-tooltip strong { color:#ffe500; }
.map-legend {
  position:absolute;
  left:15px;
  bottom:13px;
  display:flex;
  align-items:center;
  gap:8px;
  color:rgba(255,255,255,.58);
  font-size:.68rem;
  font-weight:600;
}
.map-gradient {
  width:92px;
  height:7px;
  border-radius:999px;
  background:linear-gradient(90deg,#462239,#82515f,#d69f3a,#ffe500);
}
.mini-ranking {
  padding-right:4px;
  max-height:338px;
  scrollbar-color:rgba(255,255,255,.28) transparent;
}
.rank-row {
  padding:9px 10px;
  border-radius:13px;
  transition:background .2s ease, transform .2s ease;
  cursor:pointer;
}
.rank-row:hover {
  background:rgba(255,255,255,.055);
  transform:translateX(2px);
}

.industry-card-head { align-items:flex-end; }
.card-subtitle {
  margin:.42rem 0 0;
  color:rgba(255,255,255,.55);
  font-size:.78rem;
  font-weight:400;
}
.chart-controls {
  display:flex;
  align-items:flex-end;
  gap:10px;
}
.chart-controls label {
  display:flex;
  flex-direction:column;
  gap:6px;
}
.chart-controls select {
  min-width:125px;
  height:38px;
}
.industry-insight-strip {
  display:grid;
  grid-template-columns:repeat(3,minmax(0,1fr));
  gap:10px;
  margin:4px 0 12px;
}
.industry-insight {
  min-width:0;
  padding:12px 13px;
  border-radius:15px;
  background:linear-gradient(
    145deg,
    rgba(255,255,255,.07),
    rgba(255,255,255,.025)
  );
  border:1px solid rgba(255,255,255,.07);
}
.industry-insight span {
  display:block;
  color:rgba(255,255,255,.51);
  font-size:.63rem;
  font-weight:700;
  letter-spacing:.12em;
  text-transform:uppercase;
}
.industry-insight strong {
  display:block;
  margin-top:5px;
  color:#fff;
  font-size:1rem;
  font-weight:750;
  white-space:nowrap;
  overflow:hidden;
  text-overflow:ellipsis;
}
.industry-insight em {
  display:block;
  margin-top:3px;
  color:#f6b900;
  font-size:.72rem;
  font-style:normal;
  font-weight:650;
}
.industry-narrative {
  margin-top:4px;
  padding:11px 13px;
  border-left:3px solid #f6b900;
  border-radius:0 12px 12px 0;
  background:rgba(246,185,0,.075);
  color:rgba(255,255,255,.76);
  font-size:.78rem;
  line-height:1.55;
}
.industry-narrative strong { color:#fff; }

@media (max-width: 1220px) {
  .inline-filter-grid {
    grid-template-columns:repeat(2,minmax(150px,1fr));
  }
  .filter-toolbar { grid-template-columns:1fr; }
  .inline-filter-actions { justify-content:flex-start; }
}
@media (max-width: 720px) {
  .inline-filter-grid { grid-template-columns:1fr; }
  .industry-card-head {
    align-items:flex-start;
    flex-direction:column;
  }
  .chart-controls { width:100%; }
  .chart-controls label { flex:1; }
  .chart-controls select {
    width:100%;
    min-width:0;
  }
  .industry-insight-strip { grid-template-columns:1fr; }
  .au-map-svg { height:300px; }
  .state-map { min-height:300px; }
}
"""

    if "V3.1: interactive Australia map" not in css:
        css += css_append

    js = replace_between(
        js,
        "function renderActiveFilters() {",
        "function labelForFilterKey(key) {",
        r"""function renderActiveFilters() {
  const chips = Object.entries(APP.filters).filter(([,v]) => cap(v));
  const area = el('activeFilterChips');
  if (!area) return;
  if (!chips.length) {
    area.innerHTML = '';
    el('sidebarFilterSummary').textContent = 'All clients';
    return;
  }
  area.innerHTML = chips.map(([key, value]) => `
    <span class="filter-chip">${escapeHtml(labelForFilterKey(key))}: ${escapeHtml(value)} <button data-remove-filter="${key}">✕</button></span>
  `).join('');
  el('sidebarFilterSummary').textContent = chips
    .map(([key, value]) => `${labelForFilterKey(key)}: ${value}`)
    .join(' • ');
  qsa('[data-remove-filter]').forEach(btn =>
    btn.addEventListener('click', () => {
      delete APP.filters[btn.dataset.removeFilter];
      buildFilterOptions();
      filterRecords();
      renderAll();
    })
  );
}""",
        "active filter renderer",
    )

    js = replace_between(
        js,
        "function buildFilterOptions() {",
        "function renderKpis() {",
        r"""function buildFilterOptions() {
  const states = distribution(APP.rawRecords, 'Current State', 50)
    .map(x => x.label);
  const industries = distribution(APP.rawRecords, 'Primary Industry', 100)
    .map(x => x.label);
  const roleFamilies = distribution(APP.rawRecords, 'Role Family', 100)
    .map(x => x.label);
  const roles = distribution(APP.rawRecords, 'Primary Target Role', 200)
    .map(x => x.label);
  const visas = distribution(APP.rawRecords, 'Visa Category', 100)
    .map(x => x.label);
  const qualifications = distribution(
    APP.rawRecords,
    'Highest Qualification Level',
    100
  ).map(x => x.label);

  populateSelect('filterState', states, APP.filters.state || '');
  populateSelect('filterIndustry', industries, APP.filters.industry || '');
  populateSelect(
    'filterRoleFamily',
    roleFamilies,
    APP.filters.role_family || ''
  );
  populateSelect('filterRole', roles, APP.filters.role || '');
  populateSelect('filterVisa', visas, APP.filters.visa || '');
  populateSelect(
    'filterQualification',
    qualifications,
    APP.filters.qualification || ''
  );

  populateSelect('quickFilterState', states, APP.filters.state || '');
  populateSelect(
    'quickFilterIndustry',
    industries,
    APP.filters.industry || ''
  );
  populateSelect(
    'quickFilterRoleFamily',
    roleFamilies,
    APP.filters.role_family || ''
  );
  populateSelect('quickFilterVisa', visas, APP.filters.visa || '');
}""",
        "filter option builder",
    )

    js = replace_between(
        js,
        "function renderStateExplorer() {",
        "function chartTheme() {",
        r"""function canonicalStateCode(value) {
  const token = norm(value).replace(/\./g, '');
  const aliases = {
    'wa':'WA', 'western australia':'WA',
    'nt':'NT', 'northern territory':'NT',
    'sa':'SA', 'south australia':'SA',
    'qld':'QLD', 'queensland':'QLD',
    'nsw':'NSW', 'new south wales':'NSW',
    'act':'ACT', 'australian capital territory':'ACT',
    'vic':'VIC', 'victoria':'VIC',
    'tas':'TAS', 'tasmania':'TAS',
  };
  return aliases[token] || cap(value).toUpperCase();
}

function stateName(code) {
  return ({
    WA:'Western Australia',
    NT:'Northern Territory',
    SA:'South Australia',
    QLD:'Queensland',
    NSW:'New South Wales',
    ACT:'Australian Capital Territory',
    VIC:'Victoria',
    TAS:'Tasmania',
  })[code] || code;
}

function stateHeatColor(count, maximum) {
  if (!count || !maximum) return '#3b2031';
  const ratio = Math.max(0, Math.min(1, count / maximum));
  const stops = [
    [70,34,57],
    [117,66,82],
    [187,124,53],
    [246,185,0],
  ];
  const scaled = ratio * (stops.length - 1);
  const index = Math.min(stops.length - 2, Math.floor(scaled));
  const t = scaled - index;
  const a = stops[index];
  const b = stops[index + 1];
  const rgb = a.map((value, i) =>
    Math.round(value + (b[i] - value) * t)
  );
  return `rgb(${rgb.join(',')})`;
}

function renderStateExplorer() {
  const stats = {};
  for (const record of APP.records) {
    const raw = cap(record['Current State']);
    if (!raw) continue;
    const code = canonicalStateCode(raw);
    if (!['WA','NT','SA','QLD','NSW','ACT','VIC','TAS'].includes(code)) {
      continue;
    }
    stats[code] ||= { code, count: 0, rawLabel: raw };
    stats[code].count += 1;
  }

  const order = ['WA','NT','SA','QLD','NSW','ACT','VIC','TAS'];
  const maximum = Math.max(
    1,
    ...order.map(code => stats[code]?.count || 0)
  );
  const total = APP.records.length || 1;
  const paths = {
    WA:  'M55 126 L214 94 L233 256 L211 383 L78 350 L45 236 Z',
    NT:  'M214 94 L338 82 L338 236 L233 256 Z',
    SA:  'M233 256 L338 236 L409 300 L366 408 L211 383 Z',
    QLD: 'M338 82 L488 53 L592 164 L547 279 L409 300 L338 236 Z',
    NSW: 'M409 300 L547 279 L563 360 L503 390 L456 401 L366 408 Z',
    VIC: 'M366 408 L456 401 L505 431 L414 457 L344 440 Z',
    TAS: 'M415 474 L456 470 L469 502 L432 522 L405 497 Z',
    ACT: 'M489 337 L501 332 L507 344 L495 352 L484 346 Z',
  };
  const labels = {
    WA:[135,238],
    NT:[283,161],
    SA:[306,333],
    QLD:[463,172],
    NSW:[472,337],
    VIC:[420,433],
    TAS:[438,496],
    ACT:[496,343],
  };

  const svg = `
    <svg class="au-map-svg" viewBox="20 30 600 510"
         role="img"
         aria-label="Interactive map of Australian states and territories">
      <g>
        ${order.map(code => {
          const item = stats[code] || {
            count:0,
            rawLabel:code,
          };
          const active =
            canonicalStateCode(APP.filters.state || '') === code
              ? 'active'
              : '';
          const [x,y] = labels[code];
          return `
            <g data-map-state="${code}"
               data-filter-value="${escapeHtml(item.rawLabel || code)}">
              <path class="au-state-shape ${active}"
                    d="${paths[code]}"
                    fill="${stateHeatColor(item.count, maximum)}"></path>
              <text class="au-map-label" x="${x}" y="${y}">${code}</text>
              <text class="au-map-count" x="${x}" y="${y + 18}">${item.count} clients</text>
            </g>`;
        }).join('')}
      </g>
    </svg>
    <div class="map-tooltip" id="mapTooltip"></div>
    <div class="map-legend">
      <span>Lower</span>
      <div class="map-gradient"></div>
      <span>Higher client volume</span>
    </div>`;

  el('stateMap').innerHTML = svg;
  const tooltip = el('mapTooltip');

  qsa('[data-map-state]', el('stateMap')).forEach(group => {
    const code = group.dataset.mapState;
    const item = stats[code] || { count:0, rawLabel:code };

    group.addEventListener('mousemove', event => {
      const bounds = el('stateMap').getBoundingClientRect();
      tooltip.style.left = `${event.clientX - bounds.left}px`;
      tooltip.style.top = `${event.clientY - bounds.top}px`;
      tooltip.innerHTML = `
        <strong>${escapeHtml(stateName(code))}</strong><br>
        ${prettyInt(item.count)} clients •
        ${(item.count / total * 100).toFixed(1)}%`;
      tooltip.style.opacity = '1';
    });

    group.addEventListener('mouseleave', () => {
      tooltip.style.opacity = '0';
    });

    group.addEventListener('click', () => {
      const raw = group.dataset.filterValue || code;
      APP.filters.state =
        canonicalStateCode(APP.filters.state || '') === code
          ? ''
          : raw;
      buildFilterOptions();
      filterRecords();
      renderAll();
    });
  });

  const ranked = order
    .map(code => stats[code] || {
      code,
      count:0,
      rawLabel:code,
    })
    .filter(item => item.count > 0)
    .sort((a,b) => b.count - a.count);

  el('stateRankings').innerHTML = ranked.map(item => `
    <div class="rank-row"
         data-ranked-state="${item.code}"
         data-filter-value="${escapeHtml(item.rawLabel || item.code)}">
      <strong>${item.code}</strong>
      <span>
        ${prettyInt(item.count)} clients •
        ${(item.count / total * 100).toFixed(1)}%
      </span>
      <div class="rank-bar">
        <div style="width:${(item.count / maximum) * 100}%"></div>
      </div>
    </div>
  `).join('') || `
    <div class="filter-empty">
      No state data available for the selected filter set.
    </div>`;

  qsa('[data-ranked-state]').forEach(row =>
    row.addEventListener('click', () => {
      const code = row.dataset.rankedState;
      APP.filters.state =
        canonicalStateCode(APP.filters.state || '') === code
          ? ''
          : row.dataset.filterValue;
      buildFilterOptions();
      filterRecords();
      renderAll();
    })
  );
}""",
        "Australia map renderer",
    )

    js = replace_between(
        js,
        "function renderOverviewCharts() {",
        "function renderMarketCharts() {",
        r"""function renderOverviewCharts() {
  const theme = chartTheme();
  const industryMode = el('industryMetricMode')?.value || 'count';
  const industryLimit = Number(el('industryTopLimit')?.value || 10);
  const allIndustries = distribution(
    APP.records,
    'Primary Industry',
    100
  );
  const industries = allIndustries.slice(0, industryLimit);
  const top = allIndustries[0];
  const topThreeShare = allIndustries
    .slice(0,3)
    .reduce((sum,item) => sum + item.percentage, 0);
  const longTail = Math.max(0, allIndustries.length - 3);

  const strip = el('industryInsightStrip');
  if (strip) {
    strip.innerHTML = `
      <div class="industry-insight">
        <span>Leading industry</span>
        <strong>${escapeHtml(top?.label || 'Not available')}</strong>
        <em>${top
          ? `${top.count} clients • ${top.percentage}%`
          : 'No populated industry data'}</em>
      </div>
      <div class="industry-insight">
        <span>Top 3 concentration</span>
        <strong>${topThreeShare.toFixed(1)}%</strong>
        <em>Share of the filtered portfolio</em>
      </div>
      <div class="industry-insight">
        <span>Industry breadth</span>
        <strong>${allIndustries.length}</strong>
        <em>${longTail} industries beyond the top 3</em>
      </div>`;
  }

  const narrative = el('industryNarrative');
  if (narrative) {
    if (allIndustries.length) {
      const second = allIndustries[1];
      narrative.innerHTML = `
        <strong>${escapeHtml(top.label)}</strong>
        is the largest visible client segment at ${top.percentage}%
        ${second
          ? `, followed by <strong>${escapeHtml(second.label)}</strong>
             at ${second.percentage}%`
          : ''}.
        The top three industries collectively represent
        <strong>${topThreeShare.toFixed(1)}%</strong>
        of the current filtered portfolio.`;
    } else {
      narrative.textContent =
        'Industry data is not populated for the current filter selection.';
    }
  }

  const values = industries.map(item =>
    industryMode === 'percentage'
      ? item.percentage
      : item.count
  );

  renderChart('industryRankChart', {
    ...theme,
    chart: {
      ...theme.chart,
      type: 'bar',
      height: 365,
      events: {
        dataPointSelection: (_event, _ctx, config) => {
          const selected = industries[config.dataPointIndex]?.label;
          if (!selected) return;
          APP.filters.industry = selected;
          buildFilterOptions();
          filterRecords();
          renderAll();
        },
      },
    },
    series: [{
      name:
        industryMode === 'percentage'
          ? 'Portfolio share'
          : 'Clients',
      data: values,
    }],
    colors: industries.map((_item,index) =>
      index === 0
        ? '#ffe500'
        : index < 3
          ? '#f6b900'
          : '#8c4bff'
    ),
    xaxis: {
      ...theme.xaxis,
      categories: industries.map(item => item.label),
      max:
        industryMode === 'percentage'
          ? Math.max(
              10,
              Math.ceil(Math.max(...values, 0) / 10) * 10
            )
          : undefined,
      labels: {
        style: {
          colors: 'rgba(255,255,255,0.68)',
          fontWeight: 500,
        },
        formatter: value =>
          industryMode === 'percentage'
            ? `${Number(value).toFixed(0)}%`
            : prettyInt(value),
      },
    },
    yaxis: {
      labels: {
        style: {
          colors: 'rgba(255,255,255,0.88)',
          fontSize: '12px',
          fontWeight: 600,
        },
        maxWidth: 180,
      },
    },
    plotOptions: {
      bar: {
        horizontal: true,
        distributed: true,
        borderRadius: 9,
        barHeight: '62%',
        dataLabels: { position: 'top' },
      },
    },
    dataLabels: {
      enabled: true,
      offsetX: 7,
      formatter: (_value, config) => {
        const item = industries[config.dataPointIndex];
        return industryMode === 'percentage'
          ? `${item.percentage}%`
          : `${item.count}`;
      },
      style: {
        colors: ['#ffffff'],
        fontSize: '11px',
        fontWeight: 700,
      },
      dropShadow: { enabled: false },
    },
    tooltip: {
      theme: 'dark',
      custom: ({ dataPointIndex }) => {
        const item = industries[dataPointIndex];
        return `
          <div style="padding:10px 12px">
            <strong>${escapeHtml(item.label)}</strong><br>
            ${item.count} clients<br>
            ${item.percentage}% of filtered portfolio
          </div>`;
      },
    },
    legend: { show: false },
  });

  const roles = distribution(APP.records, 'Primary Target Role', 10);
  renderChart('targetRolesBar', {
    ...theme,
    chart: {
      ...theme.chart,
      type: 'bar',
      height: 320,
      events: {
        dataPointSelection: clickFilterHandler(
          'role',
          roles.map(x => x.label)
        ),
      },
    },
    series: [{
      name: 'Clients',
      data: roles.map(x => x.count),
    }],
    xaxis: {
      ...theme.xaxis,
      categories: roles.map(x => x.label),
    },
    plotOptions: {
      bar: {
        horizontal: true,
        borderRadius: 10,
        barHeight: '64%',
      },
    },
  });

  const exp = distribution(APP.records, '_experienceBand', 10);
  renderChart('experienceArea', {
    ...theme,
    chart: {
      ...theme.chart,
      type: 'area',
      height: 320,
    },
    series: [{
      name: 'Clients',
      data: exp.map(x => x.count),
    }],
    xaxis: {
      ...theme.xaxis,
      categories: exp.map(x => x.label),
    },
    fill: {
      type: 'gradient',
      gradient: {
        opacityFrom: 0.45,
        opacityTo: 0.04,
      },
    },
  });
}""",
        "overview chart renderer",
    )

    old_bind_tail = """  el('mobileMenuBtn').addEventListener('click', () => qs('.sidebar').classList.toggle('open'));
}"""
    new_bind_tail = """  el('mobileMenuBtn').addEventListener('click', () => qs('.sidebar').classList.toggle('open'));

  const quickBindings = {
    quickFilterState: 'state',
    quickFilterIndustry: 'industry',
    quickFilterRoleFamily: 'role_family',
    quickFilterVisa: 'visa',
  };
  Object.entries(quickBindings).forEach(([elementId, filterKey]) => {
    const select = el(elementId);
    if (!select) return;
    select.addEventListener('change', () => {
      APP.filters[filterKey] = select.value || '';
      buildFilterOptions();
      filterRecords();
      renderAll();
    });
  });

  el('moreFiltersBtn')?.addEventListener(
    'click',
    () => openDrawer('filterDrawer')
  );
  el('inlineResetFiltersBtn')?.addEventListener('click', () => {
    APP.filters = {};
    buildFilterOptions();
    filterRecords();
    renderAll();
  });
  el('industryMetricMode')?.addEventListener(
    'change',
    renderOverviewCharts
  );
  el('industryTopLimit')?.addEventListener(
    'change',
    renderOverviewCharts
  );
}"""
    js = replace_once(
        js,
        old_bind_tail,
        new_bind_tail,
        "inline filter event bindings",
    )

    html_path.write_text(html, encoding="utf-8")
    css_path.write_text(css, encoding="utf-8")
    js_path.write_text(js, encoding="utf-8")

    print("DreamShift Australia map + industry intelligence patch applied.")
    print(f"Backup: {backup_dir}")
    print()
    print(
        "Restart the standalone dashboard server and hard-refresh "
        "with Ctrl+Shift+R."
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
