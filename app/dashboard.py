from __future__ import annotations

import asyncio
import json
import math
import os
import re
import time
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from urllib.parse import quote

import httpx
from dotenv import dotenv_values
from fastapi import APIRouter, HTTPException, Query
from fastapi.responses import HTMLResponse
from pydantic import BaseModel, Field

from app.config import get_settings
from app.query_engine import QueryEngineError, execute_chat_query


router = APIRouter(tags=["Client Intelligence Dashboard"])
BASE_DIR = Path(__file__).resolve().parent
DASHBOARD_HTML = BASE_DIR / "templates" / "dashboard.html"


FIELD_GROUPS: dict[str, list[str]] = {
    "Client & extraction": [
        "Full Name",
        "Resume Source URL",
        "confident_score",
        "Extraction Status",
    ],
    "Location & work rights": [
        "Current City",
        "Current State",
        "Visa Category",
        "Full Work Rights",
    ],
    "Career targets": [
        "Current Job Title",
        "Most Recent Job Title",
        "Primary Target Role",
        "Secondary Target Roles",
        "Role Family",
        "Job Function",
        "Seniority Level",
    ],
    "Experience": [
        "Total Years of Experience",
        "Australian Experience Years",
        "Overseas Experience Years",
        "Current Employer",
        "Previous Employers",
        "Number of Employers",
        "Leadership Experience",
        "Leadership Experience Years",
        "Most Recent Employment Start Date",
        "Employment Gap Detected",
        "Career Change Detected",
        "Australian Employer Experience",
        "Current Employment Status",
    ],
    "Industry": [
        "Primary Industry",
        "Secondary Industries",
        "Sub-Industries",
        "Business Domains",
        "Regulated Industry Experience",
        "Regulated Industries",
        "Industry Experience Years",
    ],
    "Skills & certifications": [
        "Core Professional Skills",
        "Technical Skills",
        "Tools and Platforms",
        "Number of Certificates",
        "Certificate Names",
        "Certificate Institutions",
    ],
    "Education summary": [
        "Highest Qualification Level",
        "Number of Qualifications",
        "Education Countries",
    ],
    "PhD": [
        "PhD",
        "PhD Qualification Name",
        "PhD Field of Study",
        "PhD Institution",
        "PhD Institution Country",
        "PhD Completion Year",
        "PhD Status",
        "Australian PhD",
    ],
    "Master’s education": [
        "Master’s Degree",
        "Number of Master’s Degrees",
        "Master’s Qualification Names",
        "Master’s Fields of Study",
        "Master’s Institutions",
        "Master’s Institution Countries",
        "Master’s Completion Years",
        "Master’s Status",
        "Australian Master’s Degree",
    ],
    "Bachelor’s education": [
        "Bachelor’s Degree",
        "Number of Bachelor’s Degrees",
        "Bachelor’s Qualification Names",
        "Bachelor’s Fields of Study",
        "Bachelor’s Institutions",
        "Bachelor’s Institution Countries",
        "Bachelor’s Completion Years",
        "Bachelor’s Status",
        "Australian Bachelor’s Degree",
    ],
    "Other education": [
        "Other Qualifications",
        "Number of Other Qualifications",
        "Other Qualification Names",
        "Other Qualification Levels",
        "Other Qualification Fields",
        "Other Institutions",
        "Other Institution Countries",
        "Other Qualification Completion Years",
        "Other Qualification Status",
        "Australian Other Qualification",
    ],
}

EXPECTED_FIELDS = [field for fields in FIELD_GROUPS.values() for field in fields]

# Only aggregate/segmentation fields are sent to the browser. Names, employers,
# source URLs and other direct identifiers remain server-side.
ANALYTICS_FIELDS = [
    "Current City",
    "Current State",
    "Visa Category",
    "Full Work Rights",
    "Current Job Title",
    "Most Recent Job Title",
    "Primary Target Role",
    "Secondary Target Roles",
    "Role Family",
    "Job Function",
    "Seniority Level",
    "Total Years of Experience",
    "Australian Experience Years",
    "Overseas Experience Years",
    "Leadership Experience",
    "Leadership Experience Years",
    "Employment Gap Detected",
    "Career Change Detected",
    "Australian Employer Experience",
    "Current Employment Status",
    "Primary Industry",
    "Secondary Industries",
    "Sub-Industries",
    "Business Domains",
    "Regulated Industry Experience",
    "Regulated Industries",
    "Industry Experience Years",
    "Core Professional Skills",
    "Technical Skills",
    "Tools and Platforms",
    "Number of Certificates",
    "Certificate Names",
    "Certificate Institutions",
    "Highest Qualification Level",
    "Number of Qualifications",
    "Education Countries",
    "PhD",
    "PhD Institution",
    "PhD Institution Country",
    "Australian PhD",
    "Master’s Degree",
    "Master’s Institutions",
    "Master’s Institution Countries",
    "Australian Master’s Degree",
    "Bachelor’s Degree",
    "Bachelor’s Institutions",
    "Bachelor’s Institution Countries",
    "Australian Bachelor’s Degree",
    "Other Qualifications",
    "Other Institutions",
    "Other Institution Countries",
    "Australian Other Qualification",
    "Extraction Status",
]

