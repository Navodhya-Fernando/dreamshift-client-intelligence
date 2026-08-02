from __future__ import annotations

import json
import os
import re
from collections import Counter, defaultdict
from dataclasses import dataclass
from typing import Any, Iterable

import httpx
from dotenv import dotenv_values


class QueryEngineError(RuntimeError):
    pass


@dataclass(frozen=True)
class FieldSpec:
    key: str
    field: str
    label: str
    multi: bool = False
    numeric: bool = False
    aliases: tuple[str, ...] = ()


FIELD_SPECS: dict[str, FieldSpec] = {
    "state": FieldSpec("state", "Current State", "State", aliases=("state", "states", "location", "australian state")),
    "city": FieldSpec("city", "Current City", "City", aliases=("city", "cities", "suburb")),
    "industry": FieldSpec("industry", "Primary Industry", "Primary industry", aliases=("industry", "industries", "sector", "sectors")),
    "secondary_industry": FieldSpec("secondary_industry", "Secondary Industries", "Secondary industry", multi=True, aliases=("secondary industry", "secondary industries")),
    "role": FieldSpec("role", "Primary Target Role", "Primary target role", aliases=("target role", "target roles", "job role", "job roles", "role", "roles", "position", "positions")),
    "role_family": FieldSpec("role_family", "Role Family", "Role family", aliases=("role family", "career family", "profession family")),
    "job_function": FieldSpec("job_function", "Job Function", "Job function", aliases=("job function", "function")),
    "current_job_title": FieldSpec("current_job_title", "Current Job Title", "Current job title", aliases=("current job title", "current title")),
    "recent_job_title": FieldSpec("recent_job_title", "Most Recent Job Title", "Most recent job title", aliases=("recent job title", "previous job title", "most recent title")),
    "visa": FieldSpec("visa", "Visa Category", "Visa category", aliases=("visa", "visas", "visa type", "visa types", "visa category", "visa categories", "migration status", "subclass")),
    "seniority": FieldSpec("seniority", "Seniority Level", "Seniority", aliases=("seniority", "career level", "senior", "junior", "graduate", "entry level")),
    "qualification": FieldSpec("qualification", "Highest Qualification Level", "Highest qualification", aliases=("qualification", "qualifications", "degree level", "highest degree")),
    "education_institution": FieldSpec("education_institution", "_institutions", "Education institution", multi=True, aliases=("university", "universities", "education institution", "education institutions", "college", "colleges", "alumni")),
    "education_country": FieldSpec("education_country", "_educationCountries", "Education country", multi=True, aliases=("education country", "education countries", "country of education", "study country")),
    "certification": FieldSpec("certification", "Certificate Names", "Certification", multi=True, aliases=("certification", "certifications", "certificate", "certificates", "credential", "credentials")),
    "certificate_institution": FieldSpec("certificate_institution", "Certificate Institutions", "Certificate institution", multi=True, aliases=("certificate institution", "certificate institutions", "certification institution", "certification institutions", "certificate provider", "certificate providers", "certification provider", "certification providers", "training provider", "training providers")),
    "tool": FieldSpec("tool", "Tools and Platforms", "Tool or platform", multi=True, aliases=("tool", "tools", "platform", "platforms", "software", "technology stack", "tech stack")),
    "skill": FieldSpec("skill", "_skills", "Skill", multi=True, aliases=("skill", "skills", "competency", "competencies", "capability", "capabilities")),
    "experience_band": FieldSpec("experience_band", "_experienceBand", "Experience band", aliases=("experience band", "career stage", "experience level")),
    "au_experience_band": FieldSpec("au_experience_band", "_auExperienceBand", "Australian experience band", aliases=("australian experience band", "local experience band", "au experience band")),
    "total_experience": FieldSpec("total_experience", "Total Years of Experience", "Total years of experience", numeric=True, aliases=("average experience", "years of experience", "total experience")),
    "au_experience": FieldSpec("au_experience", "Australian Experience Years", "Australian experience years", numeric=True, aliases=("average australian experience", "australian experience years", "au experience years", "local experience years")),
    "business_domain": FieldSpec("business_domain", "Business Domains", "Business domain", multi=True, aliases=("business domain", "business domains", "domain", "domains")),
    "regulated_industry": FieldSpec("regulated_industry", "Regulated Industries", "Regulated industry", multi=True, aliases=("regulated industry", "regulated industries")),
    "employment_status": FieldSpec("employment_status", "Current Employment Status", "Employment status", aliases=("employment status", "currently employed", "current employment")),
    "full_work_rights": FieldSpec("full_work_rights", "Full Work Rights", "Full work rights", aliases=("full work rights", "work rights")),
    "australian_experience_flag": FieldSpec("australian_experience_flag", "Australian Employer Experience", "Australian employer experience", aliases=("australian employer experience", "local employer experience", "has australian experience")),
    "leadership": FieldSpec("leadership", "Leadership Experience", "Leadership experience", aliases=("leadership", "leadership experience")),
    "career_change": FieldSpec("career_change", "Career Change Detected", "Career change", aliases=("career change", "career changer", "career changers")),
    "extraction_status": FieldSpec("extraction_status", "Extraction Status", "Extraction status", aliases=("extraction status", "data status")),
}

APPROVED_OPERATORS = {"equals", "contains", "contains_any", "greater_than", "less_than", "between", "is_blank", "is_not_blank"}
APPROVED_INTENTS = {"rank", "count", "percentage", "compare", "cross_tab", "summary", "average"}
APPROVED_CHARTS = {"horizontal_bar", "vertical_bar", "donut", "heatmap", "grouped_bar", "none"}

STATE_ALIASES = {
    "victoria": "VIC", "vic": "VIC",
    "new south wales": "NSW", "nsw": "NSW",
    "queensland": "QLD", "qld": "QLD",
    "south australia": "SA", "sa": "SA",
    "western australia": "WA", "wa": "WA",
    "tasmania": "TAS", "tas": "TAS",
    "northern territory": "NT", "nt": "NT",
    "australian capital territory": "ACT", "canberra": "ACT", "act": "ACT",
}

