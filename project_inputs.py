"""
Fetch a project's inputs from the two Project APIs and convert them into the
structures the calculator used to read from the Excel workbook.

  Planned API -> Premises (cost/value), Current services, Future services,
                 planned Talent/AI hours per future service
  Actual API  -> actual Talent/AI hours per future service

No calculation happens here; all maths stays in
roi_excel_calculator_v2_dynamic_premises_fixed_v8_scalar.py.
"""
import os
from concurrent.futures import ThreadPoolExecutor

try:  # read settings from a .env file next to this module, if present
    from dotenv import load_dotenv
    load_dotenv(os.path.join(os.path.dirname(os.path.abspath(__file__)), ".env"))
except ImportError:
    pass

import pandas as pd
import requests

BASE_URL = "https://personal-ivsf69f0.outsystemscloud.com/Project_API/rest/ProjectServiceROI"
PLANNED_API_URL = os.getenv("PLANNED_API_URL", f"{BASE_URL}/GetProjectServicePlanned")
ACTUAL_API_URL = os.getenv("ACTUAL_API_URL", f"{BASE_URL}/GetProjectServiceActual")
# One key authenticates both APIs; set PLANNED_API_KEY / ACTUAL_API_KEY only if they ever differ.
PROJECT_API_KEY = os.getenv("PROJECT_API_KEY", "")
PLANNED_API_KEY = os.getenv("PLANNED_API_KEY", PROJECT_API_KEY)
ACTUAL_API_KEY = os.getenv("ACTUAL_API_KEY", PROJECT_API_KEY)
API_KEY_HEADER = os.getenv("API_KEY_HEADER", "API_key")
API_TIMEOUT = float(os.getenv("PROJECT_API_TIMEOUT", "30"))

HOURS_PER_MONTH = 160.0  # same constant the calculator uses for actuals

# Columns produced by calc.read_excel_tables(); find_input_columns() relies on them.
SERVICE_COLUMNS = [
    "Service Improvement", "Team Member",
    "Talent Number of same services", "Talent % FTE/Service", "Talent Tier Input",
    "AI companion",
    "AI Number of same services", "AI % FTE/Service", "AI Tier Input",
]

# DB field -> calculator column (one service row)
SERVICE_FIELD_MAP = {
    "Service_Description": "Service Improvement",
    "TeamMember": "Team Member",
    "NumberOfSameServices_Talent": "Talent Number of same services",
    "Talent_FTE": "Talent % FTE/Service",
    "TalentRequired": "Talent Tier Input",          # X / Y / Z
    "AICompanion": "AI companion",
    "NumberOfSameServices_AI": "AI Number of same services",
    "AI_FTE": "AI % FTE/Service",
    "TalentRequiredAI": "AI Tier Input",            # X / Y / Z
}

# Premises: DB prefix -> (period, side, metric). "FTE" = FTE Value, "Cost" = FTE Cost.
PREMISES_FIELD_MAP = {
    "TalentCurrFTE": ("current", "talent", "value"),
    "TalentCurrCost": ("current", "talent", "cost"),
    "TalentFutFTE": ("future", "talent", "value"),
    "TalentFutCost": ("future", "talent", "cost"),
    "AICurrFTE": ("current", "ai", "value"),
    "AICurrCost": ("current", "ai", "cost"),
    "AIFutFTE": ("future", "ai", "value"),
    "AIFutCost": ("future", "ai", "cost"),
}

TALENT_HOURS_FIELD = "Talent_Hours"
AI_HOURS_FIELD = "AIHours"

# 'Cost and Schedule to reach Future services' inputs (rows 1, 2, 4).
# Expected shape if the Planned API returns them:
#   "CostSchedule": {"Talent_FTE": [row1, row2, row4], "AI_FTE": [row1, row2, row4]}
SCHEDULE_KEY = "CostSchedule"

# Section names in the API responses (first match wins, case-insensitive).
PREMISES_KEYS = ("ProjectService_Premises", "Premises")
CURRENT_KEYS = ("ProjectService_CurrentList", "ProjectService_Current")
FUTURE_KEYS = ("ProjectService_FutureList", "ProjectService_Future")
ACTUAL_ROWS_KEYS = ("ProjectCardsHours_List", "ProjectService_FutureList", "ProjectService_Future")