FILTER_FIELD_MAP = {
    "state": "Current State",
    "city": "Current City",
    "industry": "Primary Industry",
    "role_family": "Role Family",
    "role": "Primary Target Role",
    "visa": "Visa Category",
    "seniority": "Seniority Level",
    "qualification": "Highest Qualification Level",
}

DIMENSIONS: dict[str, dict[str, Any]] = {
    "state": {"label": "State", "field": "Current State", "multi": False},
    "city": {"label": "City", "field": "Current City", "multi": False},
    "industry": {"label": "Primary industry", "field": "Primary Industry", "multi": False},
    "role_family": {"label": "Role family", "field": "Role Family", "multi": False},
    "role": {"label": "Primary target role", "field": "Primary Target Role", "multi": False},
    "job_function": {"label": "Job function", "field": "Job Function", "multi": False},
    "visa": {"label": "Visa category", "field": "Visa Category", "multi": False},
    "seniority": {"label": "Seniority", "field": "Seniority Level", "multi": False},
    "qualification": {"label": "Highest qualification", "field": "Highest Qualification Level", "multi": False},
    "university": {"label": "Education institution", "field": "_institutions", "multi": True},
    "education_country": {"label": "Education country", "field": "_educationCountries", "multi": True},
    "experience": {"label": "Total experience band", "field": "_experienceBand", "multi": False},
    "au_experience": {"label": "Australian experience band", "field": "_auExperienceBand", "multi": False},
    "business_domain": {"label": "Business domain", "field": "Business Domains", "multi": True},
    "regulated_industry": {"label": "Regulated industry", "field": "Regulated Industries", "multi": True},
    "tools": {"label": "Tool or platform", "field": "Tools and Platforms", "multi": True},
    "skills": {"label": "Skill", "field": "_skills", "multi": True},
    "certification": {"label": "Certification", "field": "Certificate Names", "multi": True},
}

DIMENSION_KEYWORDS: list[tuple[str, tuple[str, ...]]] = [
    ("university", ("university", "universities", "institution", "college", "graduates", "studied", "alumni")),
    ("education_country", ("education country", "country of education", "studied overseas", "study country")),
    ("au_experience", ("australian experience", "au experience", "local experience")),
    ("experience", ("experience", "years of experience", "career stage")),
    ("role_family", ("role family", "career family", "profession family")),
    ("role", ("job role", "target role", "roles", "role", "positions", "jobs")),
    ("job_function", ("job function", "function")),
    ("industry", ("industry", "industries", "sector", "sectors")),
    ("state", ("state", "states", "victoria", "vic", "nsw", "queensland", "qld", "wa", "sa", "tasmania", "act")),
    ("city", ("city", "cities", "melbourne", "sydney", "brisbane", "adelaide", "perth", "canberra", "geelong")),
    ("visa", ("visa", "work rights", "migration status")),
    ("seniority", ("seniority", "senior", "junior", "graduate", "entry level", "manager")),
    ("qualification", ("qualification", "degree", "masters", "master's", "phd", "doctorate", "bachelor", "postgraduate")),
    ("business_domain", ("business domain", "domain", "domains")),
    ("regulated_industry", ("regulated industry", "regulated industries", "regulated")),
    ("tools", ("tools", "platforms", "software", "technologies")),
    ("skills", ("skills", "capabilities", "competencies")),
    ("certification", ("certification", "certifications", "certificates")),
]



# ---------------------------------------------------------------------------
# DreamShift Intelligence V2: certification normalization and exact denominators
# ---------------------------------------------------------------------------

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
    r"(?:white card|working with children|first aid|responsible service of alcohol|"
    r"\brsa\b|police check|driver'?s licence|food safety|forklift|blue card|"
    r"ndis worker screening|construction induction)",
    re.I,
)


def normalize_certification(value: str) -> str:
    text = re.sub(r"\s+", " ", str(value or "")).strip(" \t\r\n.;,")
    for pattern, canonical in CERTIFICATION_ALIASES:
        if pattern.fullmatch(text):
            return canonical
    return text


def certification_category(value: str) -> str:
    return "general_compliance" if GENERAL_COMPLIANCE_PATTERN.search(value) else "professional"


def certification_distribution(
    records: list[dict[str, Any]],
    category: str | None = None,
    limit: int = 30,
) -> list[dict[str, Any]]:
    counts: Counter[str] = Counter()
    labels: dict[str, str] = {}
    for record in records:
        normalized = unique_strings(
            [normalize_certification(v) for v in list_values(record.get("Certificate Names"))]
        )
        for certification in normalized:
            if not certification:
                continue
            if category and certification_category(certification) != category:
                continue
            token = normalized_key(certification)
            labels.setdefault(token, certification)
            counts[token] += 1

    denominator = len(records)
    return [
        {
            "label": labels[token],
            "count": count,
            "percentage": round(count / denominator * 100, 1) if denominator else 0,
            "denominator": denominator,
            "category": certification_category(labels[token]),
        }
        for token, count in counts.most_common(limit)
    ]