VALUE_ALIASES = {
    "it": ("industry", "Information Technology"),
    "tech": ("industry", "Information Technology"),
    "technology": ("industry", "Information Technology"),
    "software": ("role_family", "Information Technology"),
    "ba": ("role", "Business Analyst"),
    "business analysts": ("role", "Business Analyst"),
    "business analyst": ("role", "Business Analyst"),
}

CERTIFICATION_ALIASES: list[tuple[re.Pattern[str], str]] = [
    (re.compile(r"^(?:construction induction(?: card)? ?(?:\(white card\))?|construction induction white card|white card)$", re.I), "White Card"),
    (re.compile(r"^(?:aws(?: certified)? cloud practitioner|cloud practitioner)$", re.I), "AWS Certified Cloud Practitioner"),
    (re.compile(r"^(?:(?:microsoft )?power ?bi(?: data analyst)?(?: associate)?|pl-?300)$", re.I), "Microsoft PL-300 Power BI Data Analyst"),
    (re.compile(r"^(?:google )?data analytics(?: professional certificate)?$", re.I), "Google Data Analytics Professional Certificate"),
    (re.compile(r"^(?:ccna(?: routing and switching)?|cisco certified network associate)$", re.I), "Cisco CCNA"),
    (re.compile(r"^(?:istqb.*|certified tester foundation level)$", re.I), "ISTQB Certified Tester"),
    (re.compile(r"^(?:working with children check|wwcc)$", re.I), "Working with Children Check"),
    (re.compile(r"^(?:first aid.*|provide first aid)$", re.I), "First Aid"),
    (re.compile(r"^(?:responsible service of alcohol|rsa)$", re.I), "Responsible Service of Alcohol"),
    (re.compile(r"^(?:scrum master|certified scrum master|csm)$", re.I), "Certified ScrumMaster"),
    (re.compile(r"^(?:azure fundamentals|microsoft certified: azure fundamentals|az-900)$", re.I), "Microsoft Azure Fundamentals"),
]

GENERAL_COMPLIANCE_PATTERN = re.compile(
    r"(?:white card|working with children|first aid|responsible service of alcohol|\brsa\b|police check|driver'?s licence|food safety|forklift|blue card|ndis worker screening|construction induction)",
    re.I,
)


def _env_data() -> dict[str, str]:
    try:
        values = dotenv_values(".env")
    except Exception:
        values = {}
    return {str(k): str(v) for k, v in values.items() if k and v is not None}


def env_value(name: str, default: str | None = None) -> str | None:
    value = os.getenv(name)
    if value is None:
        value = _env_data().get(name)
    if value is None:
        return default
    value = str(value).strip().strip('"').strip("'")
    return value or default


def discover_keys() -> list[tuple[str, str]]:
    env = _env_data()
    pairs: list[tuple[str, str]] = []
    for prefix in ("DASHBOARD_GROQ_API_KEY", "LLM_API_KEY", "GROQ_API_KEY"):
        for name in [prefix, *[f"{prefix}{index}" for index in range(2, 9)]]:
            value = os.getenv(name) or env.get(name)
            if value:
                pairs.append((name, str(value).strip()))
    output: list[tuple[str, str]] = []
    seen: set[str] = set()
    for label, value in pairs:
        if not value or value in seen:
            continue
        seen.add(value)
        output.append((label, value))
        if len(output) >= 8:
            break
    return output


def norm(value: Any) -> str:
    return re.sub(r"\s+", " ", str(value or "")).strip().casefold().replace("’", "'")


def clean(value: Any) -> str:
    return re.sub(r"\s+", " ", str(value or "")).strip()


def list_values(value: Any) -> list[str]:
    if value is None:
        return []
    if isinstance(value, (list, tuple, set)):
        values: list[str] = []
        for item in value:
            values.extend(list_values(item))
        return unique(values)
    if isinstance(value, dict):
        for key in ("name", "value", "label"):
            if key in value:
                return list_values(value[key])
        return []
    text = clean(value)
    if not text:
        return []
    if text.startswith("[") and text.endswith("]"):
        try:
            decoded = json.loads(text)
            if isinstance(decoded, list):
                return list_values(decoded)
        except json.JSONDecodeError:
            pass
    if ";" in text or "\n" in text or " | " in text:
        return unique(re.split(r"\s*(?:;|\n|\|)\s*", text))
    return [text]


def unique(values: Iterable[Any]) -> list[str]:
    output: list[str] = []
    seen: set[str] = set()
    for value in values:
        text = clean(value)
        if not text:
            continue
        token = norm(text)
        if token in seen:
            continue
        seen.add(token)
        output.append(text)
    return output


def number_value(value: Any) -> float | None:
    if value is None or isinstance(value, bool):
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        match = re.search(r"-?\d+(?:\.\d+)?", str(value))
        return float(match.group(0)) if match else None


def normalize_certification(value: str) -> str:
    text = clean(value).strip(".;,")
    for pattern, canonical in CERTIFICATION_ALIASES:
        if pattern.fullmatch(text):
            return canonical
    return text


def normalize_value(field_key: str, value: str) -> str:
    if field_key == "certification":
        return normalize_certification(value)
    if field_key == "state":
        return STATE_ALIASES.get(norm(value), clean(value).upper() if len(clean(value)) <= 4 else clean(value))
    return clean(value)


def record_values(record: dict[str, Any], field_key: str) -> list[str]:
    spec = FIELD_SPECS[field_key]
    values = list_values(record.get(spec.field)) if spec.multi else list_values(record.get(spec.field))[:1]
    return unique(normalize_value(field_key, value) for value in values)


def build_catalogs(records: list[dict[str, Any]], limit: int = 80) -> dict[str, list[str]]:
    catalogs: dict[str, list[str]] = {}
    for key, spec in FIELD_SPECS.items():
        if spec.numeric:
            continue
        counts: Counter[str] = Counter()
        display: dict[str, str] = {}
        for record in records:
            for value in record_values(record, key):
                token = norm(value)
                if token in {"", "unknown", "not specified", "n/a", "none"}:
                    continue
                counts[token] += 1
                display.setdefault(token, value)
        catalogs[key] = [display[token] for token, _count in counts.most_common(limit)]
    return catalogs