class ProjectNotFound(Exception):
    pass


# =========================================================
# API CALLS
# =========================================================

def _get(url, api_key, project_id, label):
    if not api_key:
        raise ConnectionError(f"No API key set for the {label} API (set PROJECT_API_KEY in .env).")
    headers = {API_KEY_HEADER: api_key, "Accept": "application/json"}
    try:
        response = requests.get(url, params={"ProjectId": project_id},
                                headers=headers, timeout=API_TIMEOUT)
    except requests.RequestException as exc:
        raise ConnectionError(f"Could not reach the {label} API: {exc}") from exc
    if response.status_code == 404:
        raise ProjectNotFound(f"Project {project_id} was not found in the {label} API.")
    if response.status_code in (401, 403):
        raise ConnectionError(f"{label} API rejected the API key (HTTP {response.status_code}).")
    response.raise_for_status()
    try:
        return response.json()
    except ValueError:
        raise ConnectionError(
            f"{label} API returned non-JSON (HTTP {response.status_code}): {response.text[:200]}"
        )


def fetch_project(project_id):
    """Call the Planned and Actual APIs in parallel; return (planned, actual)."""
    with ThreadPoolExecutor(max_workers=2) as pool:
        planned = pool.submit(_get, PLANNED_API_URL, PLANNED_API_KEY, project_id, "Planned")
        actual = pool.submit(_get, ACTUAL_API_URL, ACTUAL_API_KEY, project_id, "Actual")
        return planned.result(), actual.result()


# =========================================================
# MAPPING
# =========================================================

def _number(value, default=0.0):
    if value is None or (isinstance(value, str) and value.strip() == ""):
        return default
    try:
        return float(str(value).replace(",", ""))
    except ValueError:
        return default


def _name(row):
    name = str(_field(row, "Service_Description") or "").strip()
    return "" if name.casefold() == "total" else name


def _ci(d):
    """Case-insensitive view of a dict's keys."""
    return {str(k).casefold(): v for k, v in d.items()} if isinstance(d, dict) else {}


def section(payload, name):
    """
    Find a top-level section (e.g. 'Premises') case-insensitively. Also looks one
    level down, for responses wrapped like {"Data": {...}} or {"Response": {...}}.
    """
    names = (name,) if isinstance(name, str) else tuple(name)
    if isinstance(payload, list) and len(payload) == 1:
        payload = payload[0]
    top = _ci(payload)
    for n in names:
        if n.casefold() in top:
            return top[n.casefold()]
    for value in top.values():
        inner = _ci(value)
        for n in names:
            if n.casefold() in inner:
                return inner[n.casefold()]
    return None


def top_level_keys(payload):
    if isinstance(payload, dict):
        return list(payload.keys())
    return f"<{type(payload).__name__}, length {len(payload) if hasattr(payload, '__len__') else '?'}>"


def _field(row, name):
    return _ci(row).get(name.casefold())


def build_premises(payload, label="Planned"):
    """Premises dict in the same shape as calc.read_premises_values()."""
    db = section(payload, PREMISES_KEYS)
    if isinstance(db, list):
        db = db[0] if db else None
    if not isinstance(db, dict):
        raise ValueError(
            f"The {label} API response has no Premises object (looked for {PREMISES_KEYS}). "
            f"Top-level keys returned: {top_level_keys(payload)}. "
            "Check the API URL and that project data exists (try /projects/{id}/debug)."
        )
    premises = {
        period: {side: {m: {} for m in ("cost", "value")} for side in ("talent", "ai")}
        for period in ("current", "future")
    }
    missing = []
    for prefix, (period, side, metric) in PREMISES_FIELD_MAP.items():
        for tier in ("X", "Y", "Z"):
            field = f"{prefix}_{tier}"
            value = _field(db, field)
            if value in (None, ""):
                missing.append(field)
            premises[period][side][metric][tier] = _number(value)
    if missing:
        raise ValueError(
            f"{label} API 'Premises' is missing these fields: " + ", ".join(missing)
            + f". Fields it does contain: {list(db.keys())}"
        )
    return premises


