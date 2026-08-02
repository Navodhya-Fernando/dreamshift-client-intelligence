
const FILTER_CONFIG = {
  state: { field: 'Current State', element: 'filterState', type: 'single' },
  industry: { field: 'Primary Industry', element: 'filterIndustry', type: 'single' },
  role_family: { field: 'Role Family', element: 'filterRoleFamily', type: 'single' },
  role: { field: 'Primary Target Role', element: 'filterRole', type: 'single' },
  visa: { field: 'Visa Category', element: 'filterVisa', type: 'single' },
  qualification: { field: 'Highest Qualification Level', element: 'filterQualification', type: 'single' },
};

const APP = {
  rawRecords: [],
  records: [],
  schema: null,
  fetchedAt: null,
  refreshSeconds: 60,
  view: 'overview',
  filters: {},
  charts: {},
  chatCounter: 0,
};

const el = (id) => document.getElementById(id);
const qs = (sel, root = document) => root.querySelector(sel);
const qsa = (sel, root = document) => Array.from(root.querySelectorAll(sel));
const cap = (v) => String(v || '').trim();
const norm = (v) => cap(v).toLowerCase();
const num = (v) => {
  const n = Number(v);
  return Number.isFinite(n) ? n : null;
};
const listify = (value) => {
  if (value == null) return [];
  if (Array.isArray(value)) return [...new Set(value.flatMap(listify).map(cap).filter(Boolean))];
  if (typeof value === 'object') return [];
  const text = cap(value);
  if (!text) return [];
  if (text.startsWith('[') && text.endsWith(']')) {
    try { return listify(JSON.parse(text)); } catch (_) {}
  }
  if (text.includes(';') || text.includes('\n') || text.includes(' | ')) {
    return [...new Set(text.split(/\s*(?:;|\n|\|)\s*/).map(cap).filter(Boolean))];
  }
  return [text];
};
const pct = (value) => value == null ? '—' : `${Number(value).toFixed(1).replace('.0', '')}%`;
const prettyInt = (value) => new Intl.NumberFormat().format(Number(value || 0));
const minutesAgo = (iso) => {
  if (!iso) return '—';
  const diff = Math.max(0, Date.now() - new Date(iso).getTime());
  const mins = Math.round(diff / 60000);
  if (mins < 1) return 'just now';
  if (mins < 60) return `${mins} min ago`;
  const hrs = (mins / 60).toFixed(1).replace('.0', '');
  return `${hrs} hr ago`;
};

function distribution(records, field, limit = 10, multi = false) {
  const counts = new Map();
  for (const record of records) {
    const raw = record[field];
    const values = multi ? listify(raw) : (cap(raw) ? [cap(raw)] : []);
    for (const value of values) {
      if (!value || ['unknown', 'not specified', 'n/a', 'none', 'null'].includes(norm(value))) continue;
      counts.set(value, (counts.get(value) || 0) + 1);
    }
  }
  return [...counts.entries()]
    .sort((a, b) => b[1] - a[1])
    .slice(0, limit)
    .map(([label, count]) => ({ label, count, percentage: records.length ? +(count / records.length * 100).toFixed(1) : 0 }));
}

function valueCounts(records, getter, limit = 10) {
  const counts = new Map();
  for (const record of records) {
    const values = listify(getter(record));
    for (const value of values) {
      if (!value || ['unknown', 'not specified', 'n/a', 'none', 'null'].includes(norm(value))) continue;
      counts.set(value, (counts.get(value) || 0) + 1);
    }
  }
  return [...counts.entries()].sort((a,b)=>b[1]-a[1]).slice(0,limit).map(([label,count])=>({label,count,percentage: records.length ? +(count / records.length * 100).toFixed(1) : 0}));
}

function crossTab(records, rowField, colField, rowLimit = 6, colLimit = 6) {
  const rows = distribution(records, rowField, rowLimit, false).map(x => x.label);
  const cols = distribution(records, colField, colLimit, false).map(x => x.label);
  return rows.map(row => ({
    name: row,
    data: cols.map(col => ({
      x: col,
      y: records.filter(r => cap(r[rowField]) === row && cap(r[colField]) === col).length,
    })),
  }));
}

function distinctCount(records, field, multi = false) {
  const s = new Set();
  for (const record of records) {
    const values = multi ? listify(record[field]) : (cap(record[field]) ? [cap(record[field])] : []);
    values.forEach(v => s.add(norm(v)));
  }
  return s.size;
}

function computeMetrics(records) {
  const schemaGroups = APP.schema?.groups || [];
  const expected = APP.schema?.expected_field_count || 0;
  const present = APP.schema?.present_expected_count || 0;
  return [
    { key: 'total', label: 'Clients represented', value: prettyInt(records.length), sub: `${distinctCount(records, 'Current State')} states • ${distinctCount(records, 'Primary Industry')} industries` },
    { key: 'roles', label: 'Target roles', value: prettyInt(distinctCount(records, 'Primary Target Role')), sub: `${distinctCount(records, 'Role Family')} role families` },
    { key: 'education', label: 'Institutions', value: prettyInt(distinctCount(records, '_institutions', true)), sub: `${distinctCount(records, '_educationCountries', true)} education countries` },
    { key: 'auqual', label: 'Australian qualifications', value: pct(yesShare(records, '_hasAustralianQualification')), sub: `${pct(yesShare(records, '_postgraduate'))} postgraduate share` },
    { key: 'leadership', label: 'Leadership experience', value: pct(yesShare(records, 'Leadership Experience')), sub: `${pct(yesShare(records, 'Australian Employer Experience'))} local employer exposure` },
    { key: 'quality', label: 'Data coverage', value: expected ? `${Math.round((present / expected) * 100)}%` : '—', sub: `${schemaGroups.length} schema groups tracked` },
  ];
}

function yesShare(records, field) {
  const known = records.filter(r => cap(r[field]) && !['unknown'].includes(norm(r[field])));
  if (!known.length) return null;
  const yes = known.filter(r => ['yes', 'true', '1', 'checked'].includes(norm(r[field]))).length;
  return +(yes / known.length * 100).toFixed(1);
}

function filterRecords() {
  APP.records = APP.rawRecords.filter(record => {
    for (const [key, config] of Object.entries(FILTER_CONFIG)) {
      const selected = cap(APP.filters[key]);
      if (!selected) continue;
      if (norm(record[config.field]) !== norm(selected)) return false;
    }
    return true;
  });
}

function populateSelect(id, values, selected = '') {
  const select = el(id);
  if (!select) return;
  select.innerHTML = `<option value="">All</option>` + values.map(v => `<option value="${escapeHtml(v)}" ${norm(v)===norm(selected)?'selected':''}>${escapeHtml(v)}</option>`).join('');
}

function escapeHtml(text) {
  return String(text)
    .replace(/&/g, '&amp;')
    .replace(/</g, '&lt;')
    .replace(/>/g, '&gt;')
    .replace(/"/g, '&quot;')
    .replace(/'/g, '&#039;');
}

function buildFilterOptions() {
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
}

function renderKpis() {
  const metrics = computeMetrics(APP.records);
  el('kpiGrid').innerHTML = metrics.map(item => `
    <article class="kpi-card glass">
      <div class="kpi-label">${escapeHtml(item.label)}</div>
      <div class="kpi-value">${escapeHtml(item.value)}</div>
      <div class="kpi-sub">${escapeHtml(item.sub)}</div>
    </article>
  `).join('');
}

function renderActiveFilters() {
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
}

function labelForFilterKey(key) {
  return ({ state:'State', industry:'Industry', role_family:'Role family', role:'Role', visa:'Visa', qualification:'Qualification' })[key] || key;
}

function canonicalStateCode(value) {
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
}

function chartTheme() {
  return {
    chart: {
      background: 'transparent',
      toolbar: { show: false },
      foreColor: 'rgba(255,255,255,0.84)',
      fontFamily: 'Poppins, sans-serif',
      animations: { enabled: true, easing: 'easeinout', speed: 550 },
    },
    colors: ['#f6b900', '#ffe500', '#8c4bff', '#36d5ff', '#26ddb1', '#ff8fb1'],
    grid: { borderColor: 'rgba(255,255,255,0.08)', strokeDashArray: 4 },
    dataLabels: { enabled: false },
    stroke: { curve: 'smooth', width: 3 },
    tooltip: { theme: 'dark' },
    legend: { labels: { colors: ['rgba(255,255,255,0.85)'] } },
    xaxis: { labels: { style: { colors: 'rgba(255,255,255,0.66)' } }, axisBorder: { color: 'rgba(255,255,255,0.08)' }, axisTicks: { color: 'rgba(255,255,255,0.08)' } },
    yaxis: { labels: { style: { colors: 'rgba(255,255,255,0.66)' } } },
  };
}

function renderChart(id, options) {
  if (APP.charts[id]) APP.charts[id].destroy();
  const container = el(id);
  if (!container) return;
  const chart = new ApexCharts(container, options);
  APP.charts[id] = chart;
  chart.render();
}

function clickFilterHandler(filterKey, labels) {
  return function(_event, _chartContext, config) {
    const label = labels?.[config.dataPointIndex];
    if (!label) return;
    APP.filters[filterKey] = label;
    buildFilterOptions();
    filterRecords();
    renderAll();
  };
}

function renderOverviewCharts() {
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
}

function renderMarketCharts() {
  const theme = chartTheme();
  const visa = distribution(APP.records, 'Visa Category', 8);
  renderChart('visaDonut', {
    ...theme,
    chart: { ...theme.chart, type: 'donut', height: 320 },
    series: visa.map(x => x.count),
    labels: visa.map(x => x.label),
    legend: { position: 'bottom' },
    plotOptions: { pie: { donut: { size: '72%' } } },
  });
  const seniority = distribution(APP.records, 'Seniority Level', 8);
  renderChart('seniorityRadial', {
    ...theme,
    chart: { ...theme.chart, type: 'radialBar', height: 320 },
    series: seniority.slice(0, 5).map(x => x.percentage),
    labels: seniority.slice(0, 5).map(x => x.label),
    plotOptions: { radialBar: { hollow: { size: '22%' }, dataLabels: { name: { color: '#fff' }, value: { color: '#fff' } } } },
  });
  const auExp = distribution(APP.records, '_auExperienceBand', 8);
  renderChart('auExperienceDonut', {
    ...theme,
    chart: { ...theme.chart, type: 'donut', height: 320 },
    series: auExp.map(x => x.count),
    labels: auExp.map(x => x.label),
    legend: { position: 'bottom' },
  });
  const cities = distribution(APP.records, 'Current City', 10);
  renderChart('citiesBar', {
    ...theme,
    chart: { ...theme.chart, type: 'bar', height: 320 },
    series: [{ name: 'Clients', data: cities.map(x => x.count) }],
    xaxis: { ...theme.xaxis, categories: cities.map(x => x.label) },
    plotOptions: { bar: { borderRadius: 10, columnWidth: '58%' } },
  });
  const heatmapSeries = crossTab(APP.records, 'Current State', 'Primary Industry', 6, 7);
  renderChart('stateIndustryHeatmap', {
    ...theme,
    chart: { ...theme.chart, type: 'heatmap', height: 320 },
    series: heatmapSeries,
    dataLabels: { enabled: false },
    plotOptions: { heatmap: { shadeIntensity: 0.7, radius: 8, colorScale: { ranges: [ { from: 0, to: 0, color: 'rgba(255,255,255,0.05)' }, { from: 1, to: 2, color: '#593270' }, { from: 3, to: 5, color: '#8c4bff' }, { from: 6, to: 999, color: '#f6b900' } ] } } },
  });
}

function renderEducationCharts() {
  const theme = chartTheme();
  const institutions = valueCounts(APP.records, r => r._institutions, 10);
  renderChart('institutionsBar', {
    ...theme,
    chart: { ...theme.chart, type: 'bar', height: 320 },
    series: [{ name: 'Clients', data: institutions.map(x => x.count) }],
    xaxis: { ...theme.xaxis, categories: institutions.map(x => x.label) },
    plotOptions: { bar: { horizontal: true, borderRadius: 10, barHeight: '62%' } },
  });
  const quals = distribution(APP.records, 'Highest Qualification Level', 10);
  renderChart('qualificationDonut', {
    ...theme,
    chart: { ...theme.chart, type: 'donut', height: 320 },
    series: quals.map(x => x.count),
    labels: quals.map(x => x.label),
    legend: { position: 'bottom' },
  });
  const eduCountries = valueCounts(APP.records, r => r._educationCountries, 10);
  renderChart('educationCountriesBar', {
    ...theme,
    chart: { ...theme.chart, type: 'bar', height: 280 },
    series: [{ name: 'Clients', data: eduCountries.map(x => x.count) }],
    xaxis: { ...theme.xaxis, categories: eduCountries.map(x => x.label) },
    plotOptions: { bar: { borderRadius: 10, columnWidth: '58%' } },
  });
  el('auQualificationMetric').textContent = pct(yesShare(APP.records, '_hasAustralianQualification'));
  el('postgraduateMetric').textContent = pct(yesShare(APP.records, '_postgraduate'));
}

function renderRoleCharts() {
  const theme = chartTheme();
  const roleFamilies = distribution(APP.records, 'Role Family', 10);
  renderChart('roleFamilyBar', {
    ...theme,
    chart: { ...theme.chart, type: 'bar', height: 320 },
    series: [{ name: 'Clients', data: roleFamilies.map(x => x.count) }],
    xaxis: { ...theme.xaxis, categories: roleFamilies.map(x => x.label) },
    plotOptions: { bar: { horizontal: true, borderRadius: 10, barHeight: '62%' } },
  });
  const skills = valueCounts(APP.records, r => [ ...(listify(r['Core Professional Skills'])), ...(listify(r['Technical Skills'])) ], 8);
  renderChart('skillsRadar', {
    ...theme,
    chart: { ...theme.chart, type: 'radar', height: 320 },
    series: [{ name: 'Skill mentions', data: skills.map(x => x.count) }],
    labels: skills.map(x => x.label),
    markers: { size: 4 },
  });
  const tools = valueCounts(APP.records, r => r['Tools and Platforms'], 10);
  renderChart('toolsBar', {
    ...theme,
    chart: { ...theme.chart, type: 'bar', height: 320 },
    series: [{ name: 'Mentions', data: tools.map(x => x.count) }],
    xaxis: { ...theme.xaxis, categories: tools.map(x => x.label) },
    plotOptions: { bar: { horizontal: true, borderRadius: 10, barHeight: '62%' } },
  });
  const certs = valueCounts(APP.records, r => r['Certificate Names'], 10);
  renderChart('certificationsBar', {
    ...theme,
    chart: { ...theme.chart, type: 'bar', height: 320 },
    series: [{ name: 'Clients', data: certs.map(x => x.count) }],
    xaxis: { ...theme.xaxis, categories: certs.map(x => x.label) },
    plotOptions: { bar: { horizontal: true, borderRadius: 10, barHeight: '62%' } },
  });
}

function renderQuality() {
  const theme = chartTheme();
  const statuses = distribution(APP.records, 'Extraction Status', 8);
  renderChart('extractionStatusDonut', {
    ...theme,
    chart: { ...theme.chart, type: 'donut', height: 320 },
    series: statuses.map(x => x.count),
    labels: statuses.map(x => x.label),
    legend: { position: 'bottom' },
  });
  const wrap = el('schemaCoverage');
  const groups = APP.schema?.groups || [];
  wrap.innerHTML = groups.map(group => `
    <section class="schema-group">
      <h4>${escapeHtml(group.name)}</h4>
      ${group.fields.map(field => `
        <div class="schema-row">
          <div><strong>${escapeHtml(field.name)}</strong><small>${escapeHtml(field.actual_name || field.name)} • ${escapeHtml(field.type || 'field')}</small></div>
          <div class="coverage-bar"><div style="width:${field.coverage || 0}%"></div></div>
          <div style="text-align:right; color:rgba(255,255,255,.78); font-weight:700;">${field.coverage || 0}%</div>
        </div>
      `).join('')}
    </section>
  `).join('');
}

function renderAll() {
  el('lastUpdatedText').textContent = minutesAgo(APP.fetchedAt);
  renderKpis();
  renderActiveFilters();
  renderStateExplorer();
  renderOverviewCharts();
  renderMarketCharts();
  renderEducationCharts();
  renderRoleCharts();
  renderQuality();
}

function setView(view) {
  APP.view = view;
  qsa('.nav-item').forEach(btn => btn.classList.toggle('active', btn.dataset.view === view));
  qsa('.view-panel').forEach(panel => panel.classList.toggle('active', panel.dataset.viewPanel === view));
}

async function loadData(force = false) {
  const response = await fetch(`/api/dashboard/data${force ? '?force=true' : ''}`);
  if (!response.ok) throw new Error(`Dashboard API failed: ${response.status}`);
  const payload = await response.json();
  APP.rawRecords = payload.records || [];
  APP.schema = payload.schema || null;
  APP.fetchedAt = payload.fetched_at || new Date().toISOString();
  APP.refreshSeconds = payload.refresh_seconds || 60;
  buildFilterOptions();
  filterRecords();
  renderAll();
}

function openDrawer(id) { el(id).classList.add('open'); }
function closeDrawer(id) { el(id).classList.remove('open'); }

function collectDrawerFilters() {
  APP.filters.state = el('filterState').value || '';
  APP.filters.industry = el('filterIndustry').value || '';
  APP.filters.role_family = el('filterRoleFamily').value || '';
  APP.filters.role = el('filterRole').value || '';
  APP.filters.visa = el('filterVisa').value || '';
  APP.filters.qualification = el('filterQualification').value || '';
}

function addMessage(kind, html) {
  const container = el('chatMessages');
  const node = document.createElement('div');
  node.className = `message ${kind}`;
  node.innerHTML = html;
  container.appendChild(node);
  container.scrollTop = container.scrollHeight;
  return node;
}

function inferVisualFocus(question) {
  const q = norm(question);
  if (q.includes('certif')) return { title: 'Certification snapshot', main: valueCounts(APP.records, r => r['Certificate Names'], 8), secondary: distribution(APP.records, 'Primary Industry', 5), chartType: 'bar' };
  if (q.includes('univers') || q.includes('institution') || q.includes('college')) return { title: 'Institution snapshot', main: valueCounts(APP.records, r => r._institutions, 8), secondary: valueCounts(APP.records, r => r._educationCountries, 5), chartType: 'bar' };
  if (q.includes('state') || q.includes('city') || q.includes('location')) return { title: 'Location snapshot', main: distribution(APP.records, 'Current State', 8), secondary: distribution(APP.records, 'Current City', 6), chartType: 'bar' };
  if (q.includes('role') || q.includes('job')) return { title: 'Role snapshot', main: distribution(APP.records, 'Primary Target Role', 8), secondary: distribution(APP.records, 'Role Family', 6), chartType: 'bar' };
  if (q.includes('industry') || q.includes('sector')) return { title: 'Industry snapshot', main: distribution(APP.records, 'Primary Industry', 8), secondary: distribution(APP.records, 'Current State', 6), chartType: 'bar' };
  return { title: 'Portfolio snapshot', main: distribution(APP.records, 'Primary Industry', 8), secondary: distribution(APP.records, 'Primary Target Role', 6), chartType: 'bar' };
}

function renderMiniChart(containerId, seriesData, categories, type='bar') {
  const theme = chartTheme();
  renderChart(containerId, {
    ...theme,
    chart: { ...theme.chart, type, height: 220 },
    series: [{ name: 'Clients', data: seriesData }],
    xaxis: { ...theme.xaxis, categories },
    plotOptions: type === 'bar' ? { bar: { horizontal: true, borderRadius: 8, barHeight: '58%' } } : {},
    legend: { show: false },
    stroke: { curve: 'smooth', width: 2 },
  });
}

async function askQuestion(question) {
  const trimmed = cap(question);
  if (!trimmed) return;
  addMessage('user', `<div class="message-label">You asked</div><p>${escapeHtml(trimmed)}</p>`);
  const loading = addMessage('assistant', `<div class="message-label">DreamShift Intelligence</div><h4>Thinking…</h4><p>Generating grounded insight from the current filtered portfolio.</p>`);

  try {
    const response = await fetch('/api/dashboard/ask', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ question: trimmed, filters: APP.filters }),
    });
    if (!response.ok) throw new Error(`Ask API failed: ${response.status}`);
    const payload = await response.json();
    const visual = inferVisualFocus(trimmed);
    const chartA = `aiChartA_${++APP.chatCounter}`;
    const chartB = `aiChartB_${++APP.chatCounter}`;
    loading.innerHTML = `
      <div class="message-label">DreamShift Intelligence ${payload.model ? `• ${escapeHtml(payload.model)}` : ''}</div>
      <h4>${escapeHtml(visual.title)}</h4>
      <p>${escapeHtml(payload.answer || 'No answer returned.')}</p>
      <div class="ai-grid">
        <div class="ai-metric"><span class="eyebrow">Filtered clients</span><strong>${prettyInt(payload.filtered_client_count || APP.records.length)}</strong><span class="muted-note">Current dashboard scope</span></div>
        <div class="ai-metric"><span class="eyebrow">Pitch-deck line</span><p>${escapeHtml(payload.pitch_deck_line || 'No pitch-deck line returned.')}</p></div>
      </div>
      ${payload.key_findings?.length ? `<div class="ai-metric" style="margin-top:12px;"><span class="eyebrow">Key findings</span><ul>${payload.key_findings.map(item => `<li>${escapeHtml(item)}</li>`).join('')}</ul></div>` : ''}
      <div class="ai-grid">
        <div class="ai-chart-card"><span class="eyebrow">Chart insight</span><div id="${chartA}" class="ai-chart"></div></div>
        <div class="ai-chart-card"><span class="eyebrow">Supporting mix</span><div id="${chartB}" class="ai-chart"></div></div>
      </div>
      <div class="ai-metric" style="margin-top:12px;"><span class="eyebrow">Business implication</span><p>${escapeHtml(payload.marketing_opportunity || 'No marketing opportunity returned.')}</p><p class="muted-note">${escapeHtml(payload.data_note || '')}</p></div>
    `;
    const main = visual.main || [];
    const secondary = visual.secondary || [];
    renderMiniChart(chartA, main.map(x => x.count), main.map(x => x.label), 'bar');
    renderMiniChart(chartB, secondary.map(x => x.count), secondary.map(x => x.label), secondary.length <= 6 ? 'donut' : 'bar');
    if (secondary.length <= 6) {
      renderChart(chartB, {
        ...chartTheme(),
        chart: { ...chartTheme().chart, type: 'donut', height: 220 },
        series: secondary.map(x => x.count),
        labels: secondary.map(x => x.label),
        legend: { position: 'bottom' },
      });
    }
  } catch (error) {
    loading.innerHTML = `<div class="message-label">DreamShift Intelligence</div><h4>Couldn’t complete the request</h4><p>${escapeHtml(error.message || String(error))}</p>`;
  }
}

function bindEvents() {
  qsa('.nav-item').forEach(btn => btn.addEventListener('click', () => setView(btn.dataset.view)));
  qsa('[data-clear-filter="state"]').forEach(btn => btn.addEventListener('click', () => {
    delete APP.filters.state; buildFilterOptions(); filterRecords(); renderAll();
  }));
  el('filterBtn').addEventListener('click', () => openDrawer('filterDrawer'));
  qsa('[data-close-drawer]').forEach(btn => btn.addEventListener('click', () => closeDrawer('filterDrawer')));
  el('applyFiltersBtn').addEventListener('click', () => { collectDrawerFilters(); filterRecords(); renderAll(); closeDrawer('filterDrawer'); });
  el('resetFiltersBtn').addEventListener('click', () => { APP.filters = {}; buildFilterOptions(); filterRecords(); renderAll(); });
  el('refreshBtn').addEventListener('click', async () => { el('refreshBtn').textContent = 'Refreshing…'; try { await loadData(true); } finally { el('refreshBtn').textContent = 'Refresh'; } });
  ['openChatBtn', 'openChatBtn2'].forEach(id => el(id).addEventListener('click', () => openDrawer('chatDrawer')));
  qsa('[data-close-chat]').forEach(btn => btn.addEventListener('click', () => closeDrawer('chatDrawer')));
  qsa('.suggestion-chip').forEach(btn => btn.addEventListener('click', () => { openDrawer('chatDrawer'); askQuestion(btn.dataset.question); }));
  qsa('.chip-btn').forEach(btn => btn.addEventListener('click', () => { openDrawer('chatDrawer'); askQuestion(btn.dataset.quickQuestion); }));
  el('chatForm').addEventListener('submit', (event) => {
    event.preventDefault();
    const question = el('chatInput').value;
    el('chatInput').value = '';
    askQuestion(question);
  });
  el('searchInput').addEventListener('keydown', (event) => {
    if (event.key === 'Enter') {
      event.preventDefault();
      const q = el('searchInput').value;
      if (cap(q)) { openDrawer('chatDrawer'); askQuestion(q); }
    }
  });
  el('mobileMenuBtn').addEventListener('click', () => qs('.sidebar').classList.toggle('open'));

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
}

async function bootstrap() {
  bindEvents();
  setView('overview');
  addMessage('assistant', `<div class="message-label">Welcome</div><h4>Ask DreamShift’s portfolio a question</h4><p>Try asking about industries, universities, states, roles, certifications or marketing-ready pitch insights. I can also surface charts inside the response.</p>`);
  await loadData(false);
}

bootstrap().catch((error) => {
  console.error(error);
  document.body.insertAdjacentHTML('afterbegin', `<div style="padding:16px; color:#fff; background:#8b1e4d;">Failed to load dashboard: ${escapeHtml(error.message || String(error))}</div>`);
});