def _phrase_present(question: str, phrase: str) -> bool:
    q = norm(question)
    p = norm(phrase)
    if len(p) <= 3:
        return bool(re.search(rf"(?<!\w){re.escape(p)}(?!\w)", q))
    return p in q



# ---------------------------------------------------------------------------
# Natural-language query scope handling
# ---------------------------------------------------------------------------

QUERY_SCOPE_PATTERNS: dict[str, tuple[str, ...]] = {
    "state": (
        r"\b(?:for|across|throughout|covering|including)\s+all\s+(?:australian\s+)?states\b",
        r"\ball\s+(?:australian\s+)?states\b",
        r"\bacross\s+australia\b",
        r"\baustralia[- ]wide\b",
        r"\bnationwide\b",
        r"\bnationally\b",
    ),
    "city": (
        r"\b(?:for|across|throughout|covering|including)\s+all\s+cities\b",
        r"\ball\s+cities\b",
    ),
    "industry": (
        r"\b(?:for|across|throughout|covering|including)\s+all\s+(?:industries|sectors)\b",
        r"\ball\s+(?:industries|sectors)\b",
    ),
    "role": (
        r"\b(?:for|across|throughout|covering|including)\s+all\s+(?:roles|jobs|positions)\b",
        r"\ball\s+(?:roles|jobs|positions)\b",
    ),
    "visa": (
        r"\b(?:for|across|throughout|covering|including)\s+all\s+(?:visa types|visa categories|visas)\b",
        r"\ball\s+(?:visa types|visa categories|visas)\b",
    ),
}


def detect_scope_overrides(question: str) -> list[str]:
    q = norm(question)
    output: list[str] = []
    for field_key, patterns in QUERY_SCOPE_PATTERNS.items():
        if any(re.search(pattern, q, flags=re.I) for pattern in patterns):
            output.append(field_key)
    return output


def dimension_detection_text(question: str) -> str:
    # Remove phrases that describe global scope rather than group-by fields.
    q = norm(question)
    for patterns in QUERY_SCOPE_PATTERNS.values():
        for pattern in patterns:
            q = re.sub(pattern, " ", q, flags=re.I)
    return clean(q)


def effective_dashboard_filters(
    question: str,
    dashboard_filters: dict[str, Any] | None,
) -> tuple[dict[str, Any], list[str]]:
    # Explicit natural-language scope overrides active dashboard filters.
    effective = {
        key: value for key, value in dict(dashboard_filters or {}).items()
        if value not in (None, "", [])
    }
    overrides = detect_scope_overrides(question)
    for field_key in overrides:
        effective.pop(field_key, None)
    return effective, overrides

def detect_dimension(question: str) -> str | None:
    q = dimension_detection_text(question)
    # More specific phrases must win over general words like "institution".
    priority = [
        "certificate_institution", "certification", "education_institution",
        "education_country", "secondary_industry", "role_family", "current_job_title",
        "recent_job_title", "au_experience_band", "experience_band", "au_experience",
        "total_experience", "business_domain", "regulated_industry", "full_work_rights",
        "australian_experience_flag", "employment_status", "job_function", "qualification",
        "seniority", "industry", "role", "state", "city", "visa", "tool", "skill",
        "leadership", "career_change", "extraction_status",
    ]
    by_parts = re.split(r"\bby\b", q, maxsplit=1)
    if len(by_parts) == 2:
        left_side = by_parts[0]
        for key in priority:
            spec = FIELD_SPECS[key]
            if any(_phrase_present(left_side, alias) for alias in spec.aliases):
                return key

    for key in priority:
        spec = FIELD_SPECS[key]
        if any(_phrase_present(q, alias) for alias in spec.aliases):
            return key
    return None


def detect_secondary_dimension(question: str, primary: str | None) -> str | None:
    q = dimension_detection_text(question)
    by_parts = re.split(r"\bby\b", q, maxsplit=1)
    if len(by_parts) == 2:
        right_side = by_parts[1]
        for key, spec in FIELD_SPECS.items():
            if key != primary and any(_phrase_present(right_side, alias) for alias in spec.aliases):
                return key

    found: list[str] = []
    for key, spec in FIELD_SPECS.items():
        if key == primary:
            continue
        if any(_phrase_present(q, alias) for alias in spec.aliases):
            found.append(key)
    return found[0] if found else None


def detect_intent(question: str, primary: str | None) -> str:
    q = norm(question)
    if re.search(r"\b(compare|comparison|versus|vs\.?|difference between)\b", q):
        return "compare"
    if re.search(r"\b(relationship|cross[- ]?tab|breakdown .* by|by .* and|across .* by)\b", q):
        return "cross_tab"
    if re.search(r"\b(percentage|percent|share|proportion|what fraction|how many percent)\b", q):
        return "percentage"
    if re.search(r"\b(average|mean)\b", q) and primary in {"total_experience", "au_experience"}:
        return "average"
    if re.search(r"\b(top|most|popular|common|leading|highest|largest|rank|ranking|frequent|frequently)\b", q):
        return "rank"
    if re.search(r"\b(how many|number of|count)\b", q):
        return "count"
    if primary:
        return "rank"
    return "summary"


def _match_catalog_value(question: str, field_key: str, catalogs: dict[str, list[str]]) -> str | None:
    q = norm(question)
    values = sorted(catalogs.get(field_key, []), key=lambda x: len(norm(x)), reverse=True)
    for value in values:
        token = norm(value)
        if token and _phrase_present(q, token):
            return value
    return None