def _tier_letter(value):
    """'Z (Top)' -> 'Z', 'y (key)' -> 'Y'. Blank stays blank (calculator defaults to X)."""
    text = str(value or "").strip().upper()
    return text[0] if text[:1] in ("X", "Y", "Z") else text


def build_service_table(rows):
    """Service DataFrame in the same shape as calc.read_excel_tables()."""
    records = []
    for row in rows or []:
        name = _name(row)
        if not name:                       # same skip rule as the Excel reader
            continue
        record = {col: _field(row, field) for field, col in SERVICE_FIELD_MAP.items()}
        record["Service Improvement"] = name
        record["Talent Tier Input"] = _tier_letter(record["Talent Tier Input"])
        record["AI Tier Input"] = _tier_letter(record["AI Tier Input"])
        records.append(record)
    return pd.DataFrame(records, columns=SERVICE_COLUMNS)


def hours_by_service(future_rows, label, warnings):
    """{service name: (talent hours, ai hours)} from Future service rows."""
    talent, ai = {}, {}
    for row in future_rows or []:
        name = _name(row)
        if not name:
            continue
        if name in talent:
            warnings.append(f"{label}: duplicate future service '{name}'; hours were added together.")
        talent[name] = talent.get(name, 0.0) + _number(_field(row, TALENT_HOURS_FIELD))
        ai[name] = ai.get(name, 0.0) + _number(_field(row, AI_HOURS_FIELD))
    return talent, ai


def build_schedule_inputs(payload, warnings):
    schedule = section(payload, SCHEDULE_KEY)
    if isinstance(schedule, dict):
        talent = [_number(v) for v in (_field(schedule, "Talent_FTE") or [])][:3]
        ai = [_number(v) for v in (_field(schedule, "AI_FTE") or [])][:3]
        if len(talent) == 3:
            return {"talent": talent, "ai": ai if len(ai) == 3 else list(talent)}
    warnings.append(
        "Cost and Schedule % FTE inputs (rows 1, 2, 4) were not returned; 0 was used, so the "
        "Cost/Schedule table and the NRE/ROI rows of the Future-Current margin table are 0 or blank."
    )
    return {"talent": [0.0, 0.0, 0.0], "ai": [0.0, 0.0, 0.0]}


def load_project_inputs(project_id, planned_payload=None, actual_payload=None, include_actual=True):
    """
    Build all calculator inputs.

    include_actual=False -> only the Planned API is called (no actual hours).
    include_actual=True  -> Planned and Actual APIs are called in parallel.
    Payloads passed in are used instead of calling the APIs.
    """
    if include_actual:
        if planned_payload is None or actual_payload is None:
            planned_payload, actual_payload = fetch_project(project_id)
    else:
        if planned_payload is None:
            planned_payload = _get(PLANNED_API_URL, PLANNED_API_KEY, project_id, "Planned")
        actual_payload = {}
    warnings = []

    # Base data (premises, current, future services) comes from the Planned API.
    future_rows = section(planned_payload, FUTURE_KEYS) or []
    future_input = build_service_table(future_rows)

    planned_talent_h, planned_ai_h = hours_by_service(future_rows, "Planned", warnings)
    actual_talent_h, actual_ai_h = {}, {}
    if include_actual:
        actual_talent_h, actual_ai_h = hours_by_service(
            section(actual_payload, ACTUAL_ROWS_KEYS), "Actual", warnings
        )

    has_planned_hours = any(
        _field(r, TALENT_HOURS_FIELD) is not None or _field(r, AI_HOURS_FIELD) is not None
        for r in future_rows
    )
    if future_rows and not has_planned_hours:
        warnings.append(
            "Planned API returned no Talent_Hours/AIHours on future services; planned hours = 0, "
            "so planned non-recurring cost is 0."
        )

    missing_actual = sorted(set(planned_talent_h) - set(actual_talent_h)) if include_actual else []
    if missing_actual:
        warnings.append("No actual hours returned for: " + ", ".join(missing_actual) + " (0 used).")

    # Premises from the Planned API; fall back to the Actual API if Planned has none.
    if section(planned_payload, PREMISES_KEYS) is None and section(actual_payload, PREMISES_KEYS) is not None:
        warnings.append("Planned API returned no Premises; Premises taken from the Actual API.")
        premises = build_premises(actual_payload, "Actual")
    else:
        premises = build_premises(planned_payload, "Planned")
    if all(v == 0 for p in premises.values() for sd in p.values() for m in sd.values() for v in m.values()):
        warnings.append("All Premises values are 0; the project may have no Premises record in the database.")

    inputs = {
        "premises": premises,
        "current_input": build_service_table(section(planned_payload, CURRENT_KEYS)),
        "future_input": future_input,
        "schedule_inputs": build_schedule_inputs(planned_payload, warnings),
        # Planned table works in months: planned hours ÷ 160.
        "planned_talent_months": {k: v / HOURS_PER_MONTH for k, v in planned_talent_h.items()},
        "planned_ai_months": {k: v / HOURS_PER_MONTH for k, v in planned_ai_h.items()},
        # Actual table takes hours and divides by 160 itself.
        "actual_talent_hours": actual_talent_h,
        "actual_ai_hours": actual_ai_h,
    }
    if future_input.empty:
        warnings.append("No Future services with a Service_Description were returned.")
    if inputs["current_input"].empty:
        warnings.append("No Current services with a Service_Description were returned.")
    return inputs, warnings


