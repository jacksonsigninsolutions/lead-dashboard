import streamlit as st
import pandas as pd
import matplotlib.pyplot as plt
import seaborn as sns
import gspread
from gspread_dataframe import get_as_dataframe
from oauth2client.service_account import ServiceAccountCredentials
from datetime import datetime

st.set_page_config(page_title="Lead Dashboard", layout="wide")
st.title("2025 Leads and Campaigns Dashboard")

# --- Google Sheets Setup ---
scope = [
    'https://www.googleapis.com/auth/spreadsheets',
    'https://www.googleapis.com/auth/drive'
]
service_account_info = st.secrets["gcp_service_account"]
creds = ServiceAccountCredentials.from_json_keyfile_dict(service_account_info, scope)
client = gspread.authorize(creds)

# --- Open Google Sheet ---
spreadsheet = client.open_by_url("https://docs.google.com/spreadsheets/d/1tZhb4xf2Mb7r0YwH-ow-73KvebzFI6YCoPeHEB3eBVM/edit?usp=sharing")
leads_w_opps_sheet = spreadsheet.worksheet("Leads w Opps")
campaigns_w_leads_sheet = spreadsheet.worksheet("Campaigns w Leads")
campaign_report_sheet = spreadsheet.worksheet("Campaign Report")
log_worksheet = spreadsheet.worksheet("Auto Refresh Execution Log")

# --- Last Update ---
raw_last_update = log_worksheet.acell('A2').value
parsed_dt = datetime.strptime(raw_last_update, "%m/%d/%Y %H:%M:%S")
formatted_last_update = parsed_dt.strftime("Last Updated: %m/%d/%Y %I:%M %p")

# --- Load DataFrames ---
leads_w_opps = get_as_dataframe(leads_w_opps_sheet, evaluate_formulas=True).dropna(how='all')
campaigns_w_leads = get_as_dataframe(campaigns_w_leads_sheet, evaluate_formulas=True).dropna(how='all')
campaign_report = get_as_dataframe(campaign_report_sheet, evaluate_formulas=True).dropna(how='all')

# Clean Dates
leads_w_opps["Created Date"] = pd.to_datetime(leads_w_opps["Created Date"], errors="coerce")
leads_w_opps["Converted Date"] = pd.to_datetime(leads_w_opps["Converted Date"], errors="coerce")
leads_w_opps["Created Month"] = leads_w_opps["Created Date"].dt.strftime('%B')

# Is Qualified
leads_w_opps["Is Qualified"] = leads_w_opps["Qualified Date"].notna().map({True: "Qualified", False: "Not Qualified"})

# Classification
def classify_account(row):
    segment = row["Segment"]
    if segment in ["Mid Market", "Mass Market"]:
        return "SMB"
    elif segment == "Enterprise":
        return "ENT"
    else:
        return "Unclassified"

leads_w_opps["Account Classification"] = leads_w_opps.apply(classify_account, axis=1)

# --- Streamlit Filters ---
st.sidebar.header("Filters")
lead_owner = st.sidebar.selectbox("Lead Owner", ["All"] + sorted(leads_w_opps["Lead Owner"].dropna().unique()))
sub_industry = st.sidebar.selectbox("ZI Sub-Industry", ["All"] + sorted(leads_w_opps["ZI Sub-Industry"].dropna().unique()))
month_order = ['January', 'February', 'March', 'April', 'May', 'June', 'July', 
               'August', 'September', 'October', 'November', 'December']
months_available = [m for m in month_order if m in leads_w_opps["Created Month"].dropna().unique()]
month = st.sidebar.selectbox("Created Month", ["All"] + months_available)
classification = st.sidebar.selectbox("Account Classification", ["All"] + sorted(leads_w_opps["Account Classification"].dropna().unique()))

# --- Apply Filters ---
df = leads_w_opps.copy()
if lead_owner != "All":
    df = df[df["Lead Owner"] == lead_owner]
if sub_industry != "All":
    df = df[df["ZI Sub-Industry"] == sub_industry]
if month != "All":
    df = df[df["Created Month"] == month]
if classification != "All":
    df = df[df["Account Classification"] == classification]

# --- Last Updated Text ---
st.markdown(f"#### {formatted_last_update}")

# --- KPI Metrics ---
total_leads = df["Lead 18-Digit ID"].nunique()
convert_to_opp_pct = df["Opportunity: Created Date"].notna().mean() * 100
closed_won_count = df[df["Stage"] == "Closed Won"].shape[0]
total_opps = df["Opportunity Name"].nunique()
closed_won_rate = (closed_won_count / total_opps * 100) if total_opps > 0 else 0

col1, col2, col3 = st.columns(3)
col1.metric("Lead Count", f"{total_leads:,}")
col2.metric("Convert to Opp %", f"{convert_to_opp_pct:.2f}%")
col3.metric("Closed Won Rate", f"{closed_won_rate:.2f}%")

# --- Leads Created + Lead Sources ---
colA, colB = st.columns(2)