def certification_question_snapshot(records: list[dict[str, Any]]) -> dict[str, Any]:
    return {
        "denominator_definition": "currently filtered DreamShift clients",
        "denominator": len(records),
        "professional_certifications": certification_distribution(
            records, category="professional", limit=20
        ),
        "general_compliance_credentials": certification_distribution(
            records, category="general_compliance", limit=20
        ),
        "rules": [
            "Aliases are normalized before counting.",
            "Each client is counted at most once per normalized certification.",
            "Percentages use the filtered client count as the denominator.",
            "General compliance cards and checks are separated from career-relevant professional certifications.",
        ],
    }


class AskDashboardRequest(BaseModel):
    question: str = Field(min_length=2, max_length=800)
    filters: dict[str, Any] = Field(default_factory=dict)


class DashboardError(RuntimeError):
    pass


class DashboardRateLimitError(DashboardError):
    def __init__(self, message: str, retry_after: float | None = None):
        super().__init__(message)
        self.retry_after = retry_after


def utc_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


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


def env_int(name: str, default: int, minimum: int, maximum: int) -> int:
    raw = env_value(name)
    try:
        value = int(raw) if raw is not None else default
    except (TypeError, ValueError):
        value = default
    return max(minimum, min(value, maximum))


def normalized_key(value: str) -> str:
    return value.casefold().replace("’", "'").strip()


def get_field(fields: dict[str, Any], name: str, default: Any = None) -> Any:
    if name in fields:
        return fields[name]
    wanted = normalized_key(name)
    for key, value in fields.items():
        if normalized_key(str(key)) == wanted:
            return value
    return default


def is_blank(value: Any) -> bool:
    if value is None:
        return True
    if isinstance(value, str):
        return not value.strip()
    if isinstance(value, (list, tuple, set, dict)):
        return len(value) == 0
    return False


def list_values(value: Any) -> list[str]:
    if value is None:
        return []
    if isinstance(value, (list, tuple, set)):
        values: list[str] = []
        for item in value:
            values.extend(list_values(item))
        return unique_strings(values)
    if isinstance(value, dict):
        for key in ("name", "value", "label"):
            if key in value:
                return list_values(value[key])
        return []
    text = str(value).strip()
    if not text:
        return []
    if text.startswith("[") and text.endswith("]"):
        try:
            decoded = json.loads(text)
            if isinstance(decoded, list):
                return list_values(decoded)
        except json.JSONDecodeError:
            pass
    # Airtable multi-select values normally arrive as arrays. This fallback
    # handles older text fields while avoiding splitting names on plain commas
    # unless a clear list delimiter exists.
    if ";" in text or "\n" in text or " | " in text:
        parts = re.split(r"\s*(?:;|\n|\|)\s*", text)
        return unique_strings(parts)
    return [text]


def unique_strings(values: list[Any]) -> list[str]:
    output: list[str] = []
    seen: set[str] = set()
    for value in values:
        text = str(value).strip() if value is not None else ""
        if not text:
            continue
        key = normalized_key(text)
        if key not in seen:
            seen.add(key)
            output.append(text)
    return output


def number_value(value: Any) -> float | None:
    if value is None or isinstance(value, bool):
        return None
    try:
        number = float(value)
    except (TypeError, ValueError):
        match = re.search(r"-?\d+(?:\.\d+)?", str(value))
        if not match:
            return None
        number = float(match.group(0))
    if not math.isfinite(number):
        return None
    return number


def experience_band(value: Any) -> str:
    number = number_value(value)
    if number is None:
        return "Not specified"
    if number <= 0:
        return "No experience"
    if number < 1:
        return "Under 1 year"
    if number < 3:
        return "1–2.9 years"
    if number < 5:
        return "3–4.9 years"
    if number < 8:
        return "5–7.9 years"
    if number < 11:
        return "8–10.9 years"
    return "11+ years"


def yes_value(value: Any) -> bool:
    if isinstance(value, bool):
        return value
    return str(value or "").strip().casefold() in {"yes", "true", "1", "checked"}


def education_institutions(fields: dict[str, Any]) -> list[str]:
    values: list[str] = []
    for field in (
        "PhD Institution",
        "Master’s Institutions",
        "Bachelor’s Institutions",
        "Other Institutions",
    ):
        values.extend(list_values(get_field(fields, field)))
    return unique_strings(values)


def education_countries(fields: dict[str, Any]) -> list[str]:
    values: list[str] = []
    for field in (
        "Education Countries",
        "PhD Institution Country",
        "Master’s Institution Countries",
        "Bachelor’s Institution Countries",
        "Other Institution Countries",
    ):
        values.extend(list_values(get_field(fields, field)))
    return unique_strings(values)


def has_australian_qualification(fields: dict[str, Any]) -> str:
    flags = [
        get_field(fields, "Australian PhD"),
        get_field(fields, "Australian Master’s Degree"),
        get_field(fields, "Australian Bachelor’s Degree"),
        get_field(fields, "Australian Other Qualification"),
    ]
    if any(yes_value(flag) for flag in flags):
        return "Yes"
    if any(not is_blank(flag) for flag in flags):
        return "No"
    countries = [value.casefold() for value in education_countries(fields)]
    if any(value == "australia" for value in countries):
        return "Yes"
    return "Unknown"


