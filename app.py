"""
ESGpedia case study — dashboard app (Step 3: scaffold)
========================================================
This is the skeleton: page config, data loading, sidebar filters
(Year, Pillar, Company), and empty tabs for the four views.

Steps 4-7 fill in the tab bodies marked with TODO below — nothing
else in this file should need to change structurally.

Run locally:   streamlit run app.py
(expects the 5 CSVs from prepare_data.py in the same folder as this file)
"""

from pathlib import Path

import pandas as pd
import plotly.express as px
import streamlit as st

DATA_DIR = Path(__file__).parent

# Friendly display labels for data_type, so the filter reads naturally
# to a non-technical user. Keeping Electricity Consumption and
# Renewable Energy as SEPARATE options is intentional (see step 1 notes) -
# they are different things that happen to share the metric label
# "Electricity" and must not be summed together.
PILLAR_LABELS = {
    "Electricity Consumption": "Electricity (grid)",
    "Renewable Energy": "Renewable energy",
    "Stationary Asset Combustion": "Fuel (diesel / petrol)",
    "Water": "Water",
    "Waste": "Waste",
}
PILLAR_LABELS_INV = {v: k for k, v in PILLAR_LABELS.items()}

# Display order for facets/legends - not alphabetical, groups the two
# electricity-related pillars together at the top.
PILLAR_ORDER = [
    "Electricity (grid)",
    "Renewable energy",
    "Fuel (diesel / petrol)",
    "Water",
    "Waste",
]


# ---------------------------------------------------------------------
# Data loading (cached so filters don't re-read CSVs on every interaction)
# ---------------------------------------------------------------------
@st.cache_data
def load_data():
    activity = pd.read_csv(DATA_DIR / "esg_activity_clean.csv")
    emissions = pd.read_csv(DATA_DIR / "esg_emissions_clean.csv")
    hierarchy = pd.read_csv(DATA_DIR / "company_hierarchy.csv")
    year_coverage = pd.read_csv(DATA_DIR / "company_year_coverage.csv")
    quality_summary = pd.read_csv(DATA_DIR / "data_quality_summary.csv")
    return activity, emissions, hierarchy, year_coverage, quality_summary


activity, emissions, hierarchy, year_coverage, quality_summary = load_data()


# ---------------------------------------------------------------------
# Page config + header
# ---------------------------------------------------------------------
st.set_page_config(
    page_title="Frontier Developments — ESG Performance",
    page_icon="🌱",
    layout="wide",
)

st.title("🌱 Frontier Developments — ESG Performance Dashboard")
st.caption(
    "Monthly electricity, water, waste and fuel data across Frontier "
    "Developments Ltd. and its subsidiaries. Use the filters on the left "
    "to explore by year, ESG pillar, and company."
)


# ---------------------------------------------------------------------
# Sidebar filters
# ---------------------------------------------------------------------
st.sidebar.header("Filters")

# --- Year filter ---
all_years = sorted(activity["reportedYear"].unique())
selected_years = st.sidebar.multiselect(
    "Year", options=all_years, default=all_years
)

# --- Pillar filter (data_type, shown with friendly labels) ---
available_pillars = [
    PILLAR_LABELS[dt] for dt in activity["data_type"].unique() if dt in PILLAR_LABELS
]
selected_pillar_labels = st.sidebar.multiselect(
    "ESG pillar", options=available_pillars, default=available_pillars
)
selected_pillars = [PILLAR_LABELS_INV[label] for label in selected_pillar_labels]

# --- Company filter, indented by hierarchy level so the tree is visible
# in the filter itself. Includes ALL 14 companies (not just the 7 that
# have data) so the reporting-coverage gap is visible as a selectable,
# empty-result option rather than hidden entirely. ---
hierarchy_sorted = hierarchy.sort_values(["top_parent_name", "level", "company_name"])
company_display_map = {
    f"{'—' * row.level} {row.company_name}": row.company_name
    for row in hierarchy_sorted.itertuples()
}
selected_company_labels = st.sidebar.multiselect(
    "Company",
    options=list(company_display_map.keys()),
    default=list(company_display_map.keys()),
)
selected_companies = [company_display_map[label] for label in selected_company_labels]


