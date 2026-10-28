"""
Service Project ROI API.

    GET /GetProjectServicePlanned?ProjectId=1415
        Current services, Future services, Cost & Schedule, Future-Current margin,
        Planned worksheet, Summary.            (calls the Planned API only)

    GET /GetProjectServiceActual?ProjectId=1415
        Current services, Future services, Cost & Schedule, Future-Current margin,
        Actual worksheet, Planned vs Actual, Summary.   (calls Planned + Actual APIs)

    GET /projects/{project_id}/debug   raw API responses + field checks (connection test)

Every calculation is the existing code in the calculator module.

Run:  uvicorn api:app --host 0.0.0.0 --port 8000
"""
import json
import os

import pandas as pd
import requests
from fastapi import FastAPI, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware

import roi_calculator as calc
from project_inputs import ProjectNotFound, diagnose, load_project_inputs

app = FastAPI(title="Service Project ROI API", version="3.0")

# CORS: "*" allows every frontend origin. To restrict later, set e.g.
#   CORS_ORIGINS=https://myapp.com,http://localhost:3000   in .env

_cors_origins = [o.strip() for o in os.getenv("CORS_ORIGINS", "*").split(",") if o.strip()]
app.add_middleware(
    CORSMiddleware,
    allow_origins=_cors_origins,,
    # allow_credentials="*" not in _cors_origins,  # browsers reject credentials with "*"
    allow_methods=["*"],
    allow_headers=["*"],
)


def _records(df):
    """DataFrame -> JSON-safe list of dicts (NaN -> null)."""
    if df is None or df.empty:
        return []
    return json.loads(df.to_json(orient="records", force_ascii=False))


def _base_tables(inputs):
    """Tables shared by both endpoints."""
    current_df, future_df, _combined, summary_df, schedule_df, margin_df = calc.process_inputs(
        inputs["premises"], inputs["current_input"],
        inputs["future_input"], inputs["schedule_inputs"],
    )
    return current_df, future_df, summary_df, schedule_df, margin_df


def _planned_df(inputs, future_df):
    if future_df.empty:
        return pd.DataFrame()
    return calc.build_planned_project_cost_worksheet(
        future_df=future_df, premises_values=inputs["premises"],
        talent_months_to_complete=inputs["planned_talent_months"],
        ai_months_to_complete=inputs["planned_ai_months"],
    )


def _actual_df(inputs, future_df):
    if future_df.empty:
        return pd.DataFrame()
    return calc.build_actual_project_cost_worksheet(
        future_df=future_df, premises_values=inputs["premises"],
        talent_hours_by_service=inputs["actual_talent_hours"],
        ai_hours_by_service=inputs["actual_ai_hours"],
    )


def calculate_planned(project_id, planned_payload=None):
    inputs, warnings = load_project_inputs(project_id, planned_payload, include_actual=False)
    current_df, future_df, summary_df, schedule_df, margin_df = _base_tables(inputs)
    return {
        "project_id": project_id,
        "warnings": warnings,
        "premises": inputs["premises"],
        "tables": {
            "current_services": _records(current_df),
            "future_services": _records(future_df),
            "cost_schedule": _records(schedule_df),
            "future_current_margin": _records(margin_df),
            "planned": _records(_planned_df(inputs, future_df)),
            "summary": _records(summary_df),
        },
    }


def calculate_actual(project_id, planned_payload=None, actual_payload=None):
    inputs, warnings = load_project_inputs(project_id, planned_payload, actual_payload, include_actual=True)
    current_df, future_df, summary_df, schedule_df, margin_df = _base_tables(inputs)
    actual_df = _actual_df(inputs, future_df)
    comparison_df = pd.DataFrame()
    if not actual_df.empty:
        # Planned figures are used only to build the comparison; the Planned table itself is not returned.
        comparison_df = calc.build_planned_vs_actual_comparison(_planned_df(inputs, future_df), actual_df)
    return {
        "project_id": project_id,
        "warnings": warnings,
        "premises": inputs["premises"],
        "tables": {
            "current_services": _records(current_df),
            "future_services": _records(future_df),
            "cost_schedule": _records(schedule_df),
            "future_current_margin": _records(margin_df),
            "actual": _records(actual_df),
            "planned_vs_actual": _records(comparison_df),
            "summary": _records(summary_df),
        },
    }


def _run(func, project_id):
    try:
        return func(project_id)
    except ProjectNotFound as exc:
        raise HTTPException(status_code=404, detail=str(exc))
    except (ConnectionError, requests.HTTPError) as exc:
        raise HTTPException(status_code=502, detail=f"Project API error: {exc}")
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc))


# =========================================================
# ENDPOINTS
# =========================================================

@app.get("/health")
def health():
    return {"status": "ok"}


@app.get("/GetProjectServicePlanned")
def get_project_service_planned(ProjectId: int = Query(..., description="Project Id")):
    """All tables except Actual and Planned vs Actual."""
    return _run(calculate_planned, ProjectId)


@app.get("/GetProjectServiceActual")
def get_project_service_actual(ProjectId: int = Query(..., description="Project Id")):
    """All tables except Planned."""
    return _run(calculate_actual, ProjectId)


@app.get("/projects/{project_id}/debug")
def project_debug(project_id: int):
    """Shows what the Planned and Actual APIs return for this project (no calculation)."""
    return diagnose(project_id)