def has_postgraduate(fields: dict[str, Any]) -> str:
    highest = str(get_field(fields, "Highest Qualification Level") or "").casefold()
    if any(token in highest for token in ("phd", "doctor", "master", "postgraduate")):
        return "Yes"
    if yes_value(get_field(fields, "PhD")) or yes_value(get_field(fields, "Master’s Degree")):
        return "Yes"
    if highest:
        return "No"
    return "Unknown"


def derive_analytics_record(record: dict[str, Any]) -> dict[str, Any]:
    fields = record.get("fields") or {}
    output: dict[str, Any] = {
        "_id": record.get("id"),
        "_createdTime": record.get("createdTime"),
    }
    for field in ANALYTICS_FIELDS:
        value = get_field(fields, field)
        if not is_blank(value):
            output[field] = value

    output["_institutions"] = education_institutions(fields)
    output["_educationCountries"] = education_countries(fields)
    output["_experienceBand"] = experience_band(get_field(fields, "Total Years of Experience"))
    output["_auExperienceBand"] = experience_band(get_field(fields, "Australian Experience Years"))
    output["_hasAustralianQualification"] = has_australian_qualification(fields)
    output["_postgraduate"] = has_postgraduate(fields)
    output["_skills"] = unique_strings(
        list_values(get_field(fields, "Core Professional Skills"))
        + list_values(get_field(fields, "Technical Skills"))
    )
    return output


class AirtableDashboardClient:
    def __init__(self) -> None:
        settings = get_settings()
        token = settings.effective_airtable_token
        if not token:
            raise DashboardError("Missing AIRTABLE_TOKEN or AIRTABLE_PAT in .env.")
        self.token = token
        self.base_id = settings.airtable_base_id
        self.table_id = settings.airtable_table_id
        if not self.base_id:
            raise DashboardError("Missing AIRTABLE_BASE_ID in .env.")
        if not self.table_id:
            raise DashboardError("Missing AIRTABLE_TABLE_ID in .env.")
        self.headers = {"Authorization": f"Bearer {token}"}
        self.endpoint = (
            "https://api.airtable.com/v0/"
            f"{quote(self.base_id, safe='')}/"
            f"{quote(self.table_id, safe='')}"
        )
        self.schema_endpoint = (
            "https://api.airtable.com/v0/meta/bases/"
            f"{quote(self.base_id, safe='')}/tables"
        )

    async def list_records(self) -> list[dict[str, Any]]:
        records: list[dict[str, Any]] = []
        offset: str | None = None
        view = env_value("DASHBOARD_AIRTABLE_VIEW")
        timeout = httpx.Timeout(60.0)

        async with httpx.AsyncClient(timeout=timeout) as client:
            while True:
                params: dict[str, Any] = {"pageSize": 100}
                if offset:
                    params["offset"] = offset
                if view:
                    params["view"] = view

                response = await client.get(
                    self.endpoint,
                    headers=self.headers,
                    params=params,
                )
                if response.status_code >= 400:
                    raise DashboardError(
                        f"Airtable records HTTP {response.status_code}: "
                        f"{response.text[:2000]}"
                    )
                payload = response.json()
                page = payload.get("records") or []
                records.extend(page)
                offset = payload.get("offset")
                if not offset:
                    break
                # Airtable's per-base limit is five requests per second.
                await asyncio.sleep(0.22)
        return records

    async def get_schema(self) -> tuple[list[dict[str, Any]], str]:
        timeout = httpx.Timeout(30.0)
        async with httpx.AsyncClient(timeout=timeout) as client:
            response = await client.get(
                self.schema_endpoint,
                headers=self.headers,
            )
        if response.status_code in {401, 403}:
            return [], "inferred"
        if response.status_code >= 400:
            return [], "inferred"

        tables = response.json().get("tables") or []
        for table in tables:
            if table.get("id") == self.table_id or table.get("name") == self.table_id:
                return table.get("fields") or [], "metadata"
        return [], "inferred"


_CACHE_LOCK = asyncio.Lock()
_DATA_CACHE: dict[str, Any] = {
    "records": None,
    "raw_records": None,
    "fetched_at": None,
    "fetched_monotonic": 0.0,
    "schema": None,
    "schema_source": "inferred",
}


async def get_dashboard_records(force: bool = False) -> tuple[list[dict[str, Any]], list[dict[str, Any]], str]:
    cache_seconds = env_int("DASHBOARD_CACHE_SECONDS", 30, 5, 3600)
    async with _CACHE_LOCK:
        fresh = (
            _DATA_CACHE["records"] is not None
            and (time.monotonic() - float(_DATA_CACHE["fetched_monotonic"])) < cache_seconds
        )
        if fresh and not force:
            return (
                list(_DATA_CACHE["records"]),
                list(_DATA_CACHE.get("schema") or []),
                str(_DATA_CACHE.get("schema_source") or "inferred"),
            )

        client = AirtableDashboardClient()
        raw_records = await client.list_records()
        schema, schema_source = await client.get_schema()
        records = [derive_analytics_record(record) for record in raw_records]

        _DATA_CACHE.update(
            {
                "records": records,
                "raw_records": raw_records,
                "fetched_at": utc_iso(),
                "fetched_monotonic": time.monotonic(),
                "schema": schema,
                "schema_source": schema_source,
            }
        )
        return list(records), list(schema), schema_source


