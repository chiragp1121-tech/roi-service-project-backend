"""
Quick check against the real APIs.

    python test_project.py            # uses ProjectId 1415
    python test_project.py 1234       # any other ProjectId

Step 1 shows each API's raw response (status + top-level keys) so a wrong URL,
header or key is easy to spot. Step 2 runs the full ROI calculation.
"""
import json
import sys

import requests

import project_inputs as pi
from api import calculate_project

project_id = int(sys.argv[1]) if len(sys.argv) > 1 else 1415

print(f"Header: {pi.API_KEY_HEADER}: {pi.PLANNED_API_KEY[:8]}…  ProjectId={project_id}\n")
for label, url, key in (("Planned", pi.PLANNED_API_URL, pi.PLANNED_API_KEY),
                        ("Actual", pi.ACTUAL_API_URL, pi.ACTUAL_API_KEY)):
    r = requests.get(url, params={"ProjectId": project_id},
                     headers={pi.API_KEY_HEADER: key, "Accept": "application/json"}, timeout=30)
    print(f"[{label}] HTTP {r.status_code}  {url}")
    try:
        body = r.json()
        print("   keys:", list(body) if isinstance(body, dict) else type(body).__name__)
        if isinstance(body, dict):
            for k in ("ProjectService_Current", "ProjectService_Future"):
                print(f"   {k}: {len(body.get(k) or [])} rows")
    except ValueError:
        print("   body:", r.text[:300])

print("\nRunning full calculation…")
result = calculate_project(project_id)
print("Warnings:", json.dumps(result["warnings"], indent=2))
for name, rows in result["tables"].items():
    print(f"  {name}: {len(rows)} rows")
print("\nPlanned vs Actual:")
print(json.dumps(result["tables"]["planned_vs_actual"], indent=2, ensure_ascii=False))