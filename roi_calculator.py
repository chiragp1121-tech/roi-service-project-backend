import os
import re
from io import BytesIO

import pandas as pd


# =========================================================
# PREMISES: ONE VALUE PER CURRENT/FUTURE TALENT/AI METRIC
# =========================================================

def _premises_metric_from_heading(value):
    """Map a Premises heading to (period, category, metric)."""
    if pd.isna(value):
        return None
    text = normalize_column_name(value)
    if "premises" in text:
        return None
    period = "current" if "current" in text else "future" if "future" in text else None
    category = "talent" if "talent" in text else "ai" if re.search(r"\bai\b", text) else None
    metric = "cost" if "cost" in text else "value" if "value" in text else None
    return (period, category, metric) if period and category and metric else None


def read_premises_values(input_file):
    """Read Current/Future × Talent/AI × Cost/Value assumptions for tiers X/Y/Z."""
    with pd.ExcelFile(input_file) as xls:
        sheet = next((name for name in xls.sheet_names if normalize_column_name(name).startswith("premises")), None)
        if sheet is None:
            raise ValueError("Could not find the 'Premises' sheet in the uploaded Excel file.")
        raw = pd.read_excel(xls, sheet_name=sheet, header=None)

    premises = {
        period: {
            side: {metric: {tier: None for tier in ("X", "Y", "Z")} for metric in ("cost", "value")}
            for side in ("talent", "ai")
        }
        for period in ("current", "future")
    }

    # The workbook places Current assumptions in one column group and Future
    # assumptions in another, with X/Y/Z labels immediately left of values.
    # Read each heading's own group independently so side-by-side headings
    # cannot interfere with one another.
    headings = []
    for r in range(len(raw)):
        for c in range(raw.shape[1]):
            parsed = _premises_metric_from_heading(raw.iat[r, c])
            if parsed:
                headings.append((r, c, parsed))

    for r, heading_col, (period, side, metric) in headings:
        # Tier values are directly beneath each heading. In this workbook the
        # tier label is in the heading column and its numeric value to the right.
        for rr in range(r + 1, min(r + 5, len(raw))):
            for label_col in range(heading_col, min(heading_col + 3, raw.shape[1] - 1)):
                label_value = raw.iat[rr, label_col]
                label = "" if pd.isna(label_value) else str(label_value).strip().upper()
                if label not in ("X", "Y", "Z"):
                    continue
                numeric_value = pd.to_numeric(raw.iat[rr, label_col + 1], errors="coerce")
                if not pd.isna(numeric_value):
                    premises[period][side][metric][label] = float(numeric_value)

    missing = [
        f"{p.title()} {side.title()} FTE {metric.title()} ({tier})"
        for p in ("current", "future")
        for side in ("talent", "ai")
        for metric in ("cost", "value")
        for tier in ("X", "Y", "Z")
        if premises[p][side][metric][tier] is None
    ]
    if missing:
        raise ValueError(
            "Could not read these X/Y/Z assumptions from the Premises tab: "
            + "; ".join(missing)
        )
    return premises


# =========================================================
# COLUMN HELPERS
# =========================================================

def normalize_column_name(value):
    value = str(value)
    value = value.replace("\n", " ").replace("\r", " ")
    value = re.sub(r"\s+", " ", value)
    return value.strip().lower()


def _find_column(columns, contains_all, exclude=None):
    exclude = exclude or []
    for column in columns:
        normalized = normalize_column_name(column)
        if all(part in normalized for part in contains_all):
            if not any(part in normalized for part in exclude):
                return column
    return None


def find_input_columns(df):
    """Locate service inputs. Unused input columns are ignored."""
    columns = list(df.columns)
    service_improvement = _find_column(columns, ["service", "improvement"]) or columns[0]
    team_matches = [c for c in columns if "team" in normalize_column_name(c) and "member" in normalize_column_name(c)]
    ai_matches = [c for c in columns if "ai" in normalize_column_name(c) and "companion" in normalize_column_name(c)]
    service_count_columns = [c for c in columns if "number" in normalize_column_name(c) and "service" in normalize_column_name(c)]
    fte_columns = [c for c in columns if "fte" in normalize_column_name(c) and "service" in normalize_column_name(c)]
    tier_columns = [c for c in columns if "tier input" in normalize_column_name(c)]
    if len(service_count_columns) < 2:
        raise ValueError("The service table must contain two 'Number of same services' columns.")
    if len(fte_columns) < 2:
        raise ValueError("The service table must contain two '% FTE/Service' columns.")
    return {
        "service_improvement": service_improvement,
        "team_member": team_matches[0] if team_matches else None,
        "talent_services": service_count_columns[0],
        "talent_fte": fte_columns[0],
        "ai_companion": ai_matches[0] if ai_matches else None,
        "ai_services": service_count_columns[1],
        "ai_fte": fte_columns[1],
        "talent_tier": tier_columns[0] if tier_columns else None,
        "ai_tier": tier_columns[1] if len(tier_columns) > 1 else (tier_columns[0] if tier_columns else None),
    }


# =========================================================
# NUMBER / VALUE HELPERS
# =========================================================

def numeric(value, default=0.0):
    if pd.isna(value):
        return default

    if isinstance(value, str):
        value = value.strip().replace(",", "")
        if value == "":
            return default

    result = pd.to_numeric(value, errors="coerce")
    return default if pd.isna(result) else float(result)


# =========================================================
# CALCULATION ENGINE
# =========================================================

def calculate_side(number_of_services, fte_per_service, fte_cost, fte_value, service_value_base="fte"):
    """Calculate one Talent or AI side using scalar Premises rates."""
    number_of_services = numeric(number_of_services)
    fte_per_service = numeric(fte_per_service)
    fte_cost = numeric(fte_cost)
    fte_value = numeric(fte_value)
    total_fte = number_of_services * fte_per_service
    total_service_cost = (total_fte * fte_cost) / 100
    if service_value_base == "cost":
        total_service_value = (total_service_cost * fte_value) / 100
    elif service_value_base == "fte":
        total_service_value = (total_fte * fte_value) / 100
    else:
        raise ValueError("Invalid service_value_base. Expected 'cost' or 'fte'.")
    yearly_margin = total_service_value - total_service_cost
    return {
        "fte_rate_cost": fte_cost, "fte_rate_value": fte_value,
        "total_fte": total_fte, "service_cost": total_service_cost,
        "service_value": total_service_value, "yearly_margin": yearly_margin,
        "monthly_margin": yearly_margin / 12,
    }


def _tier(value):
    text = "" if value is None or pd.isna(value) else str(value).strip().upper()
    return text if text in ("X", "Y", "Z") else "X"


def _rate(premises_side, metric, tier):
    rates = premises_side[metric]
    if isinstance(rates, dict):
        return numeric(rates.get(_tier(tier), rates.get("X", 0)))
    return numeric(rates)