def schema_payload(
    raw_records: list[dict[str, Any]],
    schema: list[dict[str, Any]],
    schema_source: str,
) -> dict[str, Any]:
    total = len(raw_records)
    metadata_by_name = {
        normalized_key(str(field.get("name"))): field
        for field in schema
        if field.get("name")
    }
    observed_names: set[str] = set()
    coverage_counts: Counter[str] = Counter()

    for record in raw_records:
        fields = record.get("fields") or {}
        for name, value in fields.items():
            observed_names.add(str(name))
            if not is_blank(value):
                coverage_counts[str(name)] += 1

    groups: list[dict[str, Any]] = []
    for group_name, expected in FIELD_GROUPS.items():
        field_items: list[dict[str, Any]] = []
        for field_name in expected:
            metadata = metadata_by_name.get(normalized_key(field_name), {})
            observed_match = next(
                (name for name in observed_names if normalized_key(name) == normalized_key(field_name)),
                None,
            )
            actual_name = str(metadata.get("name") or observed_match or field_name)
            count = coverage_counts.get(actual_name, 0)
            field_items.append(
                {
                    "name": field_name,
                    "actual_name": actual_name,
                    "present": bool(metadata or observed_match),
                    "type": metadata.get("type") or "inferred",
                    "filled": count,
                    "coverage": round((count / total * 100), 1) if total else 0,
                }
            )
        groups.append({"name": group_name, "fields": field_items})

    unexpected = sorted(
        name
        for name in observed_names
        if normalized_key(name) not in {normalized_key(field) for field in EXPECTED_FIELDS}
    )

    return {
        "source": schema_source,
        "groups": groups,
        "expected_field_count": len(EXPECTED_FIELDS),
        "present_expected_count": sum(
            item["present"] for group in groups for item in group["fields"]
        ),
        "unexpected_fields": unexpected,
    }


def scalar_text(value: Any) -> str | None:
    values = list_values(value)
    return values[0] if values else None


def record_dimension_values(record: dict[str, Any], dimension: str) -> list[str]:
    definition = DIMENSIONS[dimension]
    value = record.get(definition["field"])
    values = list_values(value) if definition["multi"] else ([scalar_text(value)] if scalar_text(value) else [])
    if dimension == "certification":
        values = [normalize_certification(item) for item in values]
    return unique_strings(values)


def distribution(records: list[dict[str, Any]], dimension: str, limit: int = 20) -> list[dict[str, Any]]:
    counts: Counter[str] = Counter()
    for record in records:
        for value in record_dimension_values(record, dimension):
            if value and value.casefold() not in {"unknown", "not specified", "n/a", "none"}:
                counts[value] += 1
    total = len(records)
    return [
        {
            "label": label,
            "count": count,
            "percentage": round(count / total * 100, 1) if total else 0,
        }
        for label, count in counts.most_common(limit)
    ]


def cross_tab(
    records: list[dict[str, Any]],
    first_dimension: str,
    second_dimension: str,
    limit: int = 20,
) -> list[dict[str, Any]]:
    counts: Counter[tuple[str, str]] = Counter()
    for record in records:
        first_values = record_dimension_values(record, first_dimension)
        second_values = record_dimension_values(record, second_dimension)
        for first in first_values:
            for second in second_values:
                counts[(first, second)] += 1
    total = len(records)
    return [
        {
            "first": first,
            "second": second,
            "count": count,
            "percentage": round(count / total * 100, 1) if total else 0,
        }
        for (first, second), count in counts.most_common(limit)
    ]


def percentage_yes(records: list[dict[str, Any]], field: str) -> float | None:
    known = [record for record in records if not is_blank(record.get(field))]
    if not known:
        return None
    yes_count = sum(yes_value(record.get(field)) for record in known)
    return round(yes_count / len(known) * 100, 1)


def percentage_derived(records: list[dict[str, Any]], field: str, yes_text: str = "Yes") -> float | None:
    known = [record for record in records if str(record.get(field) or "").casefold() not in {"", "unknown"}]
    if not known:
        return None
    yes_count = sum(str(record.get(field) or "").casefold() == yes_text.casefold() for record in known)
    return round(yes_count / len(known) * 100, 1)


def distinct_count(records: list[dict[str, Any]], dimension: str) -> int:
    values: set[str] = set()
    for record in records:
        values.update(normalized_key(value) for value in record_dimension_values(record, dimension))
    return len(values)


def metrics_payload(records: list[dict[str, Any]]) -> dict[str, Any]:
    return {
        "total_clients": len(records),
        "states_represented": distinct_count(records, "state"),
        "industries_represented": distinct_count(records, "industry"),
        "role_families_represented": distinct_count(records, "role_family"),
        "target_roles_represented": distinct_count(records, "role"),
        "institutions_represented": distinct_count(records, "university"),
        "education_countries_represented": distinct_count(records, "education_country"),
        "full_work_rights_percentage": percentage_yes(records, "Full Work Rights"),
        "australian_experience_percentage": percentage_yes(records, "Australian Employer Experience"),
        "leadership_percentage": percentage_yes(records, "Leadership Experience"),
        "career_change_percentage": percentage_yes(records, "Career Change Detected"),
        "regulated_industry_percentage": percentage_yes(records, "Regulated Industry Experience"),
        "australian_qualification_percentage": percentage_derived(records, "_hasAustralianQualification"),
        "postgraduate_percentage": percentage_derived(records, "_postgraduate"),
    }