with colA:
    st.markdown("### Leads Created by Month")
    monthly = df.groupby("Created Month")["Lead 18-Digit ID"].nunique()
    ordered_months = [
        'January', 'February', 'March', 'April', 'May', 'June',
        'July', 'August', 'September', 'October', 'November', 'December'
    ]
    monthly = monthly.reindex([m for m in ordered_months if m in monthly.index])

    fig1, ax1 = plt.subplots(figsize=(6, 3))

    sns.lineplot(x=monthly.index, y=monthly.values, marker='o', ax=ax1)

    # Dynamic label positioning and smaller font
    for i, v in enumerate(monthly.values):
        offset = (max(monthly.values) * 0.05) if len(monthly) > 0 else 1
        ax1.text(i, v + offset, str(int(v)), ha='center', fontsize=8)

    # Fix Y axis limits so it matches bar chart height (avoid dynamic shrink)
    max_y = max(monthly.values) if len(monthly) > 0 else 1
    ax1.set_ylim(0, max_y * 1.3)  # add buffer so labels don't get cut off

    ax1.set_ylabel("Lead Count")
    ax1.grid(True)
    plt.tight_layout()

    st.pyplot(fig1)

with colB:
    st.markdown("### Top Lead Sources")
    top_sources = (
        df.groupby("Lead Source")["Lead 18-Digit ID"]
        .nunique()
        .sort_values(ascending=False)
        .head(5)
    )

    fig2, ax2 = plt.subplots(figsize=(6, 3))

    # Plot horizontal bar chart
    top_sources[::-1].plot(kind="barh", color="#2ecc71", ax=ax2)

    # Add labels at end of each bar
    for i, v in enumerate(top_sources[::-1].values):
        ax2.text(
            v + (max(top_sources.values) * 0.02),  # offset slightly after bar
            i,
            f"{int(v):,}",  # format with commas
            va="center",
            fontsize=9
        )

    # Fix x-axis ticks: integers, clean spacing
    max_x = max(top_sources.values) if len(top_sources) > 0 else 1
    ax2.set_xlim(0, max_x * 1.2)

    # Tick step: split into ~5 intervals (no decimals)
    step = max(1, int(max_x // 5))
    ax2.set_xticks(range(0, int(max_x * 1.2) + 1, step))

    # Format x-axis ticks with commas
    ax2.xaxis.set_major_formatter(plt.FuncFormatter(lambda x, _: f"{int(x):,}"))

    # Remove extra labels
    ax2.set_xlabel("")
    ax2.set_ylabel("")
    ax2.grid(axis="x", linestyle="--", alpha=0.7)
    plt.tight_layout()

    st.pyplot(fig2)

# --- Top Campaigns ---
st.markdown("### Top Associated Campaigns")
merged = df.merge(campaigns_w_leads, on="Lead 18-Digit ID", how="left")
top_campaigns_table = (
    merged.groupby("Campaign Name")["Lead 18-Digit ID"]
    .nunique()
    .reset_index()
    .rename(columns={"Lead 18-Digit ID": "Lead Count"})
    .sort_values("Lead Count", ascending=False)
    .head(10)
)
st.dataframe(top_campaigns_table.style.format({"Lead Count": "{:,}"}), use_container_width=True, hide_index=True)

# --- Qualified + Status Tables ---
colC, colD = st.columns([1, 1.3])  # Make pie chart column smaller than table column

colC, colD = st.columns([1, 1.3])  # Keep same column width ratio

colC, colD = st.columns([1, 1.3])  # keep the layout balanced

with colC:
    st.markdown("### Qualified vs Not Qualified")
    qualified_counts = df.groupby("Is Qualified")["Lead 18-Digit ID"].nunique()

    # Create smaller figure
    fig3, ax3 = plt.subplots(figsize=(2, 2))

    # Draw pie chart with labels
    wedges, texts, autotexts = ax3.pie(
        qualified_counts,
        labels=qualified_counts.index,   # <-- add labels back
        autopct=lambda p: f'{p:.1f}%\n({int(p * sum(qualified_counts) / 100)})',
        startangle=90,
        textprops={'fontsize': 8}        # sets base fontsize
    )

    # Adjust percentage/autotext font size
    for autotext in autotexts:
        autotext.set_fontsize(7)

    # Adjust label (Qualified/Not Qualified) font size
    for text in texts:
        text.set_fontsize(8)

    ax3.set_ylabel("")
    plt.tight_layout(pad=0.1)

    st.pyplot(fig3, use_container_width=False)

with colD:
    st.markdown("### Lead Count by Status")
    status_order = ["New", "Working", "Disqualified", "Converted", "Reject - never r.."]
    status_counts = (
        df.groupby("Lead Status")["Lead 18-Digit ID"]
        .nunique()
        .reindex(status_order)
        .dropna()
    )
    status_df = status_counts.reset_index().rename(columns={"Lead 18-Digit ID": "Lead Count"})
    st.dataframe(
        status_df.style.format({"Lead Count": "{:,.0f}"}),
        use_container_width=True,
        hide_index=True
    )


# --- Opportunity Stage Summary ---
st.markdown("### Opportunity Stage Summary")
stage_order = [
    "Discovery", "Qualified", "Evaluation", "Pricing Negotiation",
    "Legal Negotiation", "Proposal", "Closed Won", "Closed Lost", "Unqualified"
]
stage_table = (
    df.groupby("Stage")
    .agg({
        "ARR Delta (converted)": "sum",
        "Lead 18-Digit ID": "nunique"
    })
    .rename(columns={"Lead 18-Digit ID": "Lead Count"})
    .reindex(stage_order)
    .dropna(how='all')
    .reset_index()  # <--- This line adds the Stage column back as a column
)

st.dataframe(
    stage_table.style.format({
        "ARR Delta (converted)": "${:,.0f}",
        "Lead Count": "{:,.0f}"   # force 0 decimal places
    }),
    use_container_width=True,
    hide_index=True
)