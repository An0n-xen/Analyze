"""SKYNET Payments — interactive dashboard for Hubtel mobile-money exports.

Upload a Hubtel transaction CSV (or use the bundled sample) and explore revenue,
fees, plans, locations, networks, peak hours, top customers and refunds.
"""

from __future__ import annotations

from pathlib import Path

import pandas as pd
import plotly.express as px
import streamlit as st

# --------------------------------------------------------------------------- #
# Config
# --------------------------------------------------------------------------- #
st.set_page_config(page_title="SKYNET Payments", page_icon="📶", layout="wide")

# Light-red background for the dedicated refunds section (refunds = money out).
st.markdown(
    "<style>.st-key-refund-section{background:#fdecec;border:1px solid #f3b9b9;"
    "border-radius:10px;padding:0.5rem 1rem 1rem;}</style>",
    unsafe_allow_html=True,
)

SAMPLE_CSV = Path(__file__).parent / "h-data.csv"
CURRENCY = "GH₵"

NETWORK_MAP = {
    "mtn-gh": "MTN",
    "vodafone-gh-ussd": "Vodafone",
    "vodafone-gh": "Vodafone",
    "airteltigo-gh": "AirtelTigo",
    "tigo-gh": "AirtelTigo",
}

# Plotly colour sequence kept consistent across charts.
PALETTE = px.colors.qualitative.Set2


def money(value: float) -> str:
    """Format a number as Ghana cedis."""
    return f"{CURRENCY}{value:,.2f}"


# --------------------------------------------------------------------------- #
# Data loading & cleaning
# --------------------------------------------------------------------------- #
@st.cache_data(show_spinner=False)
def load_data(source) -> tuple[pd.DataFrame, int]:
    """Read and clean a Hubtel export.

    Returns the cleaned DataFrame and the number of rows dropped because their
    date or amount could not be parsed.
    """
    df = pd.read_csv(source, dtype=str)
    df.columns = [c.strip() for c in df.columns]

    # Timestamps are US-format: MM/DD/YYYY HH:MM:SS
    df["Date"] = pd.to_datetime(
        df["Date"].str.strip(),
        errors="coerce",
    )

    for col in ("Amount Paid", "Amount After Charges", "Charges"):
        if col in df.columns:
            df[col] = pd.to_numeric(df[col], errors="coerce")

    # Plan + Location from Description, e.g. "SKYNET-AP WiFi - Daily - THEPOINT".
    # Split on " - " (space-hyphen-space) so the hyphen inside "SKYNET-AP" is kept.
    # Segments: [0]="SKYNET-AP WiFi", [1]=plan (Daily/Monthly/...), [2]=location (optional).
    desc = df.get("Description", pd.Series("", index=df.index)).fillna("").str.strip()
    parts = desc.str.split(r"\s+-\s+", regex=True)
    # Match a known plan keyword anywhere in the description so single-word rows
    # ("Daily") classify correctly while junk ("testing api") stays Unknown.
    df["Plan"] = (
        desc.str.extract(r"(?i)\b(Daily|Weekly|Monthly|Semester|Annual|Yearly)\b")[0]
        .str.title()
        .fillna("Unknown")
    )
    # Business rule: rows with no location predate the second site -> DREAMERS.
    df["Location"] = parts.str[2].str.strip().replace("", pd.NA).fillna("DREAMERS")

    channel = df.get("Channel", pd.Series("", index=df.index)).fillna("").str.strip()
    df["Network"] = channel.map(NETWORK_MAP).fillna(channel).replace("", "Unknown")

    df["Status"] = (
        df.get("Status", pd.Series("Unknown", index=df.index))
        .fillna("Unknown")
        .str.strip()
    )

    # Refund flag (Is Refunded column holds "True"/"False" strings).
    refunded = df.get("Is Refunded", pd.Series("False", index=df.index))
    df["Refunded"] = refunded.astype(str).str.strip().str.lower().eq("true")

    # Drop rows we can't analyse.
    before = len(df)
    df = df.dropna(subset=["Date", "Amount Paid"]).copy()
    dropped = before - len(df)

    df["DateOnly"] = df["Date"].dt.date
    df["Hour"] = df["Date"].dt.hour
    df["Weekday"] = df["Date"].dt.day_name()

    return df.reset_index(drop=True), dropped