def infer_filters(question: str, primary: str | None, catalogs: dict[str, list[str]]) -> list[dict[str, Any]]:
    q = norm(question)
    filters: list[dict[str, Any]] = []
    used: set[tuple[str, str]] = set()

    for phrase, (field_key, canonical) in sorted(VALUE_ALIASES.items(), key=lambda x: len(x[0]), reverse=True):
        if field_key == primary:
            continue
        if _phrase_present(q, phrase):
            token = (field_key, norm(canonical))
            if token not in used:
                filters.append({"field": field_key, "operator": "equals", "value": canonical})
                used.add(token)

    for phrase, canonical in sorted(STATE_ALIASES.items(), key=lambda x: len(x[0]), reverse=True):
        if primary == "state":
            continue
        if _phrase_present(q, phrase):
            token = ("state", norm(canonical))
            if token not in used:
                filters.append({"field": "state", "operator": "equals", "value": canonical})
                used.add(token)
            break

    # Match concrete Airtable values mentioned in the question. Restrict to
    # common filter dimensions to avoid accidental matches in free text.
    for field_key in ("industry", "role", "role_family", "state", "city", "visa", "seniority", "qualification", "certification", "certificate_institution", "education_institution"):
        if field_key == primary:
            continue
        value = _match_catalog_value(q, field_key, catalogs)
        if value:
            token = (field_key, norm(value))
            if token not in used:
                filters.append({"field": field_key, "operator": "equals", "value": value})
                used.add(token)
    return filters


def infer_compare_values(question: str, dimension: str | None, catalogs: dict[str, list[str]]) -> list[str]:
    if not dimension:
        return []
    q = norm(question)
    values: list[str] = []
    for value in sorted(catalogs.get(dimension, []), key=lambda x: len(norm(x)), reverse=True):
        if _phrase_present(q, value):
            values.append(value)
    for phrase, (field_key, canonical) in VALUE_ALIASES.items():
        if field_key == dimension and _phrase_present(q, phrase):
            values.append(canonical)
    return unique(values)[:4]



def explicitly_mentioned_states(question: str) -> set[str]:
    """Return only state values explicitly written as complete tokens."""

    mentioned: set[str] = set()
    for phrase, canonical in STATE_ALIASES.items():
        if _phrase_present(question, phrase):
            mentioned.add(canonical)
    return mentioned


def enforce_state_filter_boundaries(question: str, plan: dict[str, Any]) -> dict[str, Any]:
    """Remove state filters inferred from letter sequences inside other words.

    Examples that must not create state filters:
      * visa     -> does not mean SA
      * clients  -> does not mean NT
      * fantastic -> does not mean TAS
      * service   -> does not mean VIC
      * answers   -> does not mean NSW
      * always    -> does not mean WA
      * action    -> does not mean ACT

    Explicit references such as SA, NT, Victoria or Canberra remain valid.
    """

    output = dict(plan)
    allowed_states = explicitly_mentioned_states(question)
    clean_filters: list[dict[str, Any]] = []

    for item in output.get("filters") or []:
        if not isinstance(item, dict) or item.get("field") != "state":
            clean_filters.append(item)
            continue

        raw_value = norm(item.get("value"))
        canonical = STATE_ALIASES.get(raw_value)
        if canonical is None:
            upper_value = clean(item.get("value")).upper()
            canonical = upper_value if upper_value in set(STATE_ALIASES.values()) else None

        if canonical and canonical in allowed_states:
            guarded = dict(item)
            guarded["value"] = canonical
            clean_filters.append(guarded)

    output["filters"] = clean_filters
    return output

def deterministic_plan(question: str, records: list[dict[str, Any]]) -> dict[str, Any]:
    catalogs = build_catalogs(records)
    scope_overrides = detect_scope_overrides(question)
    primary = detect_dimension(question)
    secondary = detect_secondary_dimension(question, primary)
    intent = detect_intent(question, primary)

    # Comparisons such as "Compare IT and Engineering clients" may mention
    # concrete values without naming the dimension. Infer the dimension whose
    # catalog contributes at least two mentioned values.
    if intent == "compare" and not primary:
        best_key = None
        best_values: list[str] = []
        for candidate in ("industry", "role_family", "role", "state", "visa", "qualification", "seniority"):
            values = infer_compare_values(question, candidate, catalogs)
            if len(values) > len(best_values):
                best_key, best_values = candidate, values
        primary = best_key or "industry"

    if not primary:
        primary = "industry"

    secondary = secondary or detect_secondary_dimension(question, primary)
    if secondary and re.search(r"\b(?:by|across)\b", norm(question)) and intent == "rank":
        intent = "cross_tab"

    filters = infer_filters(question, primary, catalogs)
    compare_values = infer_compare_values(question, primary, catalogs) if intent == "compare" else []
    if intent == "compare":
        # Values being compared belong in compare_values, not in the filter
        # list. Keep only contextual filters such as state or visa.
        filters = [item for item in filters if item["field"] not in {primary, "role_family" if primary == "industry" else "__none__"}]

    if intent == "cross_tab" and not secondary:
        secondary = "state" if primary != "state" else "industry"
    if intent == "compare" and not secondary:
        secondary = "role" if primary != "role" else "state"

    limit_match = re.search(r"\btop\s+(\d{1,2})\b", norm(question))
    limit = int(limit_match.group(1)) if limit_match else 10
    limit = max(1, min(limit, 25))

    chart = {
        "rank": "horizontal_bar",
        "count": "none",
        "percentage": "donut",
        "compare": "grouped_bar",
        "cross_tab": "heatmap",
        "summary": "horizontal_bar",
        "average": "none",
    }[intent]

    target_value = None
    if intent in {"percentage", "count"}:
        target_value = _match_catalog_value(question, primary, catalogs)

    return {
        "intent": intent,
        "dimension": primary,
        "secondary_dimension": secondary,
        "metric": "average" if intent == "average" else "client_count",
        "filters": filters,
        "compare_values": compare_values,
        "target_value": target_value,
        "limit": limit,
        "chart": chart,
        "source": "deterministic",
        "scope_overrides": scope_overrides,
        "interpretation": f"{intent} by {FIELD_SPECS[primary].label}",
    }