def calculate_row(row, columns, service_type, premises_values):
    period = service_type.lower()
    premises = premises_values[period]
    talent_tier = row[columns["talent_tier"]] if columns.get("talent_tier") else "X"
    ai_tier = row[columns["ai_tier"]] if columns.get("ai_tier") else "X"
    talent_tier, ai_tier = _tier(talent_tier), _tier(ai_tier)
    talent = calculate_side(
        row[columns["talent_services"]], row[columns["talent_fte"]],
        _rate(premises["talent"], "cost", talent_tier),
        _rate(premises["talent"], "value", talent_tier), service_value_base="fte"
    )
    ai = calculate_side(
        row[columns["ai_services"]], row[columns["ai_fte"]],
        _rate(premises["ai"], "cost", ai_tier),
        _rate(premises["ai"], "value", ai_tier), service_value_base="fte"
    )
    return {
        "Talent Total % FTE": talent["total_fte"],
        "Talent Service Cost (K$)": talent["service_cost"],
        "Talent Service Value (K$)": talent["service_value"],
        "Talent Yearly Margin Contribution (K$)": talent["yearly_margin"],
        "Talent Monthly Margin Contribution (K$)": talent["monthly_margin"],
        "AI Total % FTE": ai["total_fte"],
        "AI Service Cost (K$)": ai["service_cost"],
        "AI Service Value (K$)": ai["service_value"],
        "AI Yearly Margin Contribution (K$)": ai["yearly_margin"],
        "AI Monthly Margin Contribution (K$)": ai["monthly_margin"],
        "Talent Tier": talent_tier,
        "AI Tier": ai_tier,
    }


# =========================================================
# EXCEL TABLE EXTRACTION
# =========================================================

def read_excel_tables(input_file):
    """
    Read the supplied workbook and extract Current and Future Services.
    Ensures the Excel workbook is properly closed after reading.
    """

    with pd.ExcelFile(input_file) as xls:

        service_sheet = next(
            (
                s for s in xls.sheet_names
                if normalize_column_name(s).startswith("services project")
            ),
            None,
        )

        if service_sheet is None:
            raise ValueError(
                "Could not find the 'Services Project' sheet "
                "in the uploaded Excel file."
            )

        raw = pd.read_excel(
            xls,
            sheet_name=service_sheet,
            header=None,
        )

    # The Excel file is now closed.

    # Find the header row containing Service Improvement.
    header_row = None

    for i in range(len(raw)):
        values = [
            normalize_column_name(v)
            for v in raw.iloc[i].tolist()
            if not pd.isna(v)
        ]

        if (
            "service improvement." in values
            or "service improvement" in values
        ):
            header_row = i
            break

    if header_row is None:
        raise ValueError(
            "Could not find the service table header row."
        )

    # The supplied workbook places the service table in columns C:K.
    # The separate Cost/Schedule heading may be outside C:K, so locate it
    # on the full worksheet and exclude everything from that row onward.
    schedule_raw_row = None
    for raw_row_idx in range(header_row + 1, len(raw)):
        row_text = " ".join(
            normalize_column_name(v)
            for v in raw.iloc[raw_row_idx].tolist()
            if not pd.isna(v)
        )
        if "cost and schedule" in row_text and "future services" in row_text:
            schedule_raw_row = raw_row_idx
            break

    if schedule_raw_row is not None:
        table = raw.iloc[header_row + 1:schedule_raw_row, 2:11].copy()
    else:
        table = raw.iloc[header_row + 1:, 2:11].copy()

    # Nine columns in the X/Y/Z workbook: selectors are part of the inputs.
    if table.shape[1] == 9:
        table.columns = [
            "Service Improvement", "Team Member",
            "Talent Number of same services", "Talent % FTE/Service",
            "Talent Tier Input", "AI companion",
            "AI Number of same services", "AI % FTE/Service",
            "AI Tier Input",
        ]
    elif table.shape[1] == 8:
        # Backward compatibility for older files without selectors.
        table.columns = [
            "Service Improvement", "Team Member",
            "Talent Number of same services", "Talent % FTE/Service",
            "AI companion", "AI Number of same services",
            "AI % FTE/Service", "Unused Input Column",
        ]
        table = table.drop(columns=["Unused Input Column"])
        table["Talent Tier Input"] = "X"
        table["AI Tier Input"] = "X"
        table = table[[
            "Service Improvement", "Team Member", "Talent Number of same services",
            "Talent % FTE/Service", "Talent Tier Input", "AI companion",
            "AI Number of same services", "AI % FTE/Service", "AI Tier Input"
        ]]
    else:
        raise ValueError(
            f"Expected 9 service input columns (C:K) for X/Y/Z selectors, found {table.shape[1]}."
        )
    table = table.reset_index(drop=True)

    # Remove completely empty rows.
    table = table.dropna(how="all").copy()

    service_col = table.columns[0]

    current_rows = []
    future_rows = []
    section = None

    for _, row in table.iterrows():

        label = (
            ""
            if pd.isna(row[service_col])
            else str(row[service_col]).strip()
        )

        lower = label.lower()

        if lower == "current services":
            section = "Current"
            continue

        if lower == "future services":
            section = "Future"
            continue

        # The Cost/Schedule table is a separate table below the service
        # sections. Do not accidentally treat its rows as Future Services
        # rows, because those rows do not contain service input columns.
        if "cost and schedule" in lower and "future services" in lower:
            section = None
            continue

        if lower == "total" or lower == "":
            continue

        if section == "Current":
            current_rows.append(row)

        elif section == "Future":
            future_rows.append(row)

    current_df = pd.DataFrame(
        current_rows,
        columns=table.columns,
    )

    future_df = pd.DataFrame(
        future_rows,
        columns=table.columns,
    )

    return (
        current_df.reset_index(drop=True),
        future_df.reset_index(drop=True),
    )


# =========================================================
# COST / SCHEDULE TO REACH FUTURE SERVICES
# =========================================================