# --------------------------------------------------------------------------- #
# Header & data source
# --------------------------------------------------------------------------- #
st.title("📶 SKYNET Payments Dashboard")
st.caption(
    "Analyse Hubtel mobile-money transactions — revenue, fees, plans, locations & more."
)

uploaded = st.file_uploader("Upload a Hubtel transaction CSV", type="csv")

if uploaded is not None:
    df, dropped = load_data(uploaded)
    st.success(f"Loaded **{len(df):,}** transactions from your upload.")
elif SAMPLE_CSV.exists():
    df, dropped = load_data(str(SAMPLE_CSV))
    st.info(f"No file uploaded — showing the bundled sample (`{SAMPLE_CSV.name}`).")
else:
    st.warning("Upload a CSV to get started.")
    st.stop()

if dropped:
    st.caption(f"⚠️ Skipped {dropped} row(s) with an unreadable date or amount.")

if df.empty:
    st.warning("No usable rows in this file.")
    st.stop()


# --------------------------------------------------------------------------- #
# Sidebar filters
# --------------------------------------------------------------------------- #
st.sidebar.header("Filters")

min_d, max_d = df["DateOnly"].min(), df["DateOnly"].max()
date_range = st.sidebar.date_input(
    "Date range", value=(min_d, max_d), min_value=min_d, max_value=max_d
)
if isinstance(date_range, (list, tuple)) and len(date_range) == 2:
    start_d, end_d = date_range
else:  # single date picked
    start_d = end_d = date_range


def multi(label: str, col: str) -> list[str]:
    opts = sorted(df[col].dropna().unique().tolist())
    return st.sidebar.multiselect(label, opts, default=opts)


sel_loc = multi("Location", "Location")
sel_plan = multi("Plan", "Plan")
sel_net = multi("Network", "Network")
sel_status = multi("Status", "Status")
hide_refunds = st.sidebar.checkbox("Exclude refunded transactions", value=False)

mask = (
    (df["DateOnly"] >= start_d)
    & (df["DateOnly"] <= end_d)
    & df["Location"].isin(sel_loc)
    & df["Plan"].isin(sel_plan)
    & df["Network"].isin(sel_net)
    & df["Status"].isin(sel_status)
)
if hide_refunds:
    mask &= ~df["Refunded"]

dff = df[mask].copy()

if dff.empty:
    st.warning("No transactions match the current filters.")
    st.stop()


# --------------------------------------------------------------------------- #
# KPIs
# --------------------------------------------------------------------------- #
gross = dff["Amount Paid"].sum()  # what customers paid, before Hubtel charges
rev_after_charges = dff["Amount After Charges"].sum()  # all txns, after charges
fees = dff["Charges"].sum()
ref_mask = dff["Refunded"]
ref_count = int(ref_mask.sum())
# Refunded total is net of fees (the after-charges value actually returned).
ref_amount = dff.loc[ref_mask, "Amount After Charges"].sum()
net_after_refunds = rev_after_charges - ref_amount  # after charges and refunds
n_tx = len(dff)
n_cust = dff["Customer Number"].nunique()

c1, c2, c3, c4, c5, c6 = st.columns(6)
c1.metric(
    "Gross Paid", money(gross), help="Total customers paid, before Hubtel charges."
)
c2.metric(
    "Revenue After Charges",
    money(rev_after_charges),
    help="Gross paid minus Hubtel transaction charges "
    "(all transactions, before refunds).",
)
c3.metric(
    "Net Revenue After Refunds",
    money(net_after_refunds),
    help="Revenue after charges, minus refunded transactions.",
)
c4.metric(
    "Total Fees", money(fees), help="Total Hubtel charges deducted from payments."
)
c5.metric("Transactions", f"{n_tx:,}")
c6.metric("Unique Customers", f"{n_cust:,}")

st.divider()