def validate_plan(plan: dict[str, Any]) -> dict[str, Any]:
    output = dict(plan)
    intent = str(output.get("intent") or "summary")
    if intent not in APPROVED_INTENTS:
        intent = "summary"
    output["intent"] = intent

    dimension = str(output.get("dimension") or "industry")
    if dimension not in FIELD_SPECS:
        dimension = "industry"
    output["dimension"] = dimension

    secondary = output.get("secondary_dimension")
    if secondary not in FIELD_SPECS or secondary == dimension:
        secondary = None
    output["secondary_dimension"] = secondary

    clean_filters: list[dict[str, Any]] = []
    for item in output.get("filters") or []:
        if not isinstance(item, dict):
            continue
        field = str(item.get("field") or "")
        operator = str(item.get("operator") or "equals")
        if field not in FIELD_SPECS or operator not in APPROVED_OPERATORS:
            continue
        clean_filters.append({"field": field, "operator": operator, "value": item.get("value")})
    output["filters"] = clean_filters[:8]

    output["scope_overrides"] = [
        value for value in unique(output.get("scope_overrides") or [])
        if value in FIELD_SPECS
    ][:8]
    output["compare_values"] = unique(output.get("compare_values") or [])[:4]
    output["limit"] = max(1, min(int(output.get("limit") or 10), 25))
    chart = str(output.get("chart") or "horizontal_bar")
    output["chart"] = chart if chart in APPROVED_CHARTS else "horizontal_bar"
    output["metric"] = "average" if intent == "average" else "client_count"
    output["target_value"] = clean(output.get("target_value")) or None
    return output


async def llm_plan(question: str, records: list[dict[str, Any]], deterministic: dict[str, Any]) -> tuple[dict[str, Any], str | None]:
    keys = discover_keys()
    enabled = norm(env_value("DASHBOARD_QUERY_PLANNER_ENABLED", "true")) not in {"false", "0", "no", "off"}
    if not keys or not enabled:
        return deterministic, None

    catalogs = build_catalogs(records, limit=20)
    compact_catalogs = {
        key: values[:12]
        for key, values in catalogs.items()
        if key in {"state", "industry", "role", "role_family", "visa", "qualification", "seniority", "certification", "certificate_institution", "education_institution"}
    }
    schema = {
        key: {"label": spec.label, "multi": spec.multi, "numeric": spec.numeric}
        for key, spec in FIELD_SPECS.items()
    }
    system = (
        "You are a query planner for DreamShift's Airtable analytics. Return JSON only. "
        "Choose only approved fields and operations from the supplied schema. Do not answer the question. "
        "The plan must have: intent, dimension, secondary_dimension, metric, filters, compare_values, target_value, limit, chart, interpretation. "
        "Valid intents: rank, count, percentage, compare, cross_tab, summary, average. "
        "Valid filter operators: equals, contains, contains_any, greater_than, less_than, between, is_blank, is_not_blank. "
        "For 'certificate institutions/providers' use certificate_institution. For universities or colleges use education_institution. "
        "For common IT certifications, use dimension certification and filter industry equals Information Technology. "
        "Phrases such as all states, across all states, nationwide or Australia-wide describe query scope: "
        "they remove an active state filter and must not make state the primary dimension. "
        "Only choose state as a dimension when the user explicitly asks for a state ranking, a breakdown by state, "
        "state-by-state results, or a comparison between states. "
        "Never invent a field. If the deterministic plan is already correct, preserve it."
    )
    user = json.dumps({
        "question": question,
        "deterministic_plan": deterministic,
        "approved_schema": schema,
        "known_values": compact_catalogs,
    }, ensure_ascii=False)
    payload = {
        "model": env_value("DASHBOARD_QUERY_MODEL") or env_value("DASHBOARD_CHAT_MODEL") or env_value("LLM_MODEL") or "openai/gpt-oss-20b",
        "temperature": 0,
        "max_completion_tokens": 650,
        "response_format": {"type": "json_object"},
        "messages": [
            {"role": "system", "content": system},
            {"role": "user", "content": user},
        ],
    }
    if str(payload["model"]).startswith("openai/gpt-oss"):
        payload["reasoning_effort"] = "low"
    endpoint = (env_value("DASHBOARD_LLM_BASE_URL") or env_value("LLM_BASE_URL") or "https://api.groq.com/openai/v1").rstrip("/") + "/chat/completions"
    timeout = float(env_value("DASHBOARD_QUERY_TIMEOUT_SECONDS", "35") or 35)
    last_error: Exception | None = None
    for label, key in keys:
        try:
            async with httpx.AsyncClient(timeout=httpx.Timeout(timeout)) as client:
                response = await client.post(endpoint, headers={"Authorization": f"Bearer {key}", "Content-Type": "application/json"}, json=payload)
            if response.status_code in {401, 403} or response.status_code >= 500:
                last_error = QueryEngineError(f"{label} returned HTTP {response.status_code}")
                continue
            if response.status_code == 429:
                return deterministic, None
            if response.status_code >= 400:
                last_error = QueryEngineError(f"Planner HTTP {response.status_code}: {response.text[:500]}")
                continue
            content = response.json().get("choices", [{}])[0].get("message", {}).get("content")
            parsed = json.loads(content)
            merged = dict(deterministic)
            merged.update(parsed if isinstance(parsed, dict) else {})
            # Preserve an explicitly detected field such as certificate
            # institution or education institution; these distinctions are
            # central to the user's question and should not be generalized.
            explicit_dimension = detect_dimension(question)
            if explicit_dimension:
                merged["dimension"] = explicit_dimension
            merged["source"] = "llm+deterministic"
            return validate_plan(merged), str(response.json().get("model") or payload["model"])
        except (httpx.HTTPError, json.JSONDecodeError, QueryEngineError) as exc:
            last_error = exc
            continue
    return deterministic, None


def _value_matches(actual_values: list[str], operator: str, expected: Any, numeric: bool) -> bool:
    if operator == "is_blank":
        return not actual_values
    if operator == "is_not_blank":
        return bool(actual_values)
    if numeric:
        actual = number_value(actual_values[0]) if actual_values else None
        if actual is None:
            return False
        if operator == "greater_than":
            return actual > float(expected)
        if operator == "less_than":
            return actual < float(expected)
        if operator == "between" and isinstance(expected, (list, tuple)) and len(expected) == 2:
            return float(expected[0]) <= actual <= float(expected[1])
        if operator == "equals":
            return actual == float(expected)
        return False

    expected_values = list_values(expected)
    actual_tokens = {norm(v) for v in actual_values}
    expected_tokens = {norm(v) for v in expected_values}
    if operator == "equals":
        return bool(actual_tokens & expected_tokens)
    if operator == "contains":
        needle = norm(expected_values[0]) if expected_values else ""
        return any(needle in token for token in actual_tokens)
    if operator == "contains_any":
        return any(any(needle in token for token in actual_tokens) for needle in expected_tokens)
    return False