# ---------------------------------------------------------------------
# Apply filters
# ---------------------------------------------------------------------
def apply_filters(df: pd.DataFrame) -> pd.DataFrame:
    return df[
        df["reportedYear"].isin(selected_years)
        & df["data_type"].isin(selected_pillars)
        & df["company_name"].isin(selected_companies)
    ]


activity_filtered = apply_filters(activity)
emissions_filtered = apply_filters(emissions)


# ---------------------------------------------------------------------
# Scaffold sanity check — quick KPI row so we can SEE the filters are
# wired up correctly before building real charts on top of them.
# ---------------------------------------------------------------------
col1, col2, col3 = st.columns(3)
col1.metric("Activity records matching filters", len(activity_filtered))
col2.metric("Companies selected", len(selected_companies))
col3.metric(
    "Companies with no data in selection",
    sum(
        activity_filtered[activity_filtered.company_name == c].empty
        for c in selected_companies
    ),
)

if activity_filtered.empty:
    st.warning(
        "No data matches the current filter selection. If you've selected "
        "only companies like Kestrel Properties or Horizon Property Group, "
        "that's expected — they have not submitted any ESG data (see the "
        "Data Quality tab)."
    )


# ---------------------------------------------------------------------
# Tab structure — steps 4-7 build these out
# ---------------------------------------------------------------------
tab_trend, tab_contributors, tab_hierarchy, tab_quality = st.tabs(
    ["📈 Trend over time", "🏆 Top contributors", "🏢 Company hierarchy", "⚠️ Data quality"]
)

with tab_trend:
    st.subheader("How has ESG performance trended over time?")

    if activity_filtered.empty:
        st.info("No data to chart for the current filter selection.")
    else:
        trend_df = activity_filtered.copy()
        trend_df["pillar"] = trend_df["data_type"].map(PILLAR_LABELS)
        trend_df["month_dt"] = pd.to_datetime(trend_df["month"], format="%Y-%m")

        # Only order/facet by pillars actually present in the current
        # selection, so an unselected pillar doesn't render an empty row.
        present_order = [p for p in PILLAR_ORDER if p in trend_df["pillar"].unique()]
        trend_df["pillar"] = pd.Categorical(
            trend_df["pillar"], categories=present_order, ordered=True
        )

        monthly = (
            trend_df.groupby(["pillar", "unit", "month_dt"], as_index=False, observed=True)[
                "total_value"
            ]
            .sum()
            .sort_values(["pillar", "month_dt"])
        )

        # each pillar has one consistent native unit (verified during data
        # profiling), so this lookup is safe
        pillar_unit = monthly.drop_duplicates("pillar").set_index("pillar")["unit"].to_dict()

        fig = px.line(
            monthly,
            x="month_dt",
            y="total_value",
            facet_row="pillar",
            markers=True,
            category_orders={"pillar": present_order},
            labels={"month_dt": "Month", "total_value": "Monthly total"},
        )
        # independent y-axis per pillar - a shared axis would be
        # meaningless across kWh, m³, litre and kg
        fig.update_yaxes(matches=None)

        def _relabel_facet(annotation):
            pillar_name = annotation.text.split("=")[-1]
            unit = pillar_unit.get(pillar_name, "")
            annotation.update(
                text=f"{pillar_name} ({unit})" if unit else pillar_name
            )

        fig.for_each_annotation(_relabel_facet)
        fig.update_layout(
            height=200 * len(present_order),
            title="Monthly totals by ESG pillar",
            showlegend=False,
            margin=dict(t=60),
        )
        st.plotly_chart(fig)

        if trend_df["is_negative"].any() or trend_df["is_sparse_metric"].any():
            st.caption(
                "⚠️ This selection includes negative-value and/or sparse-data "
                "readings, which affect the monthly totals above — see the "
                "Data Quality tab before treating these as final figures."
            )

