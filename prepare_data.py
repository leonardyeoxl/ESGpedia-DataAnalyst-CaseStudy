"""
ESGpedia case study — data prep pipeline
=========================================
Reads the 3-sheet source workbook and produces clean, analysis-ready tables:

  1. company_hierarchy.csv   — one row per company, with resolved level,
                                immediate_parent, and top_parent
  2. esg_activity_clean.csv  — long-format activity data (native units: kWh, m³,
                                litre, kg), joined to the hierarchy, with
                                per-row quality flags
  3. esg_emissions_clean.csv — same rows, but the parallel kg CO2e values
  4. data_quality_summary.csv— aggregated counts for the dashboard's
                                data-quality panel (negatives, zeros, sparse
                                metrics, per-company year coverage, and the
                                no-data-submitted company list)

Run: python3 prepare_data.py <path_to_xlsx> <output_dir>
"""

import sys
import pandas as pd


def resolve_hierarchy(company: pd.DataFrame, tier: pd.DataFrame) -> pd.DataFrame:
    """Walk each company up company_tier to find its immediate parent,
    top-level parent, and depth (level). Assumes a single-parent tree
    (verified against this dataset: every supplier_customer_id appears
    at most once as a child)."""
    parent_of = dict(zip(tier.supplier_customer_id, tier.client_customer_id))
    name_of = dict(zip(company.customer_id, company.company_name))

    rows = []
    for cid in company.customer_id:
        level = 0
        current = cid
        immediate_parent_id = parent_of.get(cid)
        while current in parent_of:
            current = parent_of[current]
            level += 1
        rows.append({
            "customer_id": cid,
            "level": level,
            "immediate_parent_id": immediate_parent_id,
            "immediate_parent_name": name_of.get(immediate_parent_id),
            "top_parent_id": current,
            "top_parent_name": name_of.get(current),
        })
    hierarchy = pd.DataFrame(rows).merge(company, on="customer_id", how="left")
    return hierarchy[
        ["customer_id", "organization_id", "company_name", "level",
         "immediate_parent_name", "top_parent_name"]
    ]


def build_quality_flags(df: pd.DataFrame) -> pd.DataFrame:
    """Row-level flags. Kept as columns (not filtered out) so the dashboard
    can choose to show/exclude/highlight rather than silently losing rows."""
    df = df.copy()
    df["is_negative"] = df["total_value"] < 0
    df["is_zero"] = df["total_value"] == 0

    # a metric is "sparse" if it has 3 or fewer total data points across
    # the whole dataset — not enough to plot a meaningful trend line
    metric_counts = df.groupby("metric")["total_value"].transform("count")
    df["is_sparse_metric"] = metric_counts <= 3
    return df


def main(xlsx_path: str, out_dir: str):
    xl = pd.ExcelFile(xlsx_path)
    raw = xl.parse("raw_data")
    company = xl.parse("company")
    tier = xl.parse("company_tier")

    # --- 1. hierarchy ---
    hierarchy = resolve_hierarchy(company, tier)
    hierarchy.to_csv(f"{out_dir}/company_hierarchy.csv", index=False)

    # --- 2. join raw_data to hierarchy ---
    # hierarchy also carries company_name (from the company sheet); drop it
    # before merging so pandas doesn't silently split it into
    # company_name_x / company_name_y. raw_data's company_name is kept as-is.
    hierarchy_for_merge = hierarchy.drop(columns=["company_name"]).rename(
        columns={"organization_id": "organizationId"}
    )
    merged = raw.merge(hierarchy_for_merge, on="organizationId", how="left")

    # --- 3. split activity (native units) vs emissions (kg CO2e) ---
    activity = merged[merged.unit != "kg CO2e"].copy()
    emissions = merged[merged.unit == "kg CO2e"].copy()

    activity = build_quality_flags(activity)
    emissions = build_quality_flags(emissions)

    activity.to_csv(f"{out_dir}/esg_activity_clean.csv", index=False)
    emissions.to_csv(f"{out_dir}/esg_emissions_clean.csv", index=False)

    # --- 4. data quality summary for the dashboard's callout panel ---
    summary_rows = []

    # companies in the hierarchy with zero submitted rows
    reporting_orgs = set(raw.organizationId.unique())
    no_data_companies = hierarchy[
        ~hierarchy.organization_id.isin(reporting_orgs)
    ]["company_name"].tolist()
    summary_rows.append({
        "check": "companies_with_no_submitted_data",
        "detail": "; ".join(no_data_companies),
        "count": len(no_data_companies),
    })

    summary_rows.append({
        "check": "negative_value_rows",
        "detail": "metrics: " + ", ".join(
            activity[activity.is_negative].metric.unique()
        ),
        "count": int(activity.is_negative.sum()),
    })

    summary_rows.append({
        "check": "zero_value_rows",
        "detail": "metrics: " + ", ".join(
            activity[activity.is_zero].metric.unique()
        ),
        "count": int(activity.is_zero.sum()),
    })

    sparse_metrics = activity[activity.is_sparse_metric].metric.unique().tolist()
    summary_rows.append({
        "check": "sparse_metrics_3_or_fewer_points",
        "detail": "; ".join(sparse_metrics),
        "count": len(sparse_metrics),
    })

    # per-company year coverage (uneven reporting history)
    coverage = raw.groupby("company_name")["reportedYear"].agg(
        min_year="min", max_year="max", n_years="nunique"
    ).reset_index()
    coverage.to_csv(f"{out_dir}/company_year_coverage.csv", index=False)
    summary_rows.append({
        "check": "company_year_coverage_detail",
        "detail": "see company_year_coverage.csv",
        "count": len(coverage),
    })

    pd.DataFrame(summary_rows).to_csv(
        f"{out_dir}/data_quality_summary.csv", index=False
    )

    print("Done. Files written to", out_dir)
    print(" - company_hierarchy.csv       ", len(hierarchy), "rows")
    print(" - esg_activity_clean.csv      ", len(activity), "rows")
    print(" - esg_emissions_clean.csv     ", len(emissions), "rows")
    print(" - company_year_coverage.csv   ", len(coverage), "rows")
    print(" - data_quality_summary.csv    ", len(summary_rows), "rows")


if __name__ == "__main__":
    xlsx_path = sys.argv[1] if len(sys.argv) > 1 else "ESGpedia_Data_Analyst_Case_Study_Dataset.xlsx"
    out_dir = sys.argv[2] if len(sys.argv) > 2 else "."
    main(xlsx_path, out_dir)