def apply_plan_filters(records: list[dict[str, Any]], filters: list[dict[str, Any]]) -> list[dict[str, Any]]:
    output: list[dict[str, Any]] = []
    for record in records:
        matched = True
        for item in filters:
            field_key = item["field"]
            spec = FIELD_SPECS[field_key]
            values = record_values(record, field_key)
            if not _value_matches(values, item["operator"], item.get("value"), spec.numeric):
                matched = False
                break
        if matched:
            output.append(record)
    return output


def aggregate_rank(records: list[dict[str, Any]], dimension: str, limit: int) -> dict[str, Any]:
    counts: Counter[str] = Counter()
    labels: dict[str, str] = {}
    populated_clients = 0
    for record in records:
        values = [v for v in record_values(record, dimension) if norm(v) not in {"", "unknown", "not specified", "n/a", "none"}]
        if values:
            populated_clients += 1
        for value in unique(values):
            token = norm(value)
            counts[token] += 1
            labels.setdefault(token, value)
    denominator = len(records)
    rows = [
        {
            "label": labels[token],
            "count": count,
            "percentage": round(count / denominator * 100, 1) if denominator else 0,
            "percentage_of_populated": round(count / populated_clients * 100, 1) if populated_clients else 0,
            **({"category": "general_compliance" if GENERAL_COMPLIANCE_PATTERN.search(labels[token]) else "professional"} if dimension == "certification" else {}),
        }
        for token, count in counts.most_common(limit)
    ]
    return {
        "rows": rows,
        "denominator": denominator,
        "populated_clients": populated_clients,
        "coverage_percentage": round(populated_clients / denominator * 100, 1) if denominator else 0,
        "distinct_values": len(counts),
    }


def execute_plan(records: list[dict[str, Any]], plan: dict[str, Any]) -> dict[str, Any]:
    plan = validate_plan(plan)
    filtered = apply_plan_filters(records, plan["filters"])
    dimension = plan["dimension"]
    intent = plan["intent"]
    spec = FIELD_SPECS[dimension]

    if intent in {"rank", "summary"}:
        aggregate = aggregate_rank(filtered, dimension, plan["limit"])
        return {"kind": "ranking", "dimension": dimension, "filtered_records": len(filtered), **aggregate}

    if intent == "average":
        values = [number_value(record.get(spec.field)) for record in filtered]
        values = [value for value in values if value is not None]
        average = round(sum(values) / len(values), 2) if values else None
        return {"kind": "average", "dimension": dimension, "filtered_records": len(filtered), "populated_clients": len(values), "average": average, "minimum": min(values) if values else None, "maximum": max(values) if values else None}

    if intent == "count":
        target = plan.get("target_value")
        if target:
            numerator = sum(any(norm(v) == norm(target) for v in record_values(record, dimension)) for record in filtered)
            return {"kind": "count", "dimension": dimension, "target_value": target, "filtered_records": len(filtered), "count": numerator, "percentage": round(numerator / len(filtered) * 100, 1) if filtered else 0}
        populated = sum(bool(record_values(record, dimension)) for record in filtered)
        return {"kind": "count", "dimension": dimension, "filtered_records": len(filtered), "count": populated, "percentage": round(populated / len(filtered) * 100, 1) if filtered else 0}

    if intent == "percentage":
        target = plan.get("target_value")
        if target:
            numerator = sum(any(norm(v) == norm(target) for v in record_values(record, dimension)) for record in filtered)
        else:
            numerator = sum(bool(record_values(record, dimension)) for record in filtered)
        denominator = len(filtered)
        return {"kind": "percentage", "dimension": dimension, "target_value": target, "filtered_records": denominator, "count": numerator, "percentage": round(numerator / denominator * 100, 1) if denominator else 0}

    if intent == "cross_tab":
        secondary = plan.get("secondary_dimension") or ("state" if dimension != "state" else "industry")
        first_rank = aggregate_rank(filtered, dimension, min(plan["limit"], 8))["rows"]
        second_rank = aggregate_rank(filtered, secondary, min(plan["limit"], 8))["rows"]
        first_values = [row["label"] for row in first_rank]
        second_values = [row["label"] for row in second_rank]
        matrix: list[dict[str, Any]] = []
        for first in first_values:
            row = []
            for second in second_values:
                count = 0
                for record in filtered:
                    if any(norm(v) == norm(first) for v in record_values(record, dimension)) and any(norm(v) == norm(second) for v in record_values(record, secondary)):
                        count += 1
                row.append({"x": second, "y": count})
            matrix.append({"name": first, "data": row})
        return {"kind": "cross_tab", "dimension": dimension, "secondary_dimension": secondary, "filtered_records": len(filtered), "series": matrix, "categories": second_values}

    if intent == "compare":
        compare_values = plan.get("compare_values") or []
        if len(compare_values) < 2:
            compare_values = [row["label"] for row in aggregate_rank(filtered, dimension, 2)["rows"]]
        secondary = plan.get("secondary_dimension") or ("role" if dimension != "role" else "state")
        segments: dict[str, list[dict[str, Any]]] = {}
        combined_counts: Counter[str] = Counter()
        for value in compare_values[:4]:
            segment = [record for record in filtered if any(norm(v) == norm(value) for v in record_values(record, dimension))]
            segments[value] = segment
            for row in aggregate_rank(segment, secondary, 12)["rows"]:
                combined_counts[row["label"]] += row["count"]
        categories = [label for label, _count in combined_counts.most_common(min(plan["limit"], 10))]
        series = []
        for value, segment in segments.items():
            row_map = {row["label"]: row["count"] for row in aggregate_rank(segment, secondary, 30)["rows"]}
            series.append({"name": value, "data": [row_map.get(category, 0) for category in categories], "segment_count": len(segment)})
        return {"kind": "comparison", "dimension": dimension, "secondary_dimension": secondary, "filtered_records": len(filtered), "compare_values": list(segments), "categories": categories, "series": series}

    return {"kind": "ranking", "dimension": dimension, "filtered_records": len(filtered), **aggregate_rank(filtered, dimension, plan["limit"])}