with tab_contributors:
    st.subheader("Which companies and assets are the largest contributors?")

    if activity_filtered.empty:
        st.info("No data to chart for the current filter selection.")
    else:
        contrib_df = activity_filtered.copy()
        contrib_df["pillar"] = contrib_df["data_type"].map(PILLAR_LABELS)
        contrib_available = [p for p in PILLAR_ORDER if p in contrib_df["pillar"].unique()]

        control_col, topn_col = st.columns([3, 2])
        with control_col:
            chosen_pillar = st.radio(
                "Pillar", options=contrib_available, horizontal=True, key="contrib_pillar"
            )
        with topn_col:
            top_n_label = st.radio(
                "Show top",
                options=["Top 5", "Top 10", "Top 15", "All"],
                index=1,
                horizontal=True,
                key="contrib_topn",
            )
        top_n = None if top_n_label == "All" else int(top_n_label.split()[1])

        pillar_df = contrib_df[contrib_df["pillar"] == chosen_pillar]
        unit = pillar_df["unit"].iloc[0]

        by_company = (
            pillar_df.groupby("company_name", as_index=False)["total_value"]
            .sum()
            .sort_values("total_value", ascending=False)
        )
        by_asset = (
            pillar_df.groupby(["asset_name", "company_name"], as_index=False)["total_value"]
            .sum()
            .sort_values("total_value", ascending=False)
        )

        by_company_display = (by_company.head(top_n) if top_n else by_company).sort_values(
            "total_value"
        )
        by_asset_display = (by_asset.head(top_n) if top_n else by_asset).sort_values(
            "total_value"
        )

        chart_col1, chart_col2 = st.columns(2)
        with chart_col1:
            fig_company = px.bar(
                by_company_display,
                x="total_value",
                y="company_name",
                orientation="h",
                labels={"total_value": f"Total ({unit})", "company_name": "Company"},
                title=f"Top companies — {chosen_pillar} ({unit})",
            )
            fig_company.update_layout(margin=dict(t=60))
            st.plotly_chart(fig_company)
        with chart_col2:
            fig_asset = px.bar(
                by_asset_display,
                x="total_value",
                y="asset_name",
                orientation="h",
                hover_data=["company_name"],
                labels={"total_value": f"Total ({unit})", "asset_name": "Asset"},
                title=f"Top assets — {chosen_pillar} ({unit})",
            )
            fig_asset.update_layout(margin=dict(t=60))
            st.plotly_chart(fig_asset)

        n_companies_with_data = pillar_df["company_name"].nunique()
        st.caption(
            f"{n_companies_with_data} of the {len(selected_companies)} selected companies "
            f"reported {chosen_pillar} data in this period. Totals reflect the years and "
            f"companies chosen in the sidebar."
        )