# =========================================================
# CONNECTION / DATA CHECK
# =========================================================

def _premises_check(payload):
    db = section(payload, PREMISES_KEYS)
    if isinstance(db, list):
        db = db[0] if db else None
    if not isinstance(db, dict):
        return {"found": False}
    expected = [f"{p}_{t}" for p in PREMISES_FIELD_MAP for t in ("X", "Y", "Z")]
    present = {f: _field(db, f) for f in expected if _field(db, f) not in (None, "")}
    return {
        "found": True,
        "project_id_in_record": _field(db, "ProjectId"),
        "fields_present": len(present),
        "fields_expected": len(expected),
        "missing_fields": [f for f in expected if f not in present],
        "all_values_zero": bool(present) and all(_number(v) == 0 for v in present.values()),
        "values": present,
    }


def _rows_check(rows):
    rows = rows if isinstance(rows, list) else []
    named = [r for r in rows if _name(r)]
    expected = list(SERVICE_FIELD_MAP) + [TALENT_HOURS_FIELD, AI_HOURS_FIELD]
    first = rows[0] if rows else {}
    return {
        "rows_returned": len(rows),
        "rows_with_service_description": len(named),
        "service_names": [_name(r) for r in named],
        "missing_fields_in_first_row": [f for f in expected if _field(first, f) is None] if rows else [],
    }


def diagnose(project_id):
    """Call both APIs and report what came back, without calculating anything."""
    report = {"project_id": project_id, "header_name": API_KEY_HEADER}
    for label, url, key in (("planned", PLANNED_API_URL, PLANNED_API_KEY),
                            ("actual", ACTUAL_API_URL, ACTUAL_API_KEY)):
        entry = {"url": url, "api_key_set": bool(key)}
        try:
            r = requests.get(url, params={"ProjectId": project_id},
                             headers={API_KEY_HEADER: key, "Accept": "application/json"},
                             timeout=API_TIMEOUT)
            entry["http_status"] = r.status_code
            try:
                body = r.json()
            except ValueError:
                entry["error"] = "Response is not JSON"
                entry["raw_body"] = r.text[:1000]
                report[label] = entry
                continue
            entry["top_level_keys"] = top_level_keys(body)
            entry["premises"] = _premises_check(body)
            entry["current_services"] = _rows_check(section(body, CURRENT_KEYS))
            entry["future_services"] = _rows_check(section(body, ACTUAL_ROWS_KEYS if label == "actual" else FUTURE_KEYS))
            entry["cost_schedule_found"] = section(body, SCHEDULE_KEY) is not None
            entry["raw_body"] = body
        except requests.RequestException as exc:
            entry["error"] = f"Connection failed: {exc}"
        report[label] = entry