def read_future_service_schedule(input_file):
    """
    Read the % FTE/Service inputs of the 'Cost and Schedule to reach Future
    services' table for BOTH Talent and AI.

    Returns:
        {"talent": [row1, row2, row4], "ai": [row1, row2, row4]}

    The section is searched dynamically (no fixed cells). The '% FTE/Service'
    headers can be on the same row as the section title or below it. Each
    header column with three numeric inputs beneath it is one side: the
    left-most column is Talent, the next one is AI. If only one column
    exists, it is used for both sides (backward compatible).

    Row 3 (Total Investment) is not an input; it is derived later as
    row 1 + row 2 separately for each side.
    """
    with pd.ExcelFile(input_file) as xls:
        service_sheet = next(
            (
                s for s in xls.sheet_names
                if normalize_column_name(s).startswith("services project")
            ),
            None,
        )

        if service_sheet is None:
            raise ValueError(
                "Could not find the 'Services Project' sheet "
                "in the uploaded Excel file."
            )

        raw = pd.read_excel(xls, sheet_name=service_sheet, header=None)

    section_row = None
    for row_idx in range(len(raw)):
        for col_idx in range(raw.shape[1]):
            normalized = normalize_column_name(raw.iat[row_idx, col_idx])
            if "cost and schedule" in normalized and "future services" in normalized:
                section_row = row_idx
                break
        if section_row is not None:
            break

    if section_row is None:
        raise ValueError(
            "Could not find the 'Cost and Schedule to reach Future services' "
            "section in the uploaded Excel file."
        )

    def first_three_numbers(col_idx, start_row):
        values = []
        for row_idx in range(start_row, min(start_row + 20, len(raw))):
            number = pd.to_numeric(raw.iat[row_idx, col_idx], errors="coerce")
            if not pd.isna(number):
                values.append(float(number))
                if len(values) == 3:
                    return values
        return None

    # 1) Find the header row (starting AT the section row, because the
    #    '% FTE/Service' headers usually share the title row).
    columns_found = []
    for header_row in range(section_row, min(section_row + 12, len(raw))):
        for col_idx in range(raw.shape[1]):
            normalized = normalize_column_name(raw.iat[header_row, col_idx])
            if "fte" not in normalized or "service" not in normalized:
                continue
            values = first_three_numbers(col_idx, header_row + 1)
            if values:
                columns_found.append((col_idx, values))
        if columns_found:
            break

    # 2) Fallback: merged/blank headers - any columns holding 3 numbers
    #    below the section title.
    if not columns_found:
        for col_idx in range(raw.shape[1]):
            values = first_three_numbers(col_idx, section_row + 1)
            if values:
                columns_found.append((col_idx, values))

    if not columns_found:
        raise ValueError(
            "The 'Cost and Schedule to reach Future services' table must "
            "contain three numeric % FTE/Service input values (rows 1, 2 "
            "and 4). None could be detected."
        )

    columns_found.sort(key=lambda item: item[0])
    talent_values = columns_found[0][1]
    ai_values = columns_found[1][1] if len(columns_found) > 1 else list(talent_values)

    return {"talent": talent_values, "ai": ai_values}


def calculate_future_service_schedule(input_file, premises_values, fte_inputs=None):
    """
    Build the four-row 'Cost and Schedule to reach Future services' table.

    The input workbook provides three Total % FTE per service values:
      Row 1, Row 2 and Row 4.
    Row 3 is calculated as Row 1 + Row 2.

    Talent and AI each read their own % FTE/Service input column from the
    workbook and use their own Current FTE Cost from the Premises sheet.

    Outputs:
      Talent:
        Talent Total % FTE per service
        Talent - Total Service Cost* (K$)
      AI:
        AI Total % FTE per service
        AI - Total Service Cost** (K$)
      Monthly Margin Contribution is populated only on the recurring-cost
      row (row 4), separately for Talent and AI:
        monthly = recurring Total Service Cost / 12
      Talent+AI monthly = Talent monthly + AI monthly
    """
    if fte_inputs is None:
        fte_inputs = read_future_service_schedule(input_file)
    talent_fte_inputs = fte_inputs["talent"]
    ai_fte_inputs = fte_inputs["ai"]

    current_talent_fte_cost = (
        sum(numeric(v) for v in premises_values["current"]["talent"]["cost"].values()) / 3
        if isinstance(premises_values["current"]["talent"]["cost"], dict)
        else numeric(premises_values["current"]["talent"]["cost"])
    )
    current_ai_fte_cost = (
        sum(numeric(v) for v in premises_values["current"]["ai"]["cost"].values()) / 3
        if isinstance(premises_values["current"]["ai"]["cost"], dict)
        else numeric(premises_values["current"]["ai"]["cost"])
    )

    if current_talent_fte_cost == 0:
        raise ValueError(
            "Current Talent FTE Cost could not be read from the Premises sheet."
        )
    if current_ai_fte_cost == 0:
        raise ValueError(
            "Current AI FTE Cost could not be read from the Premises sheet."
        )

    # Input rows are 1, 2 and 4. Row 3 is derived from rows 1 + 2,
    # separately for Talent and AI (each has its own input column).
    talent_total_fte = [
        talent_fte_inputs[0],
        talent_fte_inputs[1],
        talent_fte_inputs[0] + talent_fte_inputs[1],
        talent_fte_inputs[2],
    ]
    ai_total_fte = [
        ai_fte_inputs[0],
        ai_fte_inputs[1],
        ai_fte_inputs[0] + ai_fte_inputs[1],
        ai_fte_inputs[2],
    ]

    talent_costs = [
        value * current_talent_fte_cost
        for value in talent_total_fte
    ]
    ai_costs = [
        value * current_ai_fte_cost
        for value in ai_total_fte
    ]

    # Monthly margin contribution is required only for the recurring-cost row.
    talent_monthly = [None, None, None, talent_costs[3] / 12]
    ai_monthly = [None, None, None, ai_costs[3] / 12]

    labels = [
        "Team and AI services % FTE (Tasks, Upskilling)",
        "Cost of NRE Services of Project ((in cards as % FTE* Cost per FTE (K$))",
        "Total Investment (%FTE*Cost/FTE+NRE)",
        "Recurring Cost of Project at % FTE",
    ]

    talent_ai_monthly = [
        None,
        None,
        None,
        talent_monthly[3] + ai_monthly[3],
    ]

    output = pd.DataFrame(
        {
            "Service Improvement": labels,
            "Talent Total % FTE per service": talent_total_fte,
            "Talent Total Service Cost* (K$)": talent_costs,
            "AI Total % FTE per service": ai_total_fte,
            "AI Total Service Cost** (K$)": ai_costs,
            "Talent Monthly Margin Contribution (K$)": talent_monthly,
            "AI Monthly Margin Contribution (K$)": ai_monthly,
            "Talent+AI Monthly Margin Contribution (K$)": talent_ai_monthly,
        }
    )

    for column in [
        "Talent Total % FTE per service",
        "Talent Total Service Cost* (K$)",
        "AI Total % FTE per service",
        "AI Total Service Cost** (K$)",
        "Talent Monthly Margin Contribution (K$)",
        "AI Monthly Margin Contribution (K$)",
        "Talent+AI Monthly Margin Contribution (K$)",
    ]:
        output[column] = pd.to_numeric(output[column], errors="coerce").round(2)

    return output


# =========================================================
# PROCESS ONE TABLE
# =========================================================