def chart_from_result(plan: dict[str, Any], result: dict[str, Any]) -> dict[str, Any]:
    spec = FIELD_SPECS[plan["dimension"]]
    kind = result["kind"]
    if kind == "ranking":
        rows = result.get("rows") or []
        return {
            "type": "bar",
            "orientation": "horizontal",
            "title": f"Top {plural_label(spec.label)}",
            "categories": [row["label"] for row in rows],
            "series": [{"name": "Clients", "data": [row["count"] for row in rows]}],
            "meta": {"percentage_denominator": result.get("denominator"), "coverage_percentage": result.get("coverage_percentage")},
        }
    if kind == "percentage":
        value = result.get("percentage") or 0
        return {"type": "donut", "title": f"Share of filtered clients", "labels": ["Matches", "Other filtered clients"], "series": [result.get("count", 0), max(result.get("filtered_records", 0) - result.get("count", 0), 0)], "meta": {"percentage": value}}
    if kind == "cross_tab":
        return {"type": "heatmap", "title": f"{spec.label} × {FIELD_SPECS[result['secondary_dimension']].label}", "series": result.get("series") or []}
    if kind == "comparison":
        return {"type": "grouped_bar", "title": f"Compare {spec.label.lower()} segments", "categories": result.get("categories") or [], "series": [{"name": item["name"], "data": item["data"]} for item in result.get("series") or []]}
    return {"type": "none", "title": spec.label, "series": []}


def client_word(count: int) -> str:
    return "client" if int(count) == 1 else "clients"


def plural_label(label: str) -> str:
    lower = label.lower()
    irregular = {
        "primary industry": "primary industries",
        "secondary industry": "secondary industries",
        "city": "cities",
        "visa category": "visa categories",
        "education country": "education countries",
    }
    return irregular.get(lower, lower if lower.endswith("s") else lower + "s")


def deterministic_response(question: str, plan: dict[str, Any], result: dict[str, Any]) -> dict[str, Any]:
    spec = FIELD_SPECS[plan["dimension"]]
    filters = plan.get("filters") or []
    filter_text = ", ".join(f"{FIELD_SPECS[item['field']].label} = {item.get('value')}" for item in filters)
    scope_overrides = plan.get("scope_overrides") or []
    scope_labels = {
        "state": "all Australian states",
        "city": "all cities",
        "industry": "all industries",
        "role": "all target roles",
        "visa": "all visa categories",
    }
    global_scope = ", ".join(scope_labels[value] for value in scope_overrides if value in scope_labels)
    if filter_text and global_scope:
        scope_text = f" after applying {filter_text}, across {global_scope}"
    elif filter_text:
        scope_text = f" after applying {filter_text}"
    elif global_scope:
        scope_text = f" across {global_scope}"
    else:
        scope_text = ""
    findings: list[str] = []
    answer = ""
    pitch = ""
    opportunity = ""
    data_note = ""

    if result["kind"] == "ranking":
        rows = result.get("rows") or []
        if rows:
            top_text = ", ".join(f"{row['label']} ({row['count']} {client_word(row['count'])}, {row['percentage']}%)" for row in rows[:5])
            answer = f"The most common {plural_label(spec.label)}{scope_text} are {top_text}."
            findings = [f"#{index + 1} {row['label']}: {row['count']} {client_word(row['count'])} ({row['percentage']}% of the filtered segment)." for index, row in enumerate(rows[:5])]
            if plan["dimension"] == "certification":
                professional = [row for row in rows if row.get("category") == "professional"]
                compliance = [row for row in rows if row.get("category") == "general_compliance"]
                if professional:
                    professional_text = ", ".join(f"{row['label']} ({row['count']})" for row in professional[:5])
                    answer = f"The leading professional certifications{scope_text} are {professional_text}."
                if compliance:
                    compliance_text = ", ".join(f"{row['label']} ({row['count']})" for row in compliance[:4])
                    answer += f" General compliance credentials are separate: {compliance_text}."
            pitch = f"DreamShift’s client portfolio shows {rows[0]['label']} as the leading {spec.label.lower()}, represented across {rows[0]['count']} filtered client profiles."
            opportunity = f"Use the top {spec.label.lower()} segments to build proof-led landing pages, partnerships and campaign creative rather than relying on generic market claims."
        else:
            answer = f"No populated {spec.label.lower()} data was found for the current query scope."
            opportunity = "Improve field coverage before using this dimension in marketing claims."
        data_note = f"{result.get('populated_clients', 0)} of {result.get('denominator', 0)} filtered clients have populated {spec.label.lower()} data ({result.get('coverage_percentage', 0)}% coverage). Each client is counted once per unique value."

    elif result["kind"] == "average":
        answer = f"The average {spec.label.lower()}{scope_text} is {result.get('average') if result.get('average') is not None else 'not available'}."
        findings = [f"Populated records: {result.get('populated_clients', 0)}.", f"Observed range: {result.get('minimum')} to {result.get('maximum')}."]
        pitch = f"DreamShift supports a client base with an average {spec.label.lower()} of {result.get('average')}." if result.get("average") is not None else ""
        opportunity = "Segment campaigns by experience level and tailor proof points to the dominant career stage."
        data_note = "The average excludes blank or non-numeric records."

    elif result["kind"] in {"count", "percentage"}:
        target = result.get("target_value")
        label = f" with {spec.label.lower()} {target}" if target else f" with populated {spec.label.lower()} data"
        answer = f"{result.get('count', 0)} of {result.get('filtered_records', 0)} filtered clients{label}, equal to {result.get('percentage', 0)}%."
        findings = [answer]
        pitch = f"{result.get('percentage', 0)}% of the analysed DreamShift client segment{label}."
        opportunity = f"Use this percentage as a targeted proof point only when the current filter scope and denominator are disclosed."
        data_note = "The denominator is the currently filtered client segment."

    elif result["kind"] == "cross_tab":
        cells = []
        for series in result.get("series") or []:
            for item in series.get("data") or []:
                cells.append((item.get("y", 0), series.get("name"), item.get("x")))
        cells.sort(reverse=True)
        if cells and cells[0][0] > 0:
            count, first, second = cells[0]
            answer = f"The largest {spec.label.lower()} × {FIELD_SPECS[result['secondary_dimension']].label.lower()} intersection is {first} × {second}, with {count} clients."
            findings = [f"{first} × {second}: {count} clients." for count, first, second in cells[:5] if count > 0]
            pitch = f"DreamShift’s strongest combined client segment is {first} × {second}, represented by {count} profiles."
        else:
            answer = "No populated cross-tab intersections were found for the current filters."
        opportunity = "Use the strongest intersections for highly specific state, industry, role or education campaigns."
        data_note = "Cross-tab counts are calculated at client level from the selected dimensions."

    elif result["kind"] == "comparison":
        segments = result.get("series") or []
        counts = ", ".join(f"{item['name']}: {item.get('segment_count', 0)} {client_word(item.get('segment_count', 0))}" for item in segments)
        answer = f"The comparison covers {counts}. The chart shows their leading {FIELD_SPECS[result['secondary_dimension']].label.lower()} categories."
        findings = [f"{item['name']}: {item.get('segment_count', 0)} {client_word(item.get('segment_count', 0))} in the filtered dataset." for item in segments]
        pitch = f"DreamShift can demonstrate distinct portfolio patterns across {' and '.join(result.get('compare_values') or [])}."
        opportunity = "Build separate campaign narratives for each compared segment instead of treating them as one audience."
        data_note = "Comparison categories are ranked across the combined compared segments."

    return {
        "answer": answer,
        "key_findings": findings,
        "pitch_deck_line": pitch,
        "marketing_opportunity": opportunity,
        "data_note": data_note,
    }