with tab_hierarchy:
    st.subheader("How does performance break down across the hierarchy?")
    st.caption(
        "This view always shows the **full company tree**, regardless of the Company "
        "filter in the sidebar, so reporting gaps stay visible. Year and pillar filters "
        "still apply. Sizes are in **kg CO2e** — the one unit shared across electricity, "
        "water, waste and fuel — so the whole hierarchy can be compared on one scale."
    )

    # deliberately NOT filtered by selected_companies - the tree structure
    # itself should always be complete
    hier_activity = activity[
        activity["reportedYear"].isin(selected_years) & activity["data_type"].isin(selected_pillars)
    ]
    hier_emissions = emissions[
        emissions["reportedYear"].isin(selected_years) & emissions["data_type"].isin(selected_pillars)
    ]

    if hier_emissions.empty:
        st.info("No CO2e data available for the selected year(s)/pillar(s).")
    else:
        direct_co2e = hier_emissions.groupby("company_name")["total_value"].sum()
        companies_with_rows = set(hier_activity["company_name"].unique())

        name_to_cid = dict(zip(hierarchy["company_name"], hierarchy["customer_id"]))
        cid_to_parent_cid = {
            cid: name_to_cid.get(pname) if pd.notna(pname) else None
            for cid, pname in zip(hierarchy["customer_id"], hierarchy["immediate_parent_name"])
        }
        children_of = {}
        for cid, pcid in cid_to_parent_cid.items():
            if pcid is not None:
                children_of.setdefault(pcid, []).append(cid)

        cid_to_name = dict(zip(hierarchy["customer_id"], hierarchy["company_name"]))
        direct_by_cid = {cid: direct_co2e.get(name, 0.0) for cid, name in cid_to_name.items()}

        # bottom-up rollup computed explicitly here (not left to the charting
        # library) so the numbers are verifiable: a company's total = its own
        # direct emissions + all descendants' totals
        def rollup(cid: int) -> float:
            total = direct_by_cid.get(cid, 0.0)
            for child_cid in children_of.get(cid, []):
                total += rollup(child_cid)
            return total

        hier_view = hierarchy.copy()
        hier_view["rollup_co2e"] = hier_view["customer_id"].apply(rollup)
        hier_view["direct_co2e"] = hier_view["company_name"].map(direct_co2e).fillna(0.0)
        hier_view["has_data"] = hier_view["company_name"].isin(companies_with_rows)
        hier_view["level_label"] = hier_view["level"].map(
            {0: "Top parent", 1: "Subsidiary", 2: "Sub-subsidiary"}
        )

        ids = hier_view["customer_id"].astype(str)
        parents = hier_view["customer_id"].map(cid_to_parent_cid).apply(
            lambda x: str(int(x)) if pd.notna(x) else ""
        )

        fig = px.treemap(
            ids=ids,
            parents=parents,
            names=hier_view["company_name"],
            values=hier_view["rollup_co2e"],
            branchvalues="total",
            color=hier_view["level_label"],
            hover_data={"direct_co2e": hier_view["direct_co2e"].round(1)},
        )
        fig.update_layout(
            title="Company hierarchy sized by total footprint (kg CO2e)",
            margin=dict(t=60, l=10, r=10, b=10),
            height=500,
        )
        st.plotly_chart(fig)

        no_data_companies = hier_view.loc[~hier_view["has_data"], "company_name"].tolist()
        if no_data_companies:
            st.warning(
                f"**{len(no_data_companies)} of {len(hier_view)} companies in the hierarchy "
                f"have not submitted any ESG data** for the selected year(s)/pillar(s): "
                + ", ".join(no_data_companies)
                + ". Their boxes above only appear if a subsidiary of theirs reports instead."
            )

        st.markdown("**Full roll-up detail**")
        table = hier_view.sort_values(["top_parent_name", "level", "company_name"]).copy()
        table["Company"] = table.apply(lambda r: ("　" * r["level"]) + "└ " * (r["level"] > 0) + r["company_name"], axis=1)
        table["Rolled-up CO2e (kg)"] = table["rollup_co2e"].map(lambda v: f"{v:,.0f}")
        table["Direct CO2e (kg)"] = table["direct_co2e"].map(lambda v: f"{v:,.0f}")
        table["Reported data?"] = table["has_data"].map({True: "Yes", False: "No"})
        st.dataframe(
            table[["Company", "level_label", "Rolled-up CO2e (kg)", "Direct CO2e (kg)", "Reported data?"]]
            .rename(columns={"level_label": "Level"}),
            width="stretch",
            hide_index=True,
        )
        st.caption(
            "\"Rolled-up\" = this company's own reporting plus everything from its "
            "subsidiaries. \"Direct\" = only what this company itself submitted. A parent "
            "can show \"Reported data? No\" but still have a non-zero rolled-up total if "
            "its subsidiaries report — that's exactly what happens with Kestrel Properties."
        )