def process_table(df, service_type, premises_values):
    if df.empty:
        return pd.DataFrame()

    columns = find_input_columns(df)

    output_rows = []

    for _, row in df.iterrows():
        calculations = calculate_row(row, columns, service_type, premises_values)

        result = {
            "Service Type": service_type,
            "Service Improvement": row[columns["service_improvement"]],
            "Team Member": row[columns["team_member"]]
            if columns["team_member"] is not None
            else "",
            "Number of Services (Talent)": numeric(
                row[columns["talent_services"]]
            ),
            "% FTE/Service (Talent)": numeric(row[columns["talent_fte"]]),
            "Talent Tier": calculations["Talent Tier"],
            "Talent Total % FTE": calculations["Talent Total % FTE"],
            "Talent Service Cost (K$)": calculations["Talent Service Cost (K$)"],
            "Talent Service Value (K$)": calculations["Talent Service Value (K$)"],
            "Talent Yearly Margin Contribution (K$)": calculations["Talent Yearly Margin Contribution (K$)"],
            "Talent Monthly Margin Contribution (K$)": calculations["Talent Monthly Margin Contribution (K$)"],
            "AI Companion": row[columns["ai_companion"]]
            if columns["ai_companion"] is not None
            else "",
            "Number of Services (AI)": numeric(
                row[columns["ai_services"]]
            ),
            "% FTE/Service (AI)": numeric(row[columns["ai_fte"]]),
            "AI Tier": calculations["AI Tier"],
            "AI Total % FTE": calculations["AI Total % FTE"],
            "AI Service Cost (K$)": calculations["AI Service Cost (K$)"],
            "AI Service Value (K$)": calculations["AI Service Value (K$)"],
            "AI Yearly Margin Contribution (K$)": calculations["AI Yearly Margin Contribution (K$)"],
            "AI Monthly Margin Contribution (K$)": calculations["AI Monthly Margin Contribution (K$)"],
            "Talent+AI Total % FTE Cost": calculations["Talent Service Cost (K$)"] + calculations["AI Service Cost (K$)"],
            "Talent+AI Service Value": calculations["Talent Service Value (K$)"] + calculations["AI Service Value (K$)"],
            "Talent+AI Yearly Margin Contribution (K$)": calculations["Talent Yearly Margin Contribution (K$)"] + calculations["AI Yearly Margin Contribution (K$)"],
            "Talent+AI Monthly Margin Contribution (K$)": calculations["Talent Monthly Margin Contribution (K$)"] + calculations["AI Monthly Margin Contribution (K$)"],
        }

        output_rows.append(result)

    output = pd.DataFrame(output_rows)

    # Numeric output formatting.
    numeric_columns = output.select_dtypes(include="number").columns
    output[numeric_columns] = output[numeric_columns].round(2)

    # Add a final totals row. Sum numeric columns individually; leave text columns blank.
    totals_row = {column: (output[column].sum() if column in numeric_columns else "")
                  for column in output.columns}

    # Label the final totals row in the Service Improvement column.
    if "Service Improvement" in totals_row:
        totals_row["Service Improvement"] = "Total"

    output = pd.concat([output, pd.DataFrame([totals_row])], ignore_index=True)
    output[numeric_columns] = output[numeric_columns].round(2)

    return output



# def calculate_future_current_service_margin(current_df, future_df, future_schedule_df):
    """
    Build the five-row 'Future-Current Service Margin Contribution' table.

    The first two rows are the existing Net Gain/Loss and NRE rows.

    Talent:
      Row 1 Yearly  = Future Talent Yearly Margin - Current Talent Yearly Margin
      Row 1 Monthly = Future Talent Monthly Margin - Current Talent Monthly Margin

      Row 2 Yearly  = Talent Total Investment Service Cost* / 100
      Row 2 Monthly = Talent Recurring Service Cost* / 100

      Row 3 Yearly  = Row 1 Yearly - Row 2 Yearly - (Row 2 Monthly / 12)

      Row 4 Yearly  = (Row 2 Yearly / Row 3 Yearly) * 100

      Row 5 Monthly = Row 2 Yearly /
                      (Row 1 Monthly - Row 2 Monthly)

    AI uses exactly the same formulas, using the AI columns and
    AI Total Service Cost** values from the Cost/Schedule table.

    Cells for which the user did not request a value are left blank.
    """

    def total(df, col):
        if df.empty or col not in df.columns:
            return 0.0

        values = pd.to_numeric(df[col], errors="coerce").fillna(0)

        # process_table() adds a final "Total" row. Exclude it here,
        # otherwise the service values would be counted twice.
        if "Service Improvement" in df.columns:
            labels = df["Service Improvement"].astype(str).str.strip().str.lower()
            values = values[labels != "total"]

        return float(values.sum())

    def safe_divide(numerator, denominator):
        if denominator == 0:
            return None
        return numerator / denominator

    # ---------------------------------------------------------
    # Row 1: Future - Current service margin
    # ---------------------------------------------------------
    talent_net_yearly = (
        total(future_df, "Talent Yearly Margin Contribution (K$)")
        - total(current_df, "Talent Yearly Margin Contribution (K$)")
    )
    talent_net_monthly = (
        total(future_df, "Talent Monthly Margin Contribution (K$)")
        - total(current_df, "Talent Monthly Margin Contribution (K$)")
    )

    ai_net_yearly = (
        total(future_df, "AI Yearly Margin Contribution (K$)")
        - total(current_df, "AI Yearly Margin Contribution (K$)")
    )
    ai_net_monthly = (
        total(future_df, "AI Monthly Margin Contribution (K$)")
        - total(current_df, "AI Monthly Margin Contribution (K$)")
    )

    # ---------------------------------------------------------
    # Row 2: NRE / investment and recurring cost
    # ---------------------------------------------------------
    talent_cost_col = "Talent Total Service Cost* (K$)"
    ai_cost_col = "AI Total Service Cost** (K$)"

    talent_costs = (
        pd.to_numeric(
            future_schedule_df[talent_cost_col],
            errors="coerce",
        ).fillna(0)
        if talent_cost_col in future_schedule_df.columns
        else pd.Series(dtype=float)
    )

    ai_costs = (
        pd.to_numeric(
            future_schedule_df[ai_cost_col],
            errors="coerce",
        ).fillna(0)
        if ai_cost_col in future_schedule_df.columns
        else pd.Series(dtype=float)
    )

    # Cost/Schedule rows:
    # index 2 = Total Investment
    # index 3 = Recurring Cost of Project
    talent_investment = float(talent_costs.iloc[2]) if len(talent_costs) > 2 else 0.0
    talent_recurring = float(talent_costs.iloc[3]) if len(talent_costs) > 3 else 0.0

    ai_investment = float(ai_costs.iloc[2]) if len(ai_costs) > 2 else 0.0
    ai_recurring = float(ai_costs.iloc[3]) if len(ai_costs) > 3 else 0.0

    talent_nre_yearly = talent_investment / 100
    talent_nre_monthly = talent_recurring / 100

    ai_nre_yearly = ai_investment / 100
    ai_nre_monthly = ai_recurring / 100

    # ---------------------------------------------------------
    # Row 3: Net Margin Contribution Year 1
    #
    # Exact requested formula:
    # Net Gain/Loss yearly
    #   - NRE yearly
    #   - NRE monthly / 12
    # ---------------------------------------------------------
    talent_net_year_1 = (
        talent_net_yearly
        - talent_nre_monthly
        - (talent_nre_yearly / 12)
    )

    ai_net_year_1 = (
        ai_net_yearly
        - ai_nre_monthly
        - (ai_nre_yearly / 12)
    )

    # ---------------------------------------------------------
    # Row 4: ROI
    # = NRE yearly / Net Margin Contribution Year 1 * 100
    # ---------------------------------------------------------
    talent_roi = safe_divide(talent_net_year_1, talent_nre_yearly)
    ai_roi = safe_divide(ai_nre_yearly, ai_net_year_1)

    if talent_roi is not None:
        talent_roi *= 100
    if ai_roi is not None:
        ai_roi *= 100

    # ---------------------------------------------------------
    # Row 5: Months to Breakeven
    # = NRE yearly /
    #   (Net Gain/Loss monthly - NRE monthly)
    # ---------------------------------------------------------
    talent_breakeven = safe_divide(
        talent_nre_yearly,
        talent_nre_monthly - talent_net_monthly
    )

    ai_breakeven = safe_divide(
        ai_nre_yearly,
        ai_nre_monthly - ai_net_monthly
    )

    return pd.DataFrame(
        {
            "Service Improvement": [
                "Net Gain or Loss service Margin Contribution",
                "Cost of NRE Services of Project ((in cards as % FTE)",
                "Net Margin Contribution Year 1",
                "ROI (Net Margin Contribution/Investment) - %",
                "Months to Breakeven (Investment/Net Gain)",
            ],
            "Talent Yearly Margin Contribution (K$)": [
                talent_net_yearly,
                talent_nre_yearly,
                talent_net_year_1,
                talent_roi,
                None,
            ],
            "Talent Monthly Margin Contribution (K$)": [
                talent_net_monthly,
                talent_nre_monthly,
                None,
                None,
                talent_breakeven,
            ],
            "AI Yearly Margin Contribution (K$)": [
                ai_net_yearly,
                ai_nre_yearly,
                ai_net_year_1,
                ai_roi,
                None,
            ],
            "AI Monthly Margin Contribution (K$)": [
                ai_net_monthly,
                ai_nre_monthly,
                None,
                None,
                ai_breakeven,
            ],
        }
    ).round(2)