"""
Fetch a project's inputs from the two Project APIs and convert them into the
structures the calculator used to read from the Excel workbook.

  Planned API -> Premises (cost/value), Current services, Future services,
                 planned Talent/AI hours per future service
  Actual API  -> actual Talent/AI hours per future service

No calculation happens here; all maths stays in
roi_excel_calculator_v2_dynamic_premises_fixed_v8_scalar.py.
"""
import os
from concurrent.futures import ThreadPoolExecutor

try:  # read settings from a .env file next to this module, if present
    from dotenv import load_dotenv
    load_dotenv(os.path.join(os.path.dirname(os.path.abspath(__file__)), ".env"))
except ImportError:
    pass

import pandas as pd
import requests

BASE_URL = "https://personal-ivsf69f0.outsystemscloud.com/Project_API/rest/ProjectServiceROI"
PLANNED_API_URL = os.getenv("PLANNED_API_URL", f"{BASE_URL}/GetProjectServicePlanned")
ACTUAL_API_URL = os.getenv("ACTUAL_API_URL", f"{BASE_URL}/GetProjectServiceActual")
# One key authenticates both APIs; set PLANNED_API_KEY / ACTUAL_API_KEY only if they ever differ.
PROJECT_API_KEY = os.getenv("PROJECT_API_KEY", "")
PLANNED_API_KEY = os.getenv("PLANNED_API_KEY", PROJECT_API_KEY)
ACTUAL_API_KEY = os.getenv("ACTUAL_API_KEY", PROJECT_API_KEY)
API_KEY_HEADER = os.getenv("API_KEY_HEADER", "API_key")
API_TIMEOUT = float(os.getenv("PROJECT_API_TIMEOUT", "30"))

HOURS_PER_MONTH = 160.0  # same constant the calculator uses for actuals

# Columns produced by calc.read_excel_tables(); find_input_columns() relies on them.
SERVICE_COLUMNS = [
    "Service Improvement", "Team Member",
    "Talent Number of same services", "Talent % FTE/Service", "Talent Tier Input",
    "AI companion",
    "AI Number of same services", "AI % FTE/Service", "AI Tier Input",
]

# DB field -> calculator column (one service row)
SERVICE_FIELD_MAP = {
    "Service_Description": "Service Improvement",
    "TeamMember": "Team Member",
    "NumberOfSameServices_Talent": "Talent Number of same services",
    "Talent_FTE": "Talent % FTE/Service",
    "TalentRequired": "Talent Tier Input",          # X / Y / Z
    "AICompanion": "AI companion",
    "NumberOfSameServices_AI": "AI Number of same services",
    "AI_FTE": "AI % FTE/Service",
    "TalentRequiredAI": "AI Tier Input",            # X / Y / Z
}

# Premises: DB prefix -> (period, side, metric). "FTE" = FTE Value, "Cost" = FTE Cost.
PREMISES_FIELD_MAP = {
    "TalentCurrFTE": ("current", "talent", "value"),
    "TalentCurrCost": ("current", "talent", "cost"),
    "TalentFutFTE": ("future", "talent", "value"),
    "TalentFutCost": ("future", "talent", "cost"),
    "AICurrFTE": ("current", "ai", "value"),
    "AICurrCost": ("current", "ai", "cost"),
    "AIFutFTE": ("future", "ai", "value"),
    "AIFutCost": ("future", "ai", "cost"),
}

TALENT_HOURS_FIELD = "Talent_Hours"
AI_HOURS_FIELD = "AIHours"

# 'Cost and Schedule to reach Future services' inputs (rows 1, 2, 4).
# Expected shape if the Planned API returns them:
#   "CostSchedule": {"Talent_FTE": [row1, row2, row4], "AI_FTE": [row1, row2, row4]}
SCHEDULE_KEY = "CostSchedule"

# Section names in the API responses (first match wins, case-insensitive).
PREMISES_KEYS = ("ProjectService_Premises", "Premises")
CURRENT_KEYS = ("ProjectService_CurrentList", "ProjectService_Current")
FUTURE_KEYS = ("ProjectService_FutureList", "ProjectService_Future")
ACTUAL_ROWS_KEYS = ("ProjectCardsHours_List", "ProjectService_FutureList", "ProjectService_Future")