with tab_quality:
    st.subheader("Notable patterns, anomalies, and data quality")

    # scoped like the hierarchy tab: ignores the Company filter so the
    # coverage number stays consistent whichever tab you're looking at
    dq_activity_all_companies = activity[
        activity["reportedYear"].isin(selected_years) & activity["data_type"].isin(selected_pillars)
    ]
    companies_with_rows = set(dq_activity_all_companies["company_name"].unique())
    no_data_companies = hierarchy.loc[
        ~hierarchy["company_name"].isin(companies_with_rows), "company_name"
    ].tolist()

    n_negative = int(activity_filtered["is_negative"].sum())
    n_zero = int(activity_filtered["is_zero"].sum())
    sparse_in_view = sorted(
        activity_filtered.loc[activity_filtered["is_sparse_metric"], "metric"].unique()
    )

    kpi1, kpi2, kpi3, kpi4 = st.columns(4)
    kpi1.metric("Companies not reporting", f"{len(no_data_companies)} / {len(hierarchy)}")
    kpi2.metric("Negative-value readings", n_negative)
    kpi3.metric("Zero-value readings", n_zero)
    kpi4.metric("Sparse metrics in view", len(sparse_in_view))

    if no_data_companies:
        st.warning(
            "**Not reporting for the selected year(s)/pillar(s):** "
            + ", ".join(no_data_companies)
        )

    if activity_filtered.empty:
        st.info("No activity data in the current selection to analyze further.")
    else:
        st.markdown("**Negative and zero readings by metric**")
        neg_zero_by_metric = (
            activity_filtered.groupby("metric")[["is_negative", "is_zero"]].sum().reset_index()
        )
        neg_zero_by_metric = neg_zero_by_metric[
            (neg_zero_by_metric["is_negative"] > 0) | (neg_zero_by_metric["is_zero"] > 0)
        ].sort_values("is_zero", ascending=False)

        if neg_zero_by_metric.empty:
            st.write("No negative or zero readings in the current selection.")
        else:
            nz_long = neg_zero_by_metric.melt(
                id_vars="metric",
                value_vars=["is_negative", "is_zero"],
                var_name="type",
                value_name="count",
            )
            nz_long["type"] = nz_long["type"].map({"is_negative": "Negative", "is_zero": "Zero"})
            fig_nz = px.bar(
                nz_long,
                x="count",
                y="metric",
                color="type",
                orientation="h",
                barmode="group",
                labels={"count": "Number of readings", "metric": "Metric", "type": "Reading type"},
                title="Negative and zero readings by metric (current selection)",
            )
            fig_nz.update_layout(margin=dict(t=60))
            st.plotly_chart(fig_nz)

        if sparse_in_view:
            st.caption(
                "⚠️ Sparse metrics in this selection (3 or fewer data points in the full "
                "dataset — trend lines for these aren't reliable): " + ", ".join(sparse_in_view)
            )

        st.markdown("**Reporting history by company**")
        # ignores the Year filter deliberately - it's the thing being measured -
        # but respects the pillar filter, so "narrow to Waste" shows waste-specific coverage
        coverage_scope = activity[activity["data_type"].isin(selected_pillars)]
        coverage = (
            coverage_scope.groupby("company_name")["reportedYear"]
            .agg(first_year="min", last_year="max", n_years="nunique")
            .reset_index()
            .sort_values("company_name")
        )
        st.dataframe(
            coverage.rename(
                columns={
                    "company_name": "Company",
                    "first_year": "First year",
                    "last_year": "Last year",
                    "n_years": "Distinct years reporting",
                }
            ),
            width="stretch",
            hide_index=True,
        )
        st.caption(
            "Ignores the Year filter above (it's the thing being measured here) but "
            "respects the pillar filter."
        )

        st.markdown("**Activity reported but not converted to CO2e**")
        key_cols = ["organizationId", "asset_name", "metric", "month"]
        act_keys = activity_filtered[key_cols + ["total_value", "company_name"]].rename(
            columns={"total_value": "activity_value"}
        )
        em_keys = emissions_filtered[key_cols + ["total_value"]].rename(
            columns={"total_value": "co2e_value"}
        )
        joined = act_keys.merge(em_keys, on=key_cols, how="inner")
        zero_conversion = joined[(joined["activity_value"] != 0) & (joined["co2e_value"] == 0)]

        if zero_conversion.empty:
            st.write(
                "No cases found where reported activity has a zero CO2e conversion "
                "in this selection."
            )
        else:
            zc_summary = (
                zero_conversion.groupby(["company_name", "metric"])
                .size()
                .reset_index(name="affected_months")
                .sort_values("affected_months", ascending=False)
            )
            st.dataframe(
                zc_summary.rename(
                    columns={
                        "company_name": "Company",
                        "metric": "Metric",
                        "affected_months": "Months affected",
                    }
                ),
                width="stretch",
                hide_index=True,
            )
            st.caption(
                "These combinations report real, non-zero activity but every matching kg "
                "CO2e row is exactly 0 in this selection — likely a missing emission factor "
                "in the source data for that metric, not genuinely zero impact. Worth "
                "confirming with the client before quoting a carbon figure for these."
            )