def calculate_future_current_service_margin(current_df, future_df, future_schedule_df):
    """
    Build the five-row 'Future-Current Service Margin Contribution' table.

    New columns:
      - Talent+AI Yearly Margin Contribution (K$)
      - Talent+AI Monthly Margin Contribution (K$)

    Row 1:
      Talent+AI Yearly
        = Total Current Talent+AI Yearly Margin
          - Total Future Talent+AI Yearly Margin

      Talent+AI Monthly
        = Current Talent Monthly Margin
          + Current AI Monthly Margin

    Row 2:
      Talent+AI Yearly
        = Future Current Service Margin Contribution
          Talent Yearly + AI Yearly

      Talent+AI Monthly
        = Future Current Service Margin Contribution
          Talent Monthly + AI Monthly

    Row 3:
      Talent+AI Yearly
        = Future Current Service Margin Contribution
          Talent Yearly + AI Yearly

      Talent+AI Monthly
        = Future Current Service Margin Contribution
          Talent Monthly + AI Monthly

    Row 4 and Row 5:
      Talent+AI columns are left blank.
    """

    def total(df, col):
        """Sum a numeric column while excluding the Total row."""
        if df.empty or col not in df.columns:
            return 0.0

        values = pd.to_numeric(df[col], errors="coerce").fillna(0)

        # process_table() adds a final Total row.
        if "Service Improvement" in df.columns:
            labels = df["Service Improvement"].astype(str).str.strip().str.lower()
            values = values[labels != "total"]

        return float(values.sum())

    def safe_divide(numerator, denominator):
        if denominator == 0:
            return None
        return numerator / denominator

    # =========================================================
    # ROW 1: Current - Future
    # =========================================================

    # Talent
    talent_current_yearly = total(
        current_df,
        "Talent Yearly Margin Contribution (K$)"
    )

    talent_future_yearly = total(
        future_df,
        "Talent Yearly Margin Contribution (K$)"
    )

    talent_current_monthly = total(
        current_df,
        "Talent Monthly Margin Contribution (K$)"
    )

    talent_future_monthly = total(
        future_df,
        "Talent Monthly Margin Contribution (K$)"
    )

    # AI
    ai_current_yearly = total(
        current_df,
        "AI Yearly Margin Contribution (K$)"
    )

    ai_future_yearly = total(
        future_df,
        "AI Yearly Margin Contribution (K$)"
    )

    ai_current_monthly = total(
        current_df,
        "AI Monthly Margin Contribution (K$)"
    )

    ai_future_monthly = total(
        future_df,
        "AI Monthly Margin Contribution (K$)"
    )

    # Existing Talent / AI Row 1 values
    talent_net_yearly = talent_future_yearly - talent_current_yearly
    talent_net_monthly = talent_future_monthly - talent_current_monthly

    ai_net_yearly = ai_future_yearly - ai_current_yearly
    ai_net_monthly = ai_future_monthly - ai_current_monthly

    # NEW:
    # User requested Current Talent+AI Yearly - Future Talent+AI Yearly
    talent_ai_yearly_row1 = (
        (talent_future_yearly + ai_future_yearly) - (talent_current_yearly + ai_current_yearly)
    )

    # User requested:
    # Talent monthly + AI monthly
    talent_ai_monthly_row1 = (
        (talent_future_monthly + ai_future_monthly) - (talent_current_monthly + ai_current_monthly)
    )

    # =========================================================
    # ROW 2: NRE / Investment and recurring cost
    # =========================================================

    talent_cost_col = "Talent Total Service Cost* (K$)"
    ai_cost_col = "AI Total Service Cost** (K$)"

    talent_costs = (
        pd.to_numeric(
            future_schedule_df[talent_cost_col],
            errors="coerce",
        ).fillna(0)
        if talent_cost_col in future_schedule_df.columns
        else pd.Series(dtype=float)
    )

    ai_costs = (
        pd.to_numeric(
            future_schedule_df[ai_cost_col],
            errors="coerce",
        ).fillna(0)
        if ai_cost_col in future_schedule_df.columns
        else pd.Series(dtype=float)
    )

    # Cost/Schedule rows:
    # index 2 = Total Investment
    # index 3 = Recurring Cost of Project
    talent_investment = (
        float(talent_costs.iloc[2])
        if len(talent_costs) > 2
        else 0.0
    )

    talent_recurring = (
        float(talent_costs.iloc[3])
        if len(talent_costs) > 3
        else 0.0
    )

    ai_investment = (
        float(ai_costs.iloc[2])
        if len(ai_costs) > 2
        else 0.0
    )

    ai_recurring = (
        float(ai_costs.iloc[3])
        if len(ai_costs) > 3
        else 0.0
    )

    talent_nre_yearly = talent_investment / 100
    talent_nre_monthly = talent_recurring / 100

    ai_nre_yearly = ai_investment / 100
    ai_nre_monthly = ai_recurring / 100

    # Existing Talent + AI Row 2
    talent_ai_yearly_row2 = (
        talent_nre_yearly
        + ai_nre_yearly
    )

    talent_ai_monthly_row2 = (
        talent_nre_monthly
        + ai_nre_monthly
    )

    # =========================================================
    # ROW 3: Net Margin Contribution Year 1
    # =========================================================

    talent_net_year_1 = (
        talent_net_yearly
        - talent_nre_monthly
        - (talent_nre_yearly / 12)
    )

    ai_net_year_1 = (
        ai_net_yearly
        - ai_nre_monthly
        - (ai_nre_yearly / 12)
    )

    # NEW:
    # Row 3 = Future Current Service Margin Contribution
    # Talent Yearly + AI Yearly
    talent_ai_yearly_row3 = (
        talent_net_year_1
        + ai_net_year_1
    )

    # User did not specify a Row 3 monthly formula.
    # Leave it blank.
    talent_ai_monthly_row3 = None

    # =========================================================
    # ROW 4: ROI
    # =========================================================

    talent_roi = safe_divide(
        ai_nre_yearly,
        ai_net_year_1
    )

    # Keep the original Talent ROI behavior
    talent_roi_original = safe_divide(
        talent_net_year_1,
        talent_nre_yearly
    )

    if talent_roi_original is not None:
        talent_roi_original *= 100

    if talent_roi is not None:
        talent_roi *= 100

    # Original AI ROI
    ai_roi = safe_divide(
        ai_net_yearly,
        ai_nre_yearly
    )



    if ai_roi is not None:
        ai_roi *= 100

    talent_ai_yearly_row4 = safe_divide(
        talent_ai_yearly_row1,
        talent_ai_yearly_row2
    )

    if talent_ai_yearly_row4 is not None:
        talent_ai_yearly_row4 *= 100


    # =========================================================
    # ROW 5: Months to Breakeven
    # =========================================================

    talent_breakeven = safe_divide(
        talent_nre_yearly,
        talent_net_monthly-talent_nre_monthly 
    )

    ai_breakeven = safe_divide(
        ai_nre_yearly,
        ai_net_monthly- ai_nre_monthly 
    )

    breakeven_denominator = (
        talent_ai_monthly_row1
        - talent_ai_monthly_row2
    )

    talent_ai_monthly_row5 = safe_divide(
        talent_ai_yearly_row2,
        breakeven_denominator
    )


    # =========================================================
    # FINAL TABLE
    # =========================================================

    output = pd.DataFrame(
        {
            "Service Improvement": [
                "Net Gain or Loss service Margin Contribution",
                "Cost of NRE Services of Project ((in cards as % FTE)",
                "Net Margin Contribution Year 1",
                "ROI (Net Margin Contribution/Investment) - %",
                "Months to Breakeven (Investment/Net Gain)",
            ],

            # -------------------------
            # Existing Talent columns
            # -------------------------
            "Talent Yearly Margin Contribution (K$)": [
                talent_net_yearly,
                talent_nre_yearly,
                talent_net_year_1,
                talent_roi_original,
                None,
            ],

            "Talent Monthly Margin Contribution (K$)": [
                talent_net_monthly,
                talent_nre_monthly,
                None,
                None,
                talent_breakeven,
            ],

            # -------------------------
            # Existing AI columns
            # -------------------------
            "AI Yearly Margin Contribution (K$)": [
                ai_net_yearly,
                ai_nre_yearly,
                ai_net_year_1,
                ai_roi,
                None,
            ],

            "AI Monthly Margin Contribution (K$)": [
                ai_net_monthly,
                ai_nre_monthly,
                None,
                None,
                ai_breakeven,
            ],

            # -------------------------
            # NEW Talent + AI columns
            # -------------------------
            "Talent+AI Yearly Margin Contribution (K$)": [
                talent_ai_yearly_row1,
                talent_ai_yearly_row2,
                talent_ai_yearly_row3,
                talent_ai_yearly_row4,
                None,
            ],

            "Talent+AI Monthly Margin Contribution (K$)": [
                talent_ai_monthly_row1,
                talent_ai_monthly_row2,
                talent_ai_monthly_row3,
                None,
                talent_ai_monthly_row5,
            ],
        }
    )

    return output.round(2)