def match_filter(record: dict[str, Any], field: str, selected: Any) -> bool:
    if selected is None or selected == "" or selected == []:
        return True
    selected_values = list_values(selected)
    if not selected_values:
        return True
    record_values = list_values(record.get(field))
    record_keys = {normalized_key(value) for value in record_values}
    return any(normalized_key(value) in record_keys for value in selected_values)


def parse_created_date(value: Any) -> datetime | None:
    if not value:
        return None
    try:
        return datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    except ValueError:
        return None


def apply_filters(records: list[dict[str, Any]], filters: dict[str, Any]) -> list[dict[str, Any]]:
    output: list[dict[str, Any]] = []
    date_from_text = str(filters.get("date_from") or "").strip()
    date_to_text = str(filters.get("date_to") or "").strip()
    try:
        date_from = datetime.fromisoformat(date_from_text).replace(tzinfo=timezone.utc) if date_from_text else None
    except ValueError:
        date_from = None
    try:
        date_to = datetime.fromisoformat(date_to_text).replace(tzinfo=timezone.utc) if date_to_text else None
    except ValueError:
        date_to = None

    for record in records:
        if any(
            not match_filter(record, field, filters.get(filter_name))
            for filter_name, field in FILTER_FIELD_MAP.items()
        ):
            continue
        created = parse_created_date(record.get("_createdTime"))
        if date_from and created and created < date_from:
            continue
        if date_to and created and created.date() > date_to.date():
            continue
        output.append(record)
    return output


def detect_dimensions(question: str) -> list[str]:
    lowered = question.casefold()
    found: list[str] = []
    for dimension, keywords in DIMENSION_KEYWORDS:
        if any(keyword in lowered for keyword in keywords):
            found.append(dimension)
    return found[:3]


def build_snapshot(records: list[dict[str, Any]], question: str, filters: dict[str, Any]) -> dict[str, Any]:
    detected = detect_dimensions(question)
    default_dimensions = [
        "industry",
        "state",
        "role_family",
        "role",
        "university",
        "visa",
        "qualification",
        "experience",
    ]
    requested = unique_strings(detected + default_dimensions)
    distributions = {
        dimension: {
            "label": DIMENSIONS[dimension]["label"],
            "basis": "clients; multi-value dimensions may total above 100%",
            "values": distribution(records, dimension, 12),
        }
        for dimension in requested
    }
    cross_tabs: list[dict[str, Any]] = []
    if len(detected) >= 2:
        for index in range(min(len(detected) - 1, 2)):
            first = detected[index]
            second = detected[index + 1]
            cross_tabs.append(
                {
                    "first_dimension": first,
                    "first_label": DIMENSIONS[first]["label"],
                    "second_dimension": second,
                    "second_label": DIMENSIONS[second]["label"],
                    "values": cross_tab(records, first, second, 15),
                }
            )
    payload = {
        "question": question,
        "filters": filters,
        "metrics": metrics_payload(records),
        "detected_dimensions": detected,
        "distributions": distributions,
        "cross_tabs": cross_tabs,
        "data_rules": [
            "One Airtable record is treated as one DreamShift client.",
            "Institution counts deduplicate the same institution within one client record.",
            "Percentages for multi-value fields may sum above 100 percent.",
            "No client names, employers, CV text, contact details or source URLs are included.",
        ],
    }
    if "certification" in detected:
        payload["certification_analysis"] = certification_question_snapshot(records)
    return payload


def top_item(snapshot: dict[str, Any], dimension: str) -> dict[str, Any] | None:
    values = snapshot.get("distributions", {}).get(dimension, {}).get("values", [])
    return values[0] if values else None


def deterministic_answer(snapshot: dict[str, Any]) -> dict[str, Any]:
    metrics = snapshot["metrics"]
    total = metrics["total_clients"]
    industry = top_item(snapshot, "industry")
    state = top_item(snapshot, "state")
    role = top_item(snapshot, "role")
    university = top_item(snapshot, "university")
    findings: list[str] = []
    for label, item in (
        ("Top industry", industry),
        ("Top state", state),
        ("Top target role", role),
        ("Top institution", university),
    ):
        if item:
            findings.append(
                f"{label}: {item['label']} — {item['count']} {'client' if item['count'] == 1 else 'clients'} ({item['percentage']}%)."
            )
    if snapshot.get("cross_tabs"):
        cross = snapshot["cross_tabs"][0]
        if cross.get("values"):
            item = cross["values"][0]
            findings.insert(
                0,
                f"Largest {cross['first_label']} × {cross['second_label']} segment: "
                f"{item['first']} × {item['second']} — {item['count']} {'client' if item['count'] == 1 else 'clients'} "
                f"({item['percentage']}%).",
            )

    deck_parts = [f"DreamShift's current dataset includes {total} client profiles"]
    if metrics.get("industries_represented"):
        deck_parts.append(f"across {metrics['industries_represented']} primary industries")
    if metrics.get("target_roles_represented"):
        deck_parts.append(f"and {metrics['target_roles_represented']} target roles")
    pitch_line = " ".join(deck_parts) + "."

    answer = (
        "The dashboard has generated an exact data summary from the currently filtered client records. "
        + (" ".join(findings[:3]) if findings else "There is not enough populated data for a ranked insight yet.")
    )
    return {
        "mode": "data-only",
        "answer": answer,
        "key_findings": findings[:5],
        "pitch_deck_line": pitch_line,
        "marketing_opportunity": (
            f"Prioritise proof-led campaigns around {industry['label']} and {role['label']}."
            if industry and role
            else "Build campaigns around the strongest populated client segments."
        ),
        "data_note": "Generated deterministically from Airtable aggregates; no LLM was required.",
        "model": None,
    }