class ProjectNotFound(Exception):
    pass


# =========================================================
# API CALLS
# =========================================================

def _get(url, api_key, project_id, label):
    if not api_key:
        raise ConnectionError(f"No API key set for the {label} API (set PROJECT_API_KEY in .env).")
    headers = {API_KEY_HEADER: api_key, "Accept": "application/json"}
    try:
        response = requests.get(url, params={"ProjectId": project_id},
                                headers=headers, timeout=API_TIMEOUT)
    except requests.RequestException as exc:
        raise ConnectionError(f"Could not reach the {label} API: {exc}") from exc
    if response.status_code == 404:
        raise ProjectNotFound(f"Project {project_id} was not found in the {label} API.")
    if response.status_code in (401, 403):
        raise ConnectionError(f"{label} API rejected the API key (HTTP {response.status_code}).")
    response.raise_for_status()
    try:
        return response.json()
    except ValueError:
        raise ConnectionError(
            f"{label} API returned non-JSON (HTTP {response.status_code}): {response.text[:200]}"
        )


def fetch_project(project_id):
    """Call the Planned and Actual APIs in parallel; return (planned, actual)."""
    with ThreadPoolExecutor(max_workers=2) as pool:
        planned = pool.submit(_get, PLANNED_API_URL, PLANNED_API_KEY, project_id, "Planned")
        actual = pool.submit(_get, ACTUAL_API_URL, ACTUAL_API_KEY, project_id, "Actual")
        return planned.result(), actual.result()


# =========================================================
# MAPPING
# =========================================================

def _number(value, default=0.0):
    if value is None or (isinstance(value, str) and value.strip() == ""):
        return default
    try:
        return float(str(value).replace(",", ""))
    except ValueError:
        return default


def _name(row):
    name = str(_field(row, "Service_Description") or "").strip()
    return "" if name.casefold() == "total" else name


def _ci(d):
    """Case-insensitive view of a dict's keys."""
    return {str(k).casefold(): v for k, v in d.items()} if isinstance(d, dict) else {}


def section(payload, name):
    """
    Find a top-level section (e.g. 'Premises') case-insensitively. Also looks one
    level down, for responses wrapped like {"Data": {...}} or {"Response": {...}}.
    """
    names = (name,) if isinstance(name, str) else tuple(name)
    if isinstance(payload, list) and len(payload) == 1:
        payload = payload[0]
    top = _ci(payload)
    for n in names:
        if n.casefold() in top:
            return top[n.casefold()]
    for value in top.values():
        inner = _ci(value)
        for n in names:
            if n.casefold() in inner:
                return inner[n.casefold()]
    return None


def top_level_keys(payload):
    if isinstance(payload, dict):
        return list(payload.keys())
    return f"<{type(payload).__name__}, length {len(payload) if hasattr(payload, '__len__') else '?'}>"


def _field(row, name):
    return _ci(row).get(name.casefold())


def build_premises(payload, label="Planned"):
    """Premises dict in the same shape as calc.read_premises_values()."""
    db = section(payload, PREMISES_KEYS)
    if isinstance(db, list):
        db = db[0] if db else None
    if not isinstance(db, dict):
        raise ValueError(
            f"The {label} API response has no Premises object (looked for {PREMISES_KEYS}). "
            f"Top-level keys returned: {top_level_keys(payload)}. "
            "Check the API URL and that project data exists (try /projects/{id}/debug)."
        )
    premises = {
        period: {side: {m: {} for m in ("cost", "value")} for side in ("talent", "ai")}
        for period in ("current", "future")
    }
    missing = []
    for prefix, (period, side, metric) in PREMISES_FIELD_MAP.items():
        for tier in ("X", "Y", "Z"):
            field = f"{prefix}_{tier}"
            value = _field(db, field)
            if value in (None, ""):
                missing.append(field)
            premises[period][side][metric][tier] = _number(value)
    if missing:
        raise ValueError(
            f"{label} API 'Premises' is missing these fields: " + ", ".join(missing)
            + f". Fields it does contain: {list(db.keys())}"
        )
    return premises