def _monthly_service_cost_rates(service_row, premises_values, period="current"):
    talent_tier = _tier(service_row.get("Talent Tier", "X"))
    ai_tier = _tier(service_row.get("AI Tier", "X"))
    talent = _rate(premises_values[period]["talent"], "cost", talent_tier) / 12
    ai = _rate(premises_values[period]["ai"], "cost", ai_tier) / 12
    return talent, ai


# =========================================================
# PLANNED PROJECT COST WORKSHEET AND ROI MODEL
# =========================================================

def build_planned_project_cost_worksheet(
    future_df,
    premises_values,
    talent_months_to_complete,
    ai_months_to_complete,
):
    """Build one planning row for each row in Future Services, including Total."""
    rows = []
    # Keep input/output calculations only for individual service rows.
    service_rows = future_df[
        future_df["Service Improvement"].astype(str).str.strip().str.casefold() != "total"
    ] if "Service Improvement" in future_df.columns else future_df
    for _, service_row in service_rows.iterrows():
        service_name = str(service_row.get("Service Improvement", ""))
        monthly_margin = numeric(
            service_row.get("Talent+AI Monthly Margin Contribution (K$)", 0)
        )
        talent_monthly_cost, ai_monthly_cost = _monthly_service_cost_rates(service_row, premises_values)
        project_monthly_recurring_cost = talent_monthly_cost + ai_monthly_cost
        talent_months = (
            talent_months_to_complete.get(service_name, 0.0)
            if isinstance(talent_months_to_complete, dict)
            else talent_months_to_complete
        )
        ai_months = (
            ai_months_to_complete.get(service_name, 0.0)
            if isinstance(ai_months_to_complete, dict)
            else ai_months_to_complete
        )

        # Months × monthly cost gives a one-time project cost in K$.
        project_non_recurring_cost = (
            numeric(talent_months) * talent_monthly_cost
            + numeric(ai_months) * ai_monthly_cost
        )
        total_12_month_cost = (
            project_non_recurring_cost + project_monthly_recurring_cost * 12
        )
        roi_12_months = (
            (monthly_margin * 12) / total_12_month_cost
            if total_12_month_cost != 0 else None
        )
        months_to_breakeven = (
            (project_monthly_recurring_cost * 12 + project_non_recurring_cost)
            / monthly_margin
            if monthly_margin != 0 else None
        )

        rows.append({
            "Service Improvement": service_name,
            "Talent Tier": _tier(service_row.get("Talent Tier", "X")),
            "AI Tier": _tier(service_row.get("AI Tier", "X")),
            "Talent months to complete": numeric(talent_months),
            "AI months to complete": numeric(ai_months),
            "Talent cost (K$/month)": talent_monthly_cost,
            "AI cost (K$/month)": ai_monthly_cost,
            "External NRE incl. AI (K$)": "-",
            "Project non-recurring cost (K$)": project_non_recurring_cost,
            "Project monthly recurring cost (K$)": project_monthly_recurring_cost,
            "Talent+AI monthly margin (K$)": monthly_margin,
            "ROI in 12 months": roi_12_months,
            "Months to breakeven": months_to_breakeven,
        })

    result = pd.DataFrame(rows)
    if not result.empty:
        # Total row is calculated from service rows; it is never an input row.
        total_monthly_margin = numeric(result["Talent+AI monthly margin (K$)"].sum())
        total_non_recurring = numeric(result["Project non-recurring cost (K$)"].sum())
        total_monthly_recurring = numeric(result["Project monthly recurring cost (K$)"].sum())
        total_12_month_cost = total_non_recurring + total_monthly_recurring * 12
        total_roi = (
            (total_monthly_margin * 12) / total_12_month_cost
            if total_12_month_cost != 0 else None
        )
        total_breakeven = (
            (total_monthly_recurring * 12 + total_non_recurring) / total_monthly_margin
            if total_monthly_margin != 0 else None
        )
        total_row = {
            "Service Improvement": "Total",
            "Talent Tier": "—",
            "AI Tier": "—",
            "Talent months to complete": numeric(result["Talent months to complete"].sum()),
            "AI months to complete": numeric(result["AI months to complete"].sum()),
            "Talent cost (K$/month)": numeric(result["Talent cost (K$/month)"].sum()),
            "AI cost (K$/month)": numeric(result["AI cost (K$/month)"].sum()),
            "External NRE incl. AI (K$)": "-",
            "Project non-recurring cost (K$)": total_non_recurring,
            "Project monthly recurring cost (K$)": total_monthly_recurring,
            "Talent+AI monthly margin (K$)": total_monthly_margin,
            "ROI in 12 months": total_roi,
            "Months to breakeven": total_breakeven,
        }
        result = pd.concat([result, pd.DataFrame([total_row])], ignore_index=True)

    return result