# --------------------------------------------------------------------------- #
# Refunds — dedicated section (money out, tinted red)
# --------------------------------------------------------------------------- #
with st.container(key="refund-section"):
    st.subheader("💸 Refunds")
    rc1, rc2 = st.columns(2)
    rc1.metric("Refunds", f"{ref_count:,}")
    rc2.metric("Refunded Amount (after fees)", money(ref_amount))

    refunds = dff[ref_mask]
    if refunds.empty:
        st.info("No refunds in the current selection.")
    else:
        by_cust = (
            refunds.groupby("Customer Number")
            .agg(
                **{
                    "Times Refunded": ("Refunded", "size"),
                    "Total Refunded": ("Amount After Charges", "sum"),
                }
            )
            .reset_index()
            .sort_values("Total Refunded", ascending=False)
        )
        by_cust["Customer Number"] = by_cust["Customer Number"].astype(str)
        st.markdown("**Customers refunded**")
        st.dataframe(
            by_cust,
            hide_index=True,
            width="stretch",
            column_config={
                "Customer Number": "Customer",
                "Total Refunded": st.column_config.NumberColumn(
                    "Total Refunded", format="GH₵%.2f"
                ),
            },
        )

st.divider()


# --------------------------------------------------------------------------- #
# Charts
# --------------------------------------------------------------------------- #
def revenue_by(
    col: str,
    title: str,
    amount_col: str = "Amount Paid",
    order: list[str] | None = None,
):
    """Bar chart of revenue grouped by a categorical column.

    Pass `order` to fix the bar order and colours, so charts shown side by side
    keep each category in the same place and colour.
    """
    g = (
        dff.groupby(col, as_index=False)[amount_col]
        .sum()
        .sort_values(amount_col, ascending=False)
    )
    fig = px.bar(
        g,
        x=col,
        y=amount_col,
        color=col,
        text_auto=".2s",
        color_discrete_sequence=PALETTE,
        category_orders={col: order} if order else None,
        title=title,
    )
    fig.update_layout(
        showlegend=False, yaxis_title=f"Revenue ({CURRENCY})", xaxis_title=""
    )
    return fig


tab_trend, tab_break = st.tabs(["📈 Trends", "🧩 Breakdowns"])

with tab_trend:
    freq_label = st.radio("Aggregate by", ["Daily", "Weekly"], horizontal=True, index=0)
    rule = "D" if freq_label == "Daily" else "W"
    ts = (
        dff.set_index("Date")
        .groupby([pd.Grouper(freq=rule), "Location"])["Amount After Charges"]
        .sum()
        .reset_index()
    )
    fig_ts = px.area(
        ts,
        x="Date",
        y="Amount After Charges",
        color="Location",
        color_discrete_sequence=PALETTE,
        title=f"{freq_label} revenue over time by location (after Hubtel fees)",
    )
    fig_ts.update_layout(yaxis_title=f"Revenue ({CURRENCY})", xaxis_title="")
    st.plotly_chart(fig_ts, width="stretch")

    hourly = dff.groupby("Hour", as_index=False)["Amount Paid"].agg(
        Revenue="sum", Transactions="count"
    )
    fig_hour = px.bar(
        hourly,
        x="Hour",
        y="Transactions",
        color="Revenue",
        color_continuous_scale="Greens",
        title="Transactions by hour of day (peak times)",
    )
    fig_hour.update_layout(xaxis=dict(dtick=1))
    st.plotly_chart(fig_hour, width="stretch")