def _tier_letter(value):
    """'Z (Top)' -> 'Z', 'y (key)' -> 'Y'. Blank stays blank (calculator defaults to X)."""
    text = str(value or "").strip().upper()
    return text[0] if text[:1] in ("X", "Y", "Z") else text


def build_service_table(rows):
    """Service DataFrame in the same shape as calc.read_excel_tables()."""
    records = []
    for row in rows or []:
        name = _name(row)
        if not name:                       # same skip rule as the Excel reader
            continue
        record = {col: _field(row, field) for field, col in SERVICE_FIELD_MAP.items()}
        record["Service Improvement"] = name
        record["Talent Tier Input"] = _tier_letter(record["Talent Tier Input"])
        record["AI Tier Input"] = _tier_letter(record["AI Tier Input"])
        records.append(record)
    return pd.DataFrame(records, columns=SERVICE_COLUMNS)


def hours_by_service(future_rows, label, warnings):
    """{service name: (talent hours, ai hours)} from Future service rows."""
    talent, ai = {}, {}
    for row in future_rows or []:
        name = _name(row)
        if not name:
            continue
        if name in talent:
            warnings.append(f"{label}: duplicate future service '{name}'; hours were added together.")
        talent[name] = talent.get(name, 0.0) + _number(_field(row, TALENT_HOURS_FIELD))
        ai[name] = ai.get(name, 0.0) + _number(_field(row, AI_HOURS_FIELD))
    return talent, ai


def build_schedule_inputs(payload, warnings):
    schedule = section(payload, SCHEDULE_KEY)
    if isinstance(schedule, dict):
        talent = [_number(v) for v in (_field(schedule, "Talent_FTE") or [])][:3]
        ai = [_number(v) for v in (_field(schedule, "AI_FTE") or [])][:3]
        if len(talent) == 3:
            return {"talent": talent, "ai": ai if len(ai) == 3 else list(talent)}
    warnings.append(
        "Cost and Schedule % FTE inputs (rows 1, 2, 4) were not returned; 0 was used, so the "
        "Cost/Schedule table and the NRE/ROI rows of the Future-Current margin table are 0 or blank."
    )
    return {"talent": [0.0, 0.0, 0.0], "ai": [0.0, 0.0, 0.0]}


def load_project_inputs(project_id, planned_payload=None, actual_payload=None, include_actual=True):
    """
    Build all calculator inputs.

    include_actual=False -> only the Planned API is called (no actual hours).
    include_actual=True  -> Planned and Actual APIs are called in parallel.
    Payloads passed in are used instead of calling the APIs.
    """
    if include_actual:
        if planned_payload is None or actual_payload is None:
            planned_payload, actual_payload = fetch_project(project_id)
    else:
        if planned_payload is None:
            planned_payload = _get(PLANNED_API_URL, PLANNED_API_KEY, project_id, "Planned")
        actual_payload = {}
    warnings = []

    # Base data (premises, current, future services) comes from the Planned API.
    future_rows = section(planned_payload, FUTURE_KEYS) or []
    future_input = build_service_table(future_rows)

    planned_talent_h, planned_ai_h = hours_by_service(future_rows, "Planned", warnings)
    actual_talent_h, actual_ai_h = {}, {}
    if include_actual:
        actual_talent_h, actual_ai_h = hours_by_service(
            section(actual_payload, ACTUAL_ROWS_KEYS), "Actual", warnings
        )

    has_planned_hours = any(
        _field(r, TALENT_HOURS_FIELD) is not None or _field(r, AI_HOURS_FIELD) is not None
        for r in future_rows
    )
    if future_rows and not has_planned_hours:
        warnings.append(
            "Planned API returned no Talent_Hours/AIHours on future services; planned hours = 0, "
            "so planned non-recurring cost is 0."
        )

    missing_actual = sorted(set(planned_talent_h) - set(actual_talent_h)) if include_actual else []
    if missing_actual:
        warnings.append("No actual hours returned for: " + ", ".join(missing_actual) + " (0 used).")

    # Premises from the Planned API; fall back to the Actual API if Planned has none.
    if section(planned_payload, PREMISES_KEYS) is None and section(actual_payload, PREMISES_KEYS) is not None:
        warnings.append("Planned API returned no Premises; Premises taken from the Actual API.")
        premises = build_premises(actual_payload, "Actual")
    else:
        premises = build_premises(planned_payload, "Planned")
    if all(v == 0 for p in premises.values() for sd in p.values() for m in sd.values() for v in m.values()):
        warnings.append("All Premises values are 0; the project may have no Premises record in the database.")

    inputs = {
        "premises": premises,
        "current_input": build_service_table(section(planned_payload, CURRENT_KEYS)),
        "future_input": future_input,
        "schedule_inputs": build_schedule_inputs(planned_payload, warnings),
        # Planned table works in months: planned hours ÷ 160.
        "planned_talent_months": {k: v / HOURS_PER_MONTH for k, v in planned_talent_h.items()},
        "planned_ai_months": {k: v / HOURS_PER_MONTH for k, v in planned_ai_h.items()},
        # Actual table takes hours and divides by 160 itself.
        "actual_talent_hours": actual_talent_h,
        "actual_ai_hours": actual_ai_h,
    }
    if future_input.empty:
        warnings.append("No Future services with a Service_Description were returned.")
    if inputs["current_input"].empty:
        warnings.append("No Current services with a Service_Description were returned.")
    return inputs, warnings