async def llm_format(question: str, plan: dict[str, Any], result: dict[str, Any], deterministic: dict[str, Any]) -> tuple[dict[str, Any], str | None]:
    keys = discover_keys()
    enabled = norm(env_value("DASHBOARD_QUERY_FORMATTER_ENABLED", "true")) not in {"false", "0", "no", "off"}
    if not keys or not enabled:
        return deterministic, None
    system = (
        "You are DreamShift's business intelligence writer. The Python query engine has already calculated the exact result. "
        "Do not recalculate, invent, or replace any number. Answer the user's exact question, not a generic portfolio summary. "
        "Return JSON with answer, key_findings, pitch_deck_line, marketing_opportunity, data_note. "
        "Mention coverage limitations when present. These are DreamShift clients, not candidates. "
        "For certification questions, distinguish professional certifications from general compliance credentials."
    )
    payload = {
        "model": env_value("DASHBOARD_QUERY_MODEL") or env_value("DASHBOARD_CHAT_MODEL") or env_value("LLM_MODEL") or "openai/gpt-oss-20b",
        "temperature": 0.1,
        "max_completion_tokens": 750,
        "response_format": {"type": "json_object"},
        "messages": [
            {"role": "system", "content": system},
            {"role": "user", "content": json.dumps({"question": question, "validated_query_plan": plan, "exact_python_result": result, "deterministic_draft": deterministic}, ensure_ascii=False)},
        ],
    }
    if str(payload["model"]).startswith("openai/gpt-oss"):
        payload["reasoning_effort"] = "low"
    endpoint = (env_value("DASHBOARD_LLM_BASE_URL") or env_value("LLM_BASE_URL") or "https://api.groq.com/openai/v1").rstrip("/") + "/chat/completions"
    timeout = float(env_value("DASHBOARD_QUERY_TIMEOUT_SECONDS", "35") or 35)
    for label, key in keys:
        try:
            async with httpx.AsyncClient(timeout=httpx.Timeout(timeout)) as client:
                response = await client.post(endpoint, headers={"Authorization": f"Bearer {key}", "Content-Type": "application/json"}, json=payload)
            if response.status_code in {401, 403} or response.status_code >= 500:
                continue
            if response.status_code == 429:
                return deterministic, None
            if response.status_code >= 400:
                continue
            content = response.json().get("choices", [{}])[0].get("message", {}).get("content")
            parsed = json.loads(content)
            if not isinstance(parsed, dict):
                continue
            output = dict(deterministic)
            for field in ("answer", "key_findings", "pitch_deck_line", "marketing_opportunity", "data_note"):
                if field in parsed and parsed[field]:
                    output[field] = parsed[field]
            return output, str(response.json().get("model") or payload["model"])
        except (httpx.HTTPError, json.JSONDecodeError):
            continue
    return deterministic, None


async def execute_chat_query(records: list[dict[str, Any]], question: str, dashboard_filters: dict[str, Any] | None = None, preview_only: bool = False) -> dict[str, Any]:
    question = clean(question)
    deterministic = validate_plan(deterministic_plan(question, records))
    plan, planner_model = await llm_plan(question, records, deterministic)
    plan = validate_plan(plan)
    plan = enforce_state_filter_boundaries(question, plan)
    if preview_only:
        return {"question": question, "query_plan": plan, "planner_model": planner_model, "record_count": len(records)}

    result = execute_plan(records, plan)
    draft = deterministic_response(question, plan, result)
    formatted, formatter_model = await llm_format(question, plan, result, draft)
    chart = chart_from_result(plan, result)
    return {
        "mode": "query-engine",
        "question": question,
        "query_plan": plan,
        "result": result,
        "answer": formatted.get("answer") or draft["answer"],
        "key_findings": formatted.get("key_findings") or draft["key_findings"],
        "pitch_deck_line": formatted.get("pitch_deck_line") or draft["pitch_deck_line"],
        "marketing_opportunity": formatted.get("marketing_opportunity") or draft["marketing_opportunity"],
        "data_note": formatted.get("data_note") or draft["data_note"],
        "chart": chart,
        "filtered_client_count": result.get("filtered_records", len(records)),
        "planner_model": planner_model,
        "formatter_model": formatter_model,
        "model": formatter_model or planner_model,
        "dashboard_filters": dashboard_filters or {},
    }