with tab_break:
    # Hostel split — one groupby feeds both breakdowns so they always agree.
    split = (
        dff.groupby("Location", as_index=False)
        .agg(
            **{
                "Gross Paid": ("Amount Paid", "sum"),
                "Charges": ("Charges", "sum"),
                "After Charges": ("Amount After Charges", "sum"),
                "Transactions": ("Amount Paid", "size"),
            }
        )
        .sort_values("Gross Paid", ascending=False)
    )
    hostel_order = split["Location"].tolist()

    def share_of(amounts: pd.Series) -> pd.Series | int:
        """Each hostel's percentage of this breakdown's own total."""
        total = amounts.sum()
        return amounts / total * 100 if total else 0

    with_charges, without_charges = st.columns(2)
    with with_charges:
        st.markdown("**With charges: total money in**")
        st.metric(
            "Gross Paid",
            money(gross),
            help="Total customers paid, before Hubtel charges.",
        )
        fig_money_in = revenue_by(
            "Location",
            "Total money in by hostel (with charges)",
            order=hostel_order,
        )
        fig_money_in.update_layout(yaxis_title=f"Total money in ({CURRENCY})")
        st.plotly_chart(fig_money_in, width="stretch")
        st.dataframe(
            split.assign(**{"Share %": share_of(split["Gross Paid"])})[
                ["Location", "Gross Paid", "Share %", "Transactions"]
            ],
            hide_index=True,
            width="stretch",
            column_config={
                "Location": "Hostel",
                "Gross Paid": st.column_config.NumberColumn(format="GH₵%.2f"),
                "Share %": st.column_config.NumberColumn(format="%.1f%%"),
            },
        )
    with without_charges:
        st.markdown("**Without charges: revenue / profit**")
        st.metric(
            "Revenue After Charges",
            money(rev_after_charges),
            help="Gross paid minus Hubtel transaction charges.",
        )
        st.plotly_chart(
            revenue_by(
                "Location",
                "Revenue by hostel (without charges)",
                amount_col="Amount After Charges",
                order=hostel_order,
            ),
            width="stretch",
        )
        st.dataframe(
            split.assign(**{"Share %": share_of(split["After Charges"])})[
                ["Location", "Charges", "After Charges", "Share %"]
            ],
            hide_index=True,
            width="stretch",
            column_config={
                "Location": "Hostel",
                "Charges": st.column_config.NumberColumn(format="GH₵%.2f"),
                "After Charges": st.column_config.NumberColumn(format="GH₵%.2f"),
                "Share %": st.column_config.NumberColumn(format="%.1f%%"),
            },
        )
    if ref_count:
        st.caption(
            "Refunds are still counted in both breakdowns. To remove them, tick "
            "“Exclude refunded transactions” in the sidebar."
        )

    plan_col, network_col, fees_col = st.columns(3)
    with plan_col:
        st.plotly_chart(revenue_by("Plan", "Revenue by plan"), width="stretch")
    with network_col:
        net_g = dff.groupby("Network", as_index=False)["Amount Paid"].sum()
        fig_net = px.pie(
            net_g,
            names="Network",
            values="Amount Paid",
            hole=0.5,
            color_discrete_sequence=PALETTE,
            title="Revenue share by network",
        )
        st.plotly_chart(fig_net, width="stretch")
    with fees_col:
        fee_pct = (fees / gross * 100) if gross else 0
        summary = pd.DataFrame(
            {
                "Metric": ["Gross paid", "After charges", "After refunds", "Fees"],
                "Amount": [gross, rev_after_charges, net_after_refunds, fees],
            }
        )
        fig_fee = px.bar(
            summary,
            x="Metric",
            y="Amount",
            color="Metric",
            text_auto=".2s",
            color_discrete_sequence=PALETTE,
            title=f"Hubtel fees are {fee_pct:.1f}% of gross",
        )
        fig_fee.update_layout(showlegend=False, yaxis_title=CURRENCY, xaxis_title="")
        st.plotly_chart(fig_fee, width="stretch")

st.divider()


# --------------------------------------------------------------------------- #
# Data table + download
# --------------------------------------------------------------------------- #
st.subheader("Filtered transactions")
display_cols = [
    "Date",
    "Plan",
    "Location",
    "Network",
    "Amount Paid",
    "Amount After Charges",
    "Charges",
    "Status",
    "Refunded",
    "Customer Number",
]
display_cols = [c for c in display_cols if c in dff.columns]
st.dataframe(dff[display_cols], width="stretch", hide_index=True)

st.download_button(
    "⬇️ Download filtered data (CSV)",
    data=dff[display_cols].to_csv(index=False).encode("utf-8"),
    file_name="skynet_filtered.csv",
    mime="text/csv",
)