def discover_dashboard_keys() -> list[tuple[str, str]]:
    env = _env_data()
    pairs: list[tuple[str, str]] = []
    prefixes = ("DASHBOARD_GROQ_API_KEY", "LLM_API_KEY", "GROQ_API_KEY")
    for prefix in prefixes:
        names = [prefix] + [f"{prefix}{index}" for index in range(2, 9)]
        for name in names:
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


def retry_after_seconds(response: httpx.Response) -> float | None:
    raw = response.headers.get("retry-after")
    if raw:
        try:
            return float(raw)
        except ValueError:
            pass
    match = re.search(
        r"try\s+again\s+in\s+(?:(\d+(?:\.\d+)?)m)?(?:(\d+(?:\.\d+)?)s)?",
        response.text,
        flags=re.I,
    )
    if match:
        minutes = float(match.group(1) or 0)
        seconds = float(match.group(2) or 0)
        return minutes * 60 + seconds
    return None


class DashboardGroqClient:
    """Groq formatter with up to eight authorised keys.

    Keys are used for credential/availability failover. HTTP 429 is not rotated
    across keys because Groq rate limits are organisation-level and should be
    respected rather than bypassed.
    """

    def __init__(self) -> None:
        self.keys = discover_dashboard_keys()
        self.base_url = (env_value("DASHBOARD_LLM_BASE_URL") or env_value("LLM_BASE_URL") or "https://api.groq.com/openai/v1").rstrip("/")
        self.model = env_value("DASHBOARD_CHAT_MODEL") or env_value("LLM_MODEL") or "openai/gpt-oss-20b"
        self.timeout = env_int("DASHBOARD_CHAT_TIMEOUT_SECONDS", 45, 10, 180)
        self.max_tokens = env_int("DASHBOARD_CHAT_MAX_TOKENS", 900, 250, 2000)

    async def answer(self, snapshot: dict[str, Any]) -> dict[str, Any]:
        if not self.keys:
            raise DashboardError("No Groq key is configured for dashboard chat.")

        system_prompt = (
            "You are DreamShift's client intelligence analyst. Answer only from the supplied aggregate Airtable data. "
            "These are DreamShift clients, not job candidates. Never invent values, client identities, universities, employers or trends. "
            "Use counts and percentages exactly as supplied. The denominator must always match the currently filtered client count. "
            "For certification questions, lead with professional or role-relevant certifications and place White Card, Working with Children Check, first aid, police checks and similar items under a separate general-compliance heading. "
            "Never call a general compliance card an IT certification. Normalize aliases and do not add together percentages from different denominators. "
            "Distinguish primary industries and primary target roles from multi-value fields. "
            "Return one JSON object with exactly these keys: answer, key_findings, pitch_deck_line, marketing_opportunity, data_note. "
            "key_findings must be an array of concise evidence-led strings. pitch_deck_line must be a polished one-sentence claim suitable for a business pitch deck. "
            "marketing_opportunity must recommend one practical campaign, partnership or content angle. data_note must mention any limitation relevant to the question."
        )
        user_prompt = (
            "Question:\n"
            + snapshot["question"]
            + "\n\nAggregate client intelligence JSON:\n"
            + json.dumps(snapshot, ensure_ascii=False, separators=(",", ":"))
        )
        payload = {
            "model": self.model,
            "temperature": 0.15,
            "max_completion_tokens": self.max_tokens,
            "response_format": {"type": "json_object"},
            "messages": [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt},
            ],
        }
        if self.model.startswith("openai/gpt-oss"):
            payload["reasoning_effort"] = "low"

        endpoint = f"{self.base_url}/chat/completions"
        last_error: Exception | None = None
        for label, key in self.keys:
            try:
                async with httpx.AsyncClient(timeout=httpx.Timeout(self.timeout)) as client:
                    response = await client.post(
                        endpoint,
                        headers={
                            "Authorization": f"Bearer {key}",
                            "Content-Type": "application/json",
                        },
                        json=payload,
                    )
                if response.status_code == 429:
                    wait = retry_after_seconds(response)
                    raise DashboardRateLimitError(
                        f"Groq rate limit reached using {label}.",
                        retry_after=wait,
                    )
                if response.status_code in {401, 403}:
                    last_error = DashboardError(f"{label} was rejected with HTTP {response.status_code}.")
                    continue
                if response.status_code >= 500:
                    last_error = DashboardError(f"Groq HTTP {response.status_code} using {label}.")
                    continue
                if response.status_code >= 400:
                    raise DashboardError(f"Groq HTTP {response.status_code}: {response.text[:1200]}")

                envelope = response.json()
                choices = envelope.get("choices") or []
                if not choices:
                    raise DashboardError("Groq returned no chat choice.")
                content = choices[0].get("message", {}).get("content")
                if not isinstance(content, str) or not content.strip():
                    raise DashboardError("Groq returned an empty dashboard answer.")
                parsed = json.loads(content)
                if not isinstance(parsed, dict):
                    raise DashboardError("Groq dashboard response was not a JSON object.")
                parsed["mode"] = "ai"
                parsed["model"] = envelope.get("model") or self.model
                parsed["api_key_label"] = label
                return parsed
            except DashboardRateLimitError:
                raise
            except (httpx.HTTPError, json.JSONDecodeError, DashboardError) as exc:
                last_error = exc
                continue
        raise DashboardError(f"Dashboard chat failed across configured keys: {last_error}")


@router.get("/dashboard", response_class=HTMLResponse)
async def dashboard_page() -> HTMLResponse:
    if not DASHBOARD_HTML.exists():
        raise HTTPException(500, detail="Dashboard template is missing.")
    return HTMLResponse(DASHBOARD_HTML.read_text(encoding="utf-8"))


@router.get("/api/dashboard/data")
async def dashboard_data(force: bool = Query(default=False)) -> dict[str, Any]:
    try:
        records, schema, schema_source = await get_dashboard_records(force=force)
    except DashboardError as exc:
        raise HTTPException(502, detail=str(exc)) from exc

    raw_records = list(_DATA_CACHE.get("raw_records") or [])
    return {
        "records": records,
        "record_count": len(records),
        "fetched_at": _DATA_CACHE.get("fetched_at") or utc_iso(),
        "refresh_seconds": env_int("DASHBOARD_REFRESH_SECONDS", 60, 15, 3600),
        "schema": schema_payload(raw_records, schema, schema_source),
        "privacy": {
            "browser_payload_excludes": [
                "Full Name",
                "Current Employer",
                "Previous Employers",
                "Resume Source URL",
                "CV text and contact details",
            ]
        },
    }




@router.post("/api/dashboard/query")
async def query_dashboard(request: AskDashboardRequest) -> dict[str, Any]:
    try:
        records, _schema, _schema_source = await get_dashboard_records(force=False)
        dashboard_filtered = apply_filters(records, request.filters)
        return await execute_chat_query(
            dashboard_filtered,
            request.question.strip(),
            dashboard_filters=request.filters,
            preview_only=False,
        )
    except QueryEngineError as exc:
        raise HTTPException(400, detail=str(exc)) from exc
    except Exception as exc:
        raise HTTPException(500, detail=f"Airtable query engine failed: {type(exc).__name__}: {exc}") from exc


@router.post("/api/dashboard/query/preview")
async def preview_dashboard_query(request: AskDashboardRequest) -> dict[str, Any]:
    try:
        records, _schema, _schema_source = await get_dashboard_records(force=False)
        dashboard_filtered = apply_filters(records, request.filters)
        return await execute_chat_query(
            dashboard_filtered,
            request.question.strip(),
            dashboard_filters=request.filters,
            preview_only=True,
        )
    except QueryEngineError as exc:
        raise HTTPException(400, detail=str(exc)) from exc


@router.post("/api/dashboard/ask")
async def ask_dashboard(request: AskDashboardRequest) -> dict[str, Any]:
    try:
        records, _schema, _schema_source = await get_dashboard_records(force=False)
    except DashboardError as exc:
        raise HTTPException(502, detail=str(exc)) from exc

    filtered = apply_filters(records, request.filters)
    snapshot = build_snapshot(filtered, request.question.strip(), request.filters)
    fallback = deterministic_answer(snapshot)

    enabled = str(env_value("DASHBOARD_CHAT_ENABLED", "true")).casefold() not in {"0", "false", "no", "off"}
    if not enabled:
        fallback["data_note"] += " Groq formatting is disabled by DASHBOARD_CHAT_ENABLED."
        return fallback

    try:
        ai_answer = await DashboardGroqClient().answer(snapshot)
        ai_answer.setdefault("answer", fallback["answer"])
        ai_answer.setdefault("key_findings", fallback["key_findings"])
        ai_answer.setdefault("pitch_deck_line", fallback["pitch_deck_line"])
        ai_answer.setdefault("marketing_opportunity", fallback["marketing_opportunity"])
        ai_answer.setdefault("data_note", "Based only on the currently filtered aggregate Airtable data.")
        ai_answer["filtered_client_count"] = len(filtered)
        return ai_answer
    except DashboardRateLimitError as exc:
        wait_text = f" Retry after approximately {round(exc.retry_after)} seconds." if exc.retry_after else ""
        fallback["notice"] = "Groq is rate limited; exact data-only insights were returned instead." + wait_text
        fallback["filtered_client_count"] = len(filtered)
        return fallback
    except DashboardError as exc:
        fallback["notice"] = f"Groq formatting was unavailable; exact data-only insights were returned instead. {exc}"
        fallback["filtered_client_count"] = len(filtered)
        return fallback