def build_actual_project_cost_worksheet(
    future_df,
    premises_values,
    talent_hours_by_service,
    ai_hours_by_service,
    hours_per_month=160.0,
):
    """Build the Actual Project Cost Worksheet using hours inputs per service."""
    # Use each Future Service row's Talent and AI X/Y/Z tier for monthly rates.
    service_rows = future_df[
        future_df["Service Improvement"].astype(str).str.strip().str.casefold() != "total"
    ].reset_index(drop=True) if "Service Improvement" in future_df.columns else future_df.reset_index(drop=True)

    rows = []
    for _, service_row in service_rows.iterrows():
        service_name = str(service_row.get("Service Improvement", ""))
        talent_hours = numeric(talent_hours_by_service.get(service_name, 0.0))
        ai_hours = numeric(ai_hours_by_service.get(service_name, 0.0))
        # Translate hours to month-equivalent effort for the same cost formulas as the Planned table.
        talent_months = talent_hours / hours_per_month if hours_per_month else 0.0
        ai_months = ai_hours / hours_per_month if hours_per_month else 0.0
        monthly_margin = numeric(service_row.get("Talent+AI Monthly Margin Contribution (K$)", 0))
        talent_monthly_cost, ai_monthly_cost = _monthly_service_cost_rates(service_row, premises_values)

        project_non_recurring_cost = (
            talent_months * talent_monthly_cost + ai_months * ai_monthly_cost
        )
        project_monthly_recurring_cost = talent_monthly_cost + ai_monthly_cost
        total_12_month_cost = project_non_recurring_cost + project_monthly_recurring_cost * 12
        roi_12_months = (
            (monthly_margin * 12) / total_12_month_cost
            if total_12_month_cost != 0 else None
        )
        months_to_breakeven = (
            (project_monthly_recurring_cost * 12 + project_non_recurring_cost) / monthly_margin
            if monthly_margin != 0 else None
        )
        rows.append({
            "Service Improvement": service_name,
            "Talent Tier": _tier(service_row.get("Talent Tier", "X")),
            "AI Tier": _tier(service_row.get("AI Tier", "X")),
            "Talent hours from cards + todos": talent_hours,
            "AI hours from cards + todos": ai_hours,
            "Talent cost (K$/month)": talent_monthly_cost,
            "AI cost (K$/month)": ai_monthly_cost,
            "External NRE incl. AI (K$)": "-",
            "Project non-recurring cost (K$)": project_non_recurring_cost,
            "Project monthly recurring cost (K$)": project_monthly_recurring_cost,
            "Talent+AI monthly margin (K$)": monthly_margin,
            "ROI in 12 months": roi_12_months,
            "Months to breakeven": months_to_breakeven,
        })

    result = pd.DataFrame(rows)
    if not result.empty:
        total_margin = numeric(result["Talent+AI monthly margin (K$)"].sum())
        total_nre = numeric(result["Project non-recurring cost (K$)"].sum())
        total_recurring = numeric(result["Project monthly recurring cost (K$)"].sum())
        total_cost_12m = total_nre + total_recurring * 12
        total_roi = (total_margin * 12 / total_cost_12m) if total_cost_12m else None
        total_breakeven = ((total_recurring * 12 + total_nre) / total_margin) if total_margin else None
        total_row = {
            "Service Improvement": "Total",
            "Talent Tier": "—",
            "AI Tier": "—",
            "Talent hours from cards + todos": numeric(result["Talent hours from cards + todos"].sum()),
            "AI hours from cards + todos": numeric(result["AI hours from cards + todos"].sum()),
            "Talent cost (K$/month)": numeric(result["Talent cost (K$/month)"].sum()),
            "AI cost (K$/month)": numeric(result["AI cost (K$/month)"].sum()),
            "External NRE incl. AI (K$)": "-",
            "Project non-recurring cost (K$)": total_nre,
            "Project monthly recurring cost (K$)": total_recurring,
            "Talent+AI monthly margin (K$)": total_margin,
            "ROI in 12 months": total_roi,
            "Months to breakeven": total_breakeven,
        }
        result = pd.concat([result, pd.DataFrame([total_row])], ignore_index=True)
    return result