# =========================================================
# CONNECTION / DATA CHECK
# =========================================================

def _premises_check(payload):
    db = section(payload, PREMISES_KEYS)
    if isinstance(db, list):
        db = db[0] if db else None
    if not isinstance(db, dict):
        return {"found": False}
    expected = [f"{p}_{t}" for p in PREMISES_FIELD_MAP for t in ("X", "Y", "Z")]
    present = {f: _field(db, f) for f in expected if _field(db, f) not in (None, "")}
    return {
        "found": True,
        "project_id_in_record": _field(db, "ProjectId"),
        "fields_present": len(present),
        "fields_expected": len(expected),
        "missing_fields": [f for f in expected if f not in present],
        "all_values_zero": bool(present) and all(_number(v) == 0 for v in present.values()),
        "values": present,
    }


def _rows_check(rows):
    rows = rows if isinstance(rows, list) else []
    named = [r for r in rows if _name(r)]
    expected = list(SERVICE_FIELD_MAP) + [TALENT_HOURS_FIELD, AI_HOURS_FIELD]
    first = rows[0] if rows else {}
    return {
        "rows_returned": len(rows),
        "rows_with_service_description": len(named),
        "service_names": [_name(r) for r in named],
        "missing_fields_in_first_row": [f for f in expected if _field(first, f) is None] if rows else [],
    }


def diagnose(project_id):
    """Call both APIs and report what came back, without calculating anything."""
    report = {"project_id": project_id, "header_name": API_KEY_HEADER}
    for label, url, key in (("planned", PLANNED_API_URL, PLANNED_API_KEY),
                            ("actual", ACTUAL_API_URL, ACTUAL_API_KEY)):
        entry = {"url": url, "api_key_set": bool(key)}
        try:
            r = requests.get(url, params={"ProjectId": project_id},
                             headers={API_KEY_HEADER: key, "Accept": "application/json"},
                             timeout=API_TIMEOUT)
            entry["http_status"] = r.status_code
            try:
                body = r.json()
            except ValueError:
                entry["error"] = "Response is not JSON"
                entry["raw_body"] = r.text[:1000]
                report[label] = entry
                continue
            entry["top_level_keys"] = top_level_keys(body)
            entry["premises"] = _premises_check(body)
            entry["current_services"] = _rows_check(section(body, CURRENT_KEYS))
            entry["future_services"] = _rows_check(section(body, ACTUAL_ROWS_KEYS if label == "actual" else FUTURE_KEYS))
            entry["cost_schedule_found"] = section(body, SCHEDULE_KEY) is not None
            entry["raw_body"] = body
        except requests.RequestException as exc:
            entry["error"] = f"Connection failed: {exc}"
        report[label] = entry
    return report