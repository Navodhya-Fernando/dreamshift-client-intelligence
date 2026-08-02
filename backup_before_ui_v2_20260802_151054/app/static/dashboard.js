(() => {
  "use strict";

  const state = {
    records: [],
    filtered: [],
    payload: null,
    activeTab: "overview",
    refreshTimer: null,
    pitchSummary: "",
  };

  const colors = [
    "#6c5ce7", "#11a9b7", "#18a66a", "#e59b22",
    "#d94a67", "#4775f2", "#9b6ad6", "#6a8d92",
  ];

  const $ = (id) => document.getElementById(id);
  const els = {
    liveStatus: $("liveStatus"),
    lastSynced: $("lastSynced"),
    dataSourceNote: $("dataSourceNote"),
    refreshButton: $("refreshButton"),
    copySummaryButton: $("copySummaryButton"),
    filteredCountLabel: $("filteredCountLabel"),
    resetFiltersButton: $("resetFiltersButton"),
    filterState: $("filterState"),
    filterIndustry: $("filterIndustry"),
    filterRoleFamily: $("filterRoleFamily"),
    filterVisa: $("filterVisa"),
    filterSeniority: $("filterSeniority"),
    filterQualification: $("filterQualification"),
    filterDateFrom: $("filterDateFrom"),
    filterDateTo: $("filterDateTo"),
    overviewKpis: $("overviewKpis"),
    educationKpis: $("educationKpis"),
    careerKpis: $("careerKpis"),
    insightGrid: $("insightGrid"),
    fieldSearch: $("fieldSearch"),
    fieldGroups: $("fieldGroups"),
    dataOverview: $("dataOverview"),
    askLauncher: $("askLauncher"),
    askDrawer: $("askDrawer"),
    closeAskButton: $("closeAskButton"),
    drawerBackdrop: $("drawerBackdrop"),
    askForm: $("askForm"),
    askInput: $("askInput"),
    askSubmit: $("askSubmit"),
    askScope: $("askScope"),
    chatThread: $("chatThread"),
    questionSuggestions: $("questionSuggestions"),
    toast: $("toast"),
  };

  const filterFields = [
    [els.filterState, "Current State", "All states"],
    [els.filterIndustry, "Primary Industry", "All industries"],
    [els.filterRoleFamily, "Role Family", "All role families"],
    [els.filterVisa, "Visa Category", "All visa categories"],
    [els.filterSeniority, "Seniority Level", "All seniority levels"],
    [els.filterQualification, "Highest Qualification Level", "All qualifications"],
  ];

  function cleanText(value) {
    return String(value ?? "").trim();
  }

  function normaliseKey(value) {
    return cleanText(value).toLocaleLowerCase().replaceAll("’", "'");
  }

  function listValues(value) {
    if (value === null || value === undefined || value === "") return [];
    if (Array.isArray(value)) {
      return unique(value.flatMap(listValues));
    }
    if (typeof value === "object") {
      return listValues(value.name ?? value.value ?? value.label ?? "");
    }
    const text = cleanText(value);
    if (!text) return [];
    if ((text.startsWith("[") && text.endsWith("]"))) {
      try {
        const parsed = JSON.parse(text);
        if (Array.isArray(parsed)) return listValues(parsed);
      } catch (_) { /* keep as text */ }
    }
    if (text.includes(";") || text.includes("\n") || text.includes(" | ")) {
      return unique(text.split(/\s*(?:;|\n|\|)\s*/g).filter(Boolean));
    }
    return [text];
  }

  function unique(values) {
    const seen = new Set();
    const output = [];
    values.forEach((value) => {
      const text = cleanText(value);
      const key = normaliseKey(text);
      if (text && !seen.has(key)) {
        seen.add(key);
        output.push(text);
      }
    });
    return output;
  }

  function numberValue(value) {
    const numeric = Number(value);
    return Number.isFinite(numeric) ? numeric : null;
  }

  function yesValue(value) {
    return ["yes", "true", "1", "checked"].includes(normaliseKey(value));
  }

  function formatNumber(value) {
    return new Intl.NumberFormat("en-AU").format(Number(value || 0));
  }

  function formatPercent(value, fallback = "—") {
    const numeric = numberValue(value);
    return numeric === null ? fallback : `${numeric.toFixed(numeric % 1 ? 1 : 0)}%`;
  }

  function formatDateTime(value) {
    if (!value) return "Not synced yet";
    const date = new Date(value);
    if (Number.isNaN(date.getTime())) return cleanText(value);
    return new Intl.DateTimeFormat("en-AU", {
      dateStyle: "medium",
      timeStyle: "short",
    }).format(date);
  }

  function setLiveStatus(mode, text) {
    els.liveStatus.classList.remove("loading", "error");
    if (mode) els.liveStatus.classList.add(mode);
    els.liveStatus.lastChild.textContent = ` ${text}`;
  }

  function showToast(message) {
    els.toast.textContent = message;
    els.toast.classList.add("show");
    window.clearTimeout(showToast.timer);
    showToast.timer = window.setTimeout(() => els.toast.classList.remove("show"), 2200);
  }

  async function fetchJson(url, options = {}) {
    const response = await fetch(url, options);
    let body = null;
    try { body = await response.json(); } catch (_) { body = null; }
    if (!response.ok) {
      throw new Error(body?.detail || `Request failed with HTTP ${response.status}`);
    }
    return body;
  }

  function selectedFilters() {
    return {
      state: els.filterState.value,
      industry: els.filterIndustry.value,
      role_family: els.filterRoleFamily.value,
      visa: els.filterVisa.value,
      seniority: els.filterSeniority.value,
      qualification: els.filterQualification.value,
      date_from: els.filterDateFrom.value,
      date_to: els.filterDateTo.value,
    };
  }

  function recordMatches(record) {
    const filters = selectedFilters();
    const fieldPairs = [
      ["state", "Current State"],
      ["industry", "Primary Industry"],
      ["role_family", "Role Family"],
      ["visa", "Visa Category"],
      ["seniority", "Seniority Level"],
      ["qualification", "Highest Qualification Level"],
    ];
    for (const [filterName, fieldName] of fieldPairs) {
      const selected = filters[filterName];
      if (!selected) continue;
      const recordKeys = new Set(listValues(record[fieldName]).map(normaliseKey));
      if (!recordKeys.has(normaliseKey(selected))) return false;
    }
    const created = record._createdTime ? new Date(record._createdTime) : null;
    if (created && !Number.isNaN(created.getTime())) {
      if (filters.date_from) {
        const from = new Date(`${filters.date_from}T00:00:00`);
        if (created < from) return false;
      }
      if (filters.date_to) {
        const to = new Date(`${filters.date_to}T23:59:59`);
        if (created > to) return false;
      }
    }
    return true;
  }

  function dimensionValues(record, fieldName) {
    return unique(listValues(record[fieldName]));
  }

  function groupCounts(records, accessor) {
    const counts = new Map();
    records.forEach((record) => {
      const values = unique(accessor(record) || []);
      values.forEach((value) => {
        const text = cleanText(value);
        const key = normaliseKey(text);
        if (!text || ["unknown", "not specified", "n/a", "none"].includes(key)) return;
        const current = counts.get(key) || { label: text, count: 0 };
        current.count += 1;
        counts.set(key, current);
      });
    });
    const total = records.length || 1;
    return [...counts.values()]
      .map((item) => ({ ...item, percentage: item.count / total * 100 }))
      .sort((a, b) => b.count - a.count || a.label.localeCompare(b.label));
  }

  function scalarCounts(records, fieldName) {
    return groupCounts(records, (record) => dimensionValues(record, fieldName).slice(0, 1));
  }

  function multiCounts(records, fieldName) {
    return groupCounts(records, (record) => dimensionValues(record, fieldName));
  }

  function distinctCount(records, accessor) {
    const values = new Set();
    records.forEach((record) => {
      (accessor(record) || []).forEach((value) => values.add(normaliseKey(value)));
    });
    return values.size;
  }

  function percentageKnown(records, accessor, predicate = yesValue) {
    const known = records.map(accessor).filter((value) => !["", "unknown"].includes(normaliseKey(value)));
    if (!known.length) return null;
    return known.filter(predicate).length / known.length * 100;
  }

  function topItem(items) {
    return items.length ? items[0] : null;
  }

  function populateSelect(select, records, fieldName, placeholder) {
    const previous = select.value;
    const values = unique(records.flatMap((record) => dimensionValues(record, fieldName)))
      .filter((value) => !["unknown", "not specified", "n/a"].includes(normaliseKey(value)))
      .sort((a, b) => a.localeCompare(b));
    select.innerHTML = "";
    const first = document.createElement("option");
    first.value = "";
    first.textContent = placeholder;
    select.append(first);
    values.forEach((value) => {
      const option = document.createElement("option");
      option.value = value;
      option.textContent = value;
      select.append(option);
    });
    if (values.some((value) => normaliseKey(value) === normaliseKey(previous))) {
      select.value = previous;
    }
  }

  function renderKpis(container, items) {
    container.innerHTML = "";
    const palette = [
      ["#6c5ce7", "rgba(108,92,231,.10)"],
      ["#11a9b7", "rgba(17,169,183,.10)"],
      ["#18a66a", "rgba(24,166,106,.10)"],
      ["#e59b22", "rgba(229,155,34,.11)"],
      ["#d94a67", "rgba(217,74,103,.10)"],
      ["#4775f2", "rgba(71,117,242,.10)"],
    ];
    items.forEach((item, index) => {
      const card = document.createElement("article");
      card.className = "kpi-card";
      const [color, tint] = palette[index % palette.length];
      card.style.setProperty("--kpi-color", color);
      card.style.setProperty("--kpi-tint", tint);
      card.innerHTML = `
        <div class="kpi-icon">${escapeHtml(item.icon || "•")}</div>
        <strong class="kpi-value">${escapeHtml(item.value)}</strong>
        <span class="kpi-label">${escapeHtml(item.label)}</span>
      `;
      container.append(card);
    });
  }

  function renderHorizontalBars(containerId, items, limit = 10, options = {}) {
    const container = $(containerId);
    const data = items.slice(0, limit);
    if (!data.length) {
      container.innerHTML = `<div class="empty-state">No populated client data is available for this view.</div>`;
      return;
    }
    const max = Math.max(...data.map((item) => item.count), 1);
    const chart = document.createElement("div");
    chart.className = "bar-chart";
    data.forEach((item, index) => {
      const row = document.createElement("div");
      row.className = "bar-row";
      row.title = `${item.label}: ${item.count} clients (${item.percentage.toFixed(1)}%)`;
      const fillColor = options.singleColor ? colors[0] : colors[index % colors.length];
      row.innerHTML = `
        <div class="bar-label">${escapeHtml(item.label)}</div>
        <div class="bar-track"><div class="bar-fill" style="background:${fillColor}"></div></div>
        <div class="bar-value">${formatNumber(item.count)} · ${item.percentage.toFixed(1)}%</div>
      `;
      chart.append(row);
      requestAnimationFrame(() => {
        const fill = row.querySelector(".bar-fill");
        fill.style.width = `${Math.max(2, item.count / max * 100)}%`;
      });
    });
    container.innerHTML = "";
    container.append(chart);
  }

  function renderDonut(containerId, items, limit = 7) {
    const container = $(containerId);
    const data = items.slice(0, limit);
    if (!data.length) {
      container.innerHTML = `<div class="empty-state">No populated client data is available for this view.</div>`;
      return;
    }
    const included = data.reduce((sum, item) => sum + item.count, 0);
    const all = items.reduce((sum, item) => sum + item.count, 0);
    if (all > included) {
      data.push({ label: "Other", count: all - included, percentage: (all - included) / Math.max(all, 1) * 100 });
    }
    const total = data.reduce((sum, item) => sum + item.count, 0) || 1;
    let cursor = 0;
    const segments = data.map((item, index) => {
      const start = cursor;
      cursor += item.count / total * 100;
      return `${colors[index % colors.length]} ${start}% ${cursor}%`;
    });
    const wrapper = document.createElement("div");
    wrapper.className = "donut-wrap";
    wrapper.innerHTML = `
      <div class="donut" style="background:conic-gradient(${segments.join(",")})">
        <div class="donut-hole"><strong>${formatNumber(total)}</strong><span>client records</span></div>
      </div>
    `;
    const legend = document.createElement("div");
    legend.className = "legend";
    data.forEach((item, index) => {
      const row = document.createElement("div");
      row.className = "legend-row";
      row.innerHTML = `
        <span class="legend-dot" style="background:${colors[index % colors.length]}"></span>
        <span class="legend-label">${escapeHtml(item.label)}</span>
        <span class="legend-value">${formatNumber(item.count)} · ${(item.count / total * 100).toFixed(1)}%</span>
      `;
      legend.append(row);
    });
    container.innerHTML = "";
    container.append(wrapper, legend);
  }

  function renderInsights(records) {
    const industries = scalarCounts(records, "Primary Industry");
    const states = scalarCounts(records, "Current State");
    const roles = scalarCounts(records, "Primary Target Role");
    const institutions = multiCounts(records, "_institutions");
    const topIndustries = industries.slice(0, 3);
    const concentration = topIndustries.reduce((sum, item) => sum + item.count, 0) / Math.max(records.length, 1) * 100;
    const topState = topItem(states);
    const topRole = topItem(roles);
    const topInstitution = topItem(institutions);
    const cards = [
      {
        number: "01",
        title: topState ? `${topState.label} is the largest client market` : "Location insight pending",
        copy: topState ? `${topState.count} clients, representing ${topState.percentage.toFixed(1)}% of the current segment.` : "Populate Current State to reveal geographic concentration.",
      },
      {
        number: "02",
        title: topIndustries.length ? `Top 3 industries represent ${concentration.toFixed(1)}%` : "Industry insight pending",
        copy: topIndustries.length ? topIndustries.map((item) => item.label).join(" · ") : "Populate Primary Industry to reveal market concentration.",
      },
      {
        number: "03",
        title: topRole ? `${topRole.label} is the leading target role` : "Role insight pending",
        copy: topRole ? `${topRole.count} clients are primarily targeting this role (${topRole.percentage.toFixed(1)}%).` : "Populate Primary Target Role to reveal job-search demand.",
      },
      {
        number: "04",
        title: topInstitution ? `${topInstitution.label} leads the education footprint` : "Education insight pending",
        copy: topInstitution ? `${topInstitution.count} clients have a qualification from this institution.` : "Populate degree institution fields to reveal university reach.",
      },
    ];
    els.insightGrid.innerHTML = cards.map((card) => `
      <article class="insight-card">
        <span class="insight-number">${card.number}</span>
        <h4>${escapeHtml(card.title)}</h4>
        <p>${escapeHtml(card.copy)}</p>
      </article>
    `).join("");

    const parts = [`DreamShift's current client intelligence dataset includes ${records.length} client profiles.`];
    if (industries.length) parts.push(`It spans ${industries.length} primary industries, led by ${industries[0].label} (${industries[0].percentage.toFixed(1)}%).`);
    if (roles.length) parts.push(`${roles[0].label} is the most common primary target role (${roles[0].count} clients).`);
    if (institutions.length) parts.push(`Clients represent ${institutions.length} education institutions, with ${institutions[0].label} the most represented.`);
    state.pitchSummary = parts.join(" ");
  }

  function renderOverview(records) {
    const industries = scalarCounts(records, "Primary Industry");
    const states = scalarCounts(records, "Current State");
    const roleFamilies = scalarCounts(records, "Role Family");
    const roles = scalarCounts(records, "Primary Target Role");
    const institutions = multiCounts(records, "_institutions");
    const auQualification = percentageKnown(records, (record) => record._hasAustralianQualification);

    renderKpis(els.overviewKpis, [
      { icon: "01", value: formatNumber(records.length), label: "Client profiles in the current segment" },
      { icon: "AU", value: formatNumber(states.length), label: "Australian states or territories represented" },
      { icon: "IN", value: formatNumber(industries.length), label: "Primary industries represented" },
      { icon: "RF", value: formatNumber(roleFamilies.length), label: "Role families supported" },
      { icon: "ED", value: formatNumber(institutions.length), label: "Education institutions represented" },
      { icon: "%", value: formatPercent(auQualification), label: "Clients with an Australian qualification" },
    ]);
    renderInsights(records);
    renderHorizontalBars("industryChart", industries, 10, { singleColor: true });
    renderDonut("stateChart", states, 7);
    renderHorizontalBars("roleFamilyChart", roleFamilies, 10);
    renderHorizontalBars("targetRoleChart", roles, 10);
  }

  function renderEducation(records) {
    const institutions = multiCounts(records, "_institutions");
    const countries = multiCounts(records, "_educationCountries");
    const qualifications = scalarCounts(records, "Highest Qualification Level");
    const auQualification = percentageKnown(records, (record) => record._hasAustralianQualification);
    const postgraduate = percentageKnown(records, (record) => record._postgraduate);
    renderKpis(els.educationKpis, [
      { icon: "ED", value: formatNumber(institutions.length), label: "Distinct institutions represented" },
      { icon: "GL", value: formatNumber(countries.length), label: "Education countries represented" },
      { icon: "PG", value: formatPercent(postgraduate), label: "Clients with postgraduate education" },
      { icon: "AU", value: formatPercent(auQualification), label: "Clients with an Australian qualification" },
      { icon: "MQ", value: formatNumber(records.filter((record) => yesValue(record["Master’s Degree"])).length), label: "Clients with at least one master’s degree" },
      { icon: "PHD", value: formatNumber(records.filter((record) => yesValue(record.PhD)).length), label: "Clients with a PhD" },
    ]);
    renderHorizontalBars("institutionChart", institutions, 10, { singleColor: true });
    renderDonut("qualificationChart", qualifications, 7);
    renderHorizontalBars("educationCountryChart", countries, 10);

    const degreeItems = [
      ["Australian Master’s Degree", "Australian master’s"],
      ["Australian Bachelor’s Degree", "Australian bachelor’s"],
      ["Australian PhD", "Australian PhD"],
      ["Australian Other Qualification", "Other Australian qualification"],
    ].map(([field, label]) => {
      const count = records.filter((record) => yesValue(record[field])).length;
      return { label, count, percentage: count / Math.max(records.length, 1) * 100 };
    }).sort((a, b) => b.count - a.count);
    renderHorizontalBars("australianDegreeChart", degreeItems, 10);
  }

  function renderCareers(records) {
    const experience = scalarCounts(records, "_experienceBand");
    const auExperience = scalarCounts(records, "_auExperienceBand");
    const visas = scalarCounts(records, "Visa Category");
    const seniority = scalarCounts(records, "Seniority Level");
    const jobFunctions = scalarCounts(records, "Job Function");
    const businessDomains = multiCounts(records, "Business Domains");
    const localExperience = percentageKnown(records, (record) => record["Australian Employer Experience"]);
    const fullWorkRights = percentageKnown(records, (record) => record["Full Work Rights"]);
    const leadership = percentageKnown(records, (record) => record["Leadership Experience"]);
    const regulated = percentageKnown(records, (record) => record["Regulated Industry Experience"]);
    renderKpis(els.careerKpis, [
      { icon: "AU", value: formatPercent(localExperience), label: "Clients with Australian employer experience" },
      { icon: "WR", value: formatPercent(fullWorkRights), label: "Clients with full work rights among known records" },
      { icon: "LD", value: formatPercent(leadership), label: "Clients with leadership experience" },
      { icon: "RG", value: formatPercent(regulated), label: "Clients with regulated-industry experience" },
      { icon: "JF", value: formatNumber(jobFunctions.length), label: "Job functions represented" },
      { icon: "BD", value: formatNumber(businessDomains.length), label: "Business domains represented" },
    ]);
    renderHorizontalBars("experienceChart", experience, 10);
    renderHorizontalBars("auExperienceChart", auExperience, 10);
    renderDonut("visaChart", visas, 7);
    renderHorizontalBars("seniorityChart", seniority, 10);
    renderHorizontalBars("jobFunctionChart", jobFunctions, 10);
    renderHorizontalBars("businessDomainChart", businessDomains, 10);
  }

  function renderDataDictionary(query = "") {
    const schema = state.payload?.schema;
    if (!schema) return;
    const search = normaliseKey(query);
    const groups = (schema.groups || []).map((group) => ({
      ...group,
      fields: (group.fields || []).filter((field) => {
        if (!search) return true;
        return [field.name, field.actual_name, field.type].some((value) => normaliseKey(value).includes(search));
      }),
    })).filter((group) => group.fields.length);

    els.dataOverview.innerHTML = [
      [schema.expected_field_count || 0, "Expected extractor columns"],
      [schema.present_expected_count || 0, "Expected columns currently detected"],
      [state.records.length, "Live Airtable client records"],
      [schema.source === "metadata" ? "Metadata API" : "Record inference", "Schema detection method"],
    ].map(([value, label]) => `<article class="data-stat"><strong>${escapeHtml(value)}</strong><span>${escapeHtml(label)}</span></article>`).join("");

    if (!groups.length) {
      els.fieldGroups.innerHTML = `<div class="empty-state">No columns match this search.</div>`;
      return;
    }
    els.fieldGroups.innerHTML = groups.map((group, index) => {
      const present = group.fields.filter((field) => field.present).length;
      return `
        <details class="field-group" ${index < 2 || search ? "open" : ""}>
          <summary>${escapeHtml(group.name)} <span>${present}/${group.fields.length} detected</span></summary>
          <div class="field-list">
            ${group.fields.map((field) => `
              <div class="field-row">
                <div class="field-name"><strong title="${escapeHtml(field.actual_name)}">${escapeHtml(field.name)}</strong><span>${escapeHtml(field.type || "inferred")}</span></div>
                <div class="field-status ${field.present ? "present" : "missing"}">${field.present ? "Detected" : "Missing"}</div>
                <div class="coverage"><div class="coverage-track"><div class="coverage-fill" style="width:${Math.min(100, field.coverage || 0)}%"></div></div><span>${Number(field.coverage || 0).toFixed(0)}%</span></div>
              </div>
            `).join("")}
          </div>
        </details>
      `;
    }).join("");
  }

  function renderAll() {
    state.filtered = state.records.filter(recordMatches);
    els.filteredCountLabel.textContent = `${formatNumber(state.filtered.length)} of ${formatNumber(state.records.length)} clients visible`;
    els.askScope.textContent = `Using ${formatNumber(state.filtered.length)} visible clients`;
    renderOverview(state.filtered);
    renderEducation(state.filtered);
    renderCareers(state.filtered);
    renderDataDictionary(els.fieldSearch.value);
  }

  async function loadData(force = false) {
    setLiveStatus("loading", "Refreshing Airtable data");
    els.refreshButton.disabled = true;
    els.refreshButton.textContent = "Refreshing…";
    try {
      const payload = await fetchJson(`/api/dashboard/data?force=${force ? "true" : "false"}`);
      state.payload = payload;
      state.records = Array.isArray(payload.records) ? payload.records : [];
      filterFields.forEach(([select, fieldName, placeholder]) => populateSelect(select, state.records, fieldName, placeholder));
      els.lastSynced.textContent = formatDateTime(payload.fetched_at);
      const schemaText = payload.schema?.source === "metadata" ? "Airtable metadata verified" : "Schema inferred from populated records";
      els.dataSourceNote.textContent = `${schemaText} · Browser payload excludes direct identifiers`;
      setLiveStatus("", "Live Airtable data");
      renderAll();
      window.clearInterval(state.refreshTimer);
      const refreshSeconds = Math.max(15, Number(payload.refresh_seconds || 60));
      state.refreshTimer = window.setInterval(() => {
        if (!document.hidden) loadData(true);
      }, refreshSeconds * 1000);
    } catch (error) {
      console.error(error);
      setLiveStatus("error", "Airtable connection error");
      els.lastSynced.textContent = "Sync failed";
      els.dataSourceNote.textContent = error.message;
      showToast(error.message);
    } finally {
      els.refreshButton.disabled = false;
      els.refreshButton.textContent = "Refresh now";
    }
  }

  function setActiveTab(name) {
    state.activeTab = name;
    document.querySelectorAll(".tab").forEach((button) => button.classList.toggle("active", button.dataset.tab === name));
    document.querySelectorAll(".tab-panel").forEach((panel) => panel.classList.toggle("active", panel.id === `tab-${name}`));
  }

  function resetFilters() {
    filterFields.forEach(([select]) => { select.value = ""; });
    els.filterDateFrom.value = "";
    els.filterDateTo.value = "";
    renderAll();
  }

  function openAsk() {
    els.askDrawer.classList.add("open");
    els.drawerBackdrop.classList.add("open");
    els.askDrawer.setAttribute("aria-hidden", "false");
    window.setTimeout(() => els.askInput.focus(), 180);
  }

  function closeAsk() {
    els.askDrawer.classList.remove("open");
    els.drawerBackdrop.classList.remove("open");
    els.askDrawer.setAttribute("aria-hidden", "true");
  }

  function addChatMessage(text, role = "assistant") {
    const message = document.createElement("div");
    message.className = `chat-message ${role}`;
    message.textContent = text;
    els.chatThread.append(message);
    els.chatThread.scrollTop = els.chatThread.scrollHeight;
    return message;
  }

  function addChatResult(result) {
    const box = document.createElement("div");
    box.className = "chat-result";
    const findings = Array.isArray(result.key_findings) ? result.key_findings : [];
    box.innerHTML = `
      <h4>${result.mode === "ai" ? "AI-grounded analysis" : "Exact data analysis"}</h4>
      <p>${escapeHtml(result.answer || "No answer was returned.")}</p>
      ${findings.length ? `<ul>${findings.map((item) => `<li>${escapeHtml(item)}</li>`).join("")}</ul>` : ""}
      ${result.pitch_deck_line ? `<div class="pitch-line">${escapeHtml(result.pitch_deck_line)}</div>` : ""}
      ${result.marketing_opportunity ? `<p><strong>Marketing opportunity:</strong> ${escapeHtml(result.marketing_opportunity)}</p>` : ""}
      <div class="chat-meta">${escapeHtml(result.notice || result.data_note || "")}${result.model ? ` · ${escapeHtml(result.model)}` : ""}</div>
    `;
    if (result.pitch_deck_line) {
      const copy = document.createElement("button");
      copy.type = "button";
      copy.className = "text-button";
      copy.textContent = "Copy pitch-deck line";
      copy.addEventListener("click", async () => {
        await navigator.clipboard.writeText(result.pitch_deck_line);
        showToast("Pitch-deck line copied");
      });
      box.append(copy);
    }
    els.chatThread.append(box);
    els.chatThread.scrollTop = els.chatThread.scrollHeight;
  }

  async function askQuestion(question) {
    const text = cleanText(question);
    if (text.length < 2) return;
    addChatMessage(text, "user");
    els.askInput.value = "";
    const loading = addChatMessage("Analysing the current Airtable segment…", "assistant");
    els.askSubmit.disabled = true;
    try {
      const result = await fetchJson("/api/dashboard/ask", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ question: text, filters: selectedFilters() }),
      });
      loading.remove();
      addChatResult(result);
    } catch (error) {
      loading.textContent = `Analysis failed: ${error.message}`;
    } finally {
      els.askSubmit.disabled = false;
    }
  }

  function escapeHtml(value) {
    return cleanText(value)
      .replaceAll("&", "&amp;")
      .replaceAll("<", "&lt;")
      .replaceAll(">", "&gt;")
      .replaceAll('"', "&quot;")
      .replaceAll("'", "&#039;");
  }

  document.querySelectorAll(".tab").forEach((button) => button.addEventListener("click", () => setActiveTab(button.dataset.tab)));
  filterFields.forEach(([select]) => select.addEventListener("change", renderAll));
  els.filterDateFrom.addEventListener("change", renderAll);
  els.filterDateTo.addEventListener("change", renderAll);
  els.resetFiltersButton.addEventListener("click", resetFilters);
  els.refreshButton.addEventListener("click", () => loadData(true));
  els.copySummaryButton.addEventListener("click", async () => {
    if (!state.pitchSummary) return;
    await navigator.clipboard.writeText(state.pitchSummary);
    showToast("Pitch summary copied");
  });
  els.fieldSearch.addEventListener("input", () => renderDataDictionary(els.fieldSearch.value));
  els.askLauncher.addEventListener("click", openAsk);
  els.closeAskButton.addEventListener("click", closeAsk);
  els.drawerBackdrop.addEventListener("click", closeAsk);
  els.askForm.addEventListener("submit", (event) => {
    event.preventDefault();
    askQuestion(els.askInput.value);
  });
  els.askInput.addEventListener("keydown", (event) => {
    if (event.key === "Enter" && !event.shiftKey) {
      event.preventDefault();
      els.askForm.requestSubmit();
    }
  });
  els.questionSuggestions.addEventListener("click", (event) => {
    const button = event.target.closest("button");
    if (!button) return;
    els.askInput.value = button.textContent;
    askQuestion(button.textContent);
  });
  document.addEventListener("keydown", (event) => {
    if (event.key === "Escape") closeAsk();
  });

  loadData(false);
})();