def build_planned_vs_actual_comparison(planned_df, actual_df):
    """Join planned and actual worksheets by Service Improvement and calculate deltas."""
    if planned_df is None or actual_df is None or planned_df.empty or actual_df.empty:
        return pd.DataFrame()

    p = planned_df.copy()
    a = actual_df.copy()
    p["Service Improvement"] = p["Service Improvement"].astype(str).str.strip()
    a["Service Improvement"] = a["Service Improvement"].astype(str).str.strip()
    p = p[p["Service Improvement"].str.casefold() != "total"]
    a = a[a["Service Improvement"].str.casefold() != "total"]

    p = p.set_index("Service Improvement")
    a = a.set_index("Service Improvement")
    common = p.index.intersection(a.index, sort=False)
    rows = []

    measures = [
        ("Talent months", "Talent months to complete", "Talent hours from cards + todos", 2),
        ("AI months", "AI months to complete", "AI hours from cards + todos", 2),
        ("Non-recurring cost (K$)", "Project non-recurring cost (K$)", "Project non-recurring cost (K$)", 2),
        ("ROI in 12 months", "ROI in 12 months", "ROI in 12 months", 4),
        ("Months to breakeven", "Months to breakeven", "Months to breakeven", 2),
    ]

    for service in common:
        row = {"Future service": service}
        for label, pcol, acol, precision in measures:
            pv = numeric(p.loc[service, pcol]) if pcol in p.columns else None
            av = numeric(a.loc[service, acol]) if acol in a.columns else None
            if label == "Talent months":
                av = av / 160 if av is not None else None
            elif label == "AI months":
                av = av / 160 if av is not None else None
            delta = (av - pv) if pv is not None and av is not None else None
            if label == "ROI in 12 months" and delta is not None:
                delta *= 100  # show the difference in percentage points
            row[(label, "Planned")] = pv
            row[(label, "Actual")] = av
            row[(label, "Δ")] = delta
        rows.append(row)

    if not rows:
        return pd.DataFrame()
    result = pd.DataFrame(rows)
    # Streamlit column_config and Excel writers require scalar column names.
    # Flatten the grouped Planned / Actual / delta headings into readable strings.
    flattened = []
    for col in result.columns:
        if isinstance(col, tuple):
            if col[0] == "Future service":
                flattened.append("Future service")
            else:
                flattened.append(f"{col[0]} — {col[1]}")
        else:
            flattened.append(str(col))
    result.columns = flattened
    return result


# =========================================================
# MAIN PROCESS
# =========================================================

def process_file(input_file):
    """
    Returns:
        current_df
        future_df
        combined_df
        summary_df
    """

    premises_values = read_premises_values(input_file)
    current_input, future_input = read_excel_tables(input_file)
    schedule_inputs = read_future_service_schedule(input_file)
    return process_inputs(premises_values, current_input, future_input, schedule_inputs)


def process_inputs(premises_values, current_input, future_input, schedule_inputs):
    """
    Run every calculation from already-loaded inputs (Excel or database).

    premises_values : {period: {side: {"cost"/"value": {"X","Y","Z"}}}}
    current_input / future_input : DataFrames with the read_excel_tables() columns
    schedule_inputs : {"talent": [row1, row2, row4], "ai": [row1, row2, row4]}
    """
    # Third table: Cost and Schedule to reach Future services.
    future_schedule_df = calculate_future_service_schedule(
        None,
        premises_values,
        fte_inputs=schedule_inputs,
    )

    current_df = process_table(
        current_input,
        "Current",
        premises_values,
    )
    future_df = process_table(
        future_input,
        "Future",
        premises_values,
    )

    if not current_df.empty and not future_df.empty:
        combined_df = pd.concat(
            [current_df, future_df],
            ignore_index=True,
        )
    elif not current_df.empty:
        combined_df = current_df.copy()
    else:
        combined_df = future_df.copy()

    summary_rows = []

    for service_type, df in [
        ("Current", current_df),
        ("Future", future_df),
    ]:
        if df.empty:
            continue

        summary_rows.append({
            "Service Type": service_type,
            "Rows": len(df),
            "Talent Total % FTE": df["Talent Total % FTE"].sum(),
            "AI Total % FTE": df["AI Total % FTE"].sum(),
            "Talent Service Cost (K$)": df["Talent Service Cost (K$)"].sum(),
            "AI Service Cost (K$)": df["AI Service Cost (K$)"].sum(),
            "Talent Service Value (K$)": df["Talent Service Value (K$)"].sum(),
            "AI Service Value (K$)": df["AI Service Value (K$)"].sum(),
            "Talent Yearly Margin Contribution (K$)": (
                df["Talent Yearly Margin Contribution (K$)"].sum()
            ),
            "AI Yearly Margin Contribution (K$)": (
                df["AI Yearly Margin Contribution (K$)"].sum()
            ),
            "Talent Monthly Margin Contribution (K$)": (
                df["Talent Monthly Margin Contribution (K$)"].sum()
            ),
            "AI Monthly Margin Contribution (K$)": (
                df["AI Monthly Margin Contribution (K$)"].sum()
            ),
        })

    summary_df = pd.DataFrame(summary_rows).round(2)

    future_current_margin_df = calculate_future_current_service_margin(
        current_df, future_df, future_schedule_df
    )

    return (
        current_df,
        future_df,
        combined_df,
        summary_df,
        future_schedule_df,
        future_current_margin_df,
    )


# =========================================================
# EXCEL DOWNLOAD
# =========================================================

def create_excel_download(
    current_df,
    future_df,
    combined_df,
    summary_df,
    future_schedule_df,
    future_current_margin_df,
    planned_project_cost_df=None,
    actual_project_cost_df=None,
    comparison_df=None,
):
    """
    Create an Excel workbook containing Current Services, Future Services,
    and the Cost and Schedule to reach Future services table.
    """

    output = BytesIO()

    with pd.ExcelWriter(
        output,
        engine="openpyxl",
    ) as writer:
        sheet_name = "Calculated Services"

        # Current Services table.
        current_df.to_excel(
            writer,
            sheet_name=sheet_name,
            index=False,
            startrow=0,
        )

        # Future Services table starts after Current table + 3 blank rows.
        future_start_row = len(current_df) + 4
        future_df.to_excel(
            writer,
            sheet_name=sheet_name,
            index=False,
            startrow=future_start_row,
        )

        # Third table starts after Future Services + 3 blank rows.
        schedule_start_row = future_start_row + len(future_df) + 4
        future_schedule_df.to_excel(
            writer,
            sheet_name=sheet_name,
            index=False,
            startrow=schedule_start_row,
        )

        margin_start_row = schedule_start_row + len(future_schedule_df) + 4
        future_current_margin_df.to_excel(
            writer,
            sheet_name=sheet_name,
            index=False,
            startrow=margin_start_row,
        )

        next_row = margin_start_row + len(future_current_margin_df) + 4
        for extra_df in (planned_project_cost_df, actual_project_cost_df, comparison_df):
            if extra_df is not None and not extra_df.empty:
                extra_df.to_excel(
                    writer,
                    sheet_name=sheet_name,
                    index=False,
                    startrow=next_row,
                )
                next_row += len(extra_df) + 4

        worksheet = writer.book[sheet_name]
        worksheet.freeze_panes = "A2"

        for column_cells in worksheet.columns:
            max_length = 0
            column_letter = column_cells[0].column_letter
            for cell in column_cells:
                value = "" if cell.value is None else str(cell.value)
                max_length = max(max_length, len(value))
            worksheet.column_dimensions[column_letter].width = min(
                max(max_length + 2, 12),
                45,
            )

    output.seek(0)
    return output.getvalue()