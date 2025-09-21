import streamlit as st
import pandas as pd
import plotly.express as px
from pathlib import Path

# ------------------------- Page Setup -------------------------
st.set_page_config(page_title="Lebanon External Finance Dashboard", layout="wide")
st.title("Lebanon External Finance – Interactive Dashboard")

st.markdown("""
This dashboard visualizes Lebanon's external finance indicators and lets you explore trends, composition, and risk signals.
Upload a CSV (or keep **External Debt Dataset.csv** in this folder). Expected columns: **refPeriod**, **Indicator Code**, **Value**.
""")

# ------------------------- Friendly Names -------------------------
# Prefer the full mapping file; fall back to a minimal internal map.
MAP_PATH = Path("debt_code_mapping.csv")


def load_mapping():
    if MAP_PATH.exists():
        m = pd.read_csv(MAP_PATH)
        return dict(zip(m["Indicator Code"], m["Friendly Name"]))
    return _fallback_map

friendly = load_mapping()
name_for = lambda code: friendly.get(code, code)

# ------------------------- Data Loading -------------------------
DEFAULT_FILE = Path("External Debt Dataset.csv")
uploaded = st.file_uploader("Upload CSV", type=["csv"])

@st.cache_data
def read_csv_any(src):
    return pd.read_csv(src)

def normalize_columns(df: pd.DataFrame) -> pd.DataFrame:
    ren = {}
    if "refPeriod" not in df.columns:
        for alt in ["Year", "year", "RefPeriod", "refperiod"]:
            if alt in df.columns: ren[alt] = "refPeriod"; break
    if "Indicator Code" not in df.columns:
        for alt in ["Indicator_Code","IndicatorCode","indicator_code"]:
            if alt in df.columns: ren[alt] = "Indicator Code"; break
    if "Value" not in df.columns:
        for alt in ["value","VAL","Amount"]:
            if alt in df.columns: ren[alt] = "Value"; break
    if ren: df = df.rename(columns=ren)

    required = {"refPeriod","Indicator Code","Value"}
    missing = required - set(df.columns)
    if missing:
        raise ValueError(f"Missing required columns: {missing} (found: {list(df.columns)})")

    df["refPeriod"] = pd.to_numeric(df["refPeriod"], errors="coerce")
    df["Value"] = pd.to_numeric(df["Value"], errors="coerce")
    return df.dropna(subset=["refPeriod","Value"])

if uploaded is not None:
    df_raw = read_csv_any(uploaded)
elif DEFAULT_FILE.exists():
    st.info(f"Using local file: {DEFAULT_FILE.name}")
    df_raw = read_csv_any(DEFAULT_FILE)
else:
    st.warning("Upload a CSV above or place one named **External Debt Dataset.csv** in this folder.")
    st.stop()

try:
    df = normalize_columns(df_raw)
except Exception as e:
    st.error(str(e)); st.stop()

# ------------------------- Sidebar Controls -------------------------
st.sidebar.header("For full dashboard")
years = sorted(df["refPeriod"].unique())
yr_min, yr_max = int(min(years)), int(max(years))
year_range = st.sidebar.slider("Year range", min_value=yr_min, max_value=yr_max, value=(yr_min, yr_max))
logy = st.sidebar.checkbox("Log scale (y-axis)", value=False)

all_codes = sorted(df["Indicator Code"].dropna().unique().tolist())

RECOMMENDED_LINE = ["DT.DOD.DECT.CD"]
default_present_line = [c for c in RECOMMENDED_LINE if c in all_codes]
if not default_present_line:
    default_present_line = all_codes[:2]  # fallback

RECOMMENDED_BAR = ["DT.TDS.DECT.GN.ZS", "DT.DOD.DSTC.IR.ZS"]
default_present_bar = [c for c in RECOMMENDED_BAR if c in all_codes]
if not default_present_bar:
    default_present_bar = all_codes[:2]  # fallback    

# ---- Separate filters for line and bar ----
st.sidebar.markdown("### Line chart filters")
line_codes = st.sidebar.multiselect(
    "Indicators to trend (line)",
    options=all_codes,
    default=default_present_line,
    format_func=name_for,
)

st.sidebar.markdown("### Bar chart filters")
bar_codes = st.sidebar.multiselect(
    "Indicators to compare (bar)",
    options=all_codes,
    default=default_present_bar,
    format_func=name_for,
)
bar_year_options = [int(y) for y in years if year_range[0] <= y <= year_range[1]]
if not bar_year_options:
    bar_year_options = [yr_min]
bar_year = st.sidebar.select_slider("Bar chart year", options=sorted(bar_year_options), value=sorted(bar_year_options)[-1])

# Extra interactive features (kept from your original)
st.sidebar.markdown("Advanced filters")
base_year = st.sidebar.select_slider("Index base year (=100)", options=sorted(set(df["refPeriod"].astype(int))), value=yr_min)
x_code = st.sidebar.selectbox("Scatter X", options=all_codes, index=0, format_func=name_for)
y_code = st.sidebar.selectbox("Scatter Y", options=all_codes, index=min(1, len(all_codes)-1), format_func=name_for)
num_code = st.sidebar.selectbox("Ratio numerator", options=all_codes, index=0, format_func=name_for)
den_code = st.sidebar.selectbox("Ratio denominator", options=all_codes, index=min(1, len(all_codes)-1), format_func=name_for)
roll_win = st.sidebar.slider("Rolling correlation window (years)", 3, 10, 5)

# ------------------------- Filtered data -------------------------
fdf = df[(df["refPeriod"] >= year_range[0]) & (df["refPeriod"] <= year_range[1])].copy()
fdf["Label"] = fdf["Indicator Code"].map(name_for)

# ------------------------- LINE CHART -------------------------
st.subheader("Trends over time (line)")
line_df = fdf[fdf["Indicator Code"].isin(line_codes)].copy()
if not line_df.empty:
    fig_line = px.line(
        line_df, x="refPeriod", y="Value", color="Label",
        labels={"refPeriod":"Year","Value":"Value"},
        title="Selected indicators across time"
    )
    if logy: fig_line.update_yaxes(type="log")
    st.plotly_chart(fig_line, use_container_width=True)
else:
    st.info("Pick at least one indicator in the **line** chart controls.")

# ------------------------- BAR CHART -------------------------
st.subheader("Year snapshot (bar)")
bar_df = fdf[(fdf["refPeriod"] == bar_year) & (fdf["Indicator Code"].isin(bar_codes))].copy()
if not bar_df.empty:
    fig_bar = px.bar(
        bar_df.sort_values("Value", ascending=False),
        x="Label", y="Value",
        labels={"Label":"Indicator","Value":"Value"},
        title=f"Selected indicators in {bar_year}"
    )
    if logy: fig_bar.update_yaxes(type="log")
    st.plotly_chart(fig_bar, use_container_width=True)
else:
    st.info("No data for the chosen **bar** indicators in the selected year. Try a different year or indicators.")

# ------------------------- SCATTER with OLS -------------------------
wide_scatter = (fdf[fdf["Indicator Code"].isin([x_code, y_code])]
                .pivot_table(index="refPeriod", columns="Indicator Code", values="Value")
                .dropna())
if not wide_scatter.empty:
    fig_sc = px.scatter(
        wide_scatter.reset_index(), x=x_code, y=y_code, hover_name="refPeriod",
        trendline="ols",
        labels={x_code: name_for(x_code), y_code: name_for(y_code)},
        title=f"Relationship: {name_for(y_code)} vs {name_for(x_code)}"
    )
    st.plotly_chart(fig_sc, use_container_width=True)

# ------------------------- Indexed to 100 -------------------------
idx_df = fdf[fdf["Indicator Code"].isin(line_codes)].copy()
if not idx_df.empty and base_year in idx_df["refPeriod"].unique():
    base = (idx_df[idx_df["refPeriod"] == base_year].set_index("Indicator Code")["Value"])
    idx_df["Index_100"] = idx_df.apply(
        lambda r: (r["Value"] / base.get(r["Indicator Code"], float("nan"))) * 100, axis=1
    )
    idx_df = idx_df.dropna(subset=["Index_100"])
    fig_idx = px.line(
        idx_df, x="refPeriod", y="Index_100", color="Label",
        title=f"Relative Growth – Indexed to 100 in {base_year}",
        labels={"refPeriod":"Year","Index_100":"Index (=100 at base year)"}
    )
    st.plotly_chart(fig_idx, use_container_width=True)

# ------------------------- Ratio line -------------------------
wide_ratio = (fdf[fdf["Indicator Code"].isin([num_code, den_code])]
              .pivot_table(index="refPeriod", columns="Indicator Code", values="Value")
              .dropna())
if not wide_ratio.empty:
    wide_ratio["ratio"] = wide_ratio[num_code] / wide_ratio[den_code]
    fig_ratio = px.line(
        wide_ratio.reset_index(), x="refPeriod", y="ratio",
        title=f"Ratio: {name_for(num_code)} / {name_for(den_code)}",
        labels={"refPeriod":"Year","ratio":"Ratio"}
    )
    if logy: fig_ratio.update_yaxes(type="log")
    st.plotly_chart(fig_ratio, use_container_width=True)

# ------------------------- Rolling correlation -------------------------
corr_wide = (fdf[fdf["Indicator Code"].isin([x_code, y_code])]
             .pivot_table(index="refPeriod", columns="Indicator Code", values="Value")
             .dropna())
if not corr_wide.empty and len(corr_wide) >= roll_win:
    corr_series = corr_wide[x_code].rolling(roll_win).corr(corr_wide[y_code])
    corr_df = corr_series.reset_index()
    corr_df.columns = ["refPeriod", "Correlation"]
    fig_rc = px.line(
        corr_df, x="refPeriod", y="Correlation",
        title=f"Rolling {roll_win}-Year Correlation: {name_for(x_code)} vs {name_for(y_code)}",
        labels={"refPeriod":"Year","Correlation":"Correlation"}
    )
    fig_rc.add_hline(y=0, line_dash="dash")
    st.plotly_chart(fig_rc, use_container_width=True)

# ------------------------- Reading Guide -------------------------
with st.expander("How to read this page"):
    st.markdown("""
- **Line chart:** choose indicators in *Line chart controls* (top-left). Log scale helps if magnitudes differ.
- **Bar chart:** choose indicators in *Bar chart controls* and pick the **Bar chart year**.
- **Scatter:** explores relationships with an OLS trendline.
- **Indexed to 100:** compares growth regardless of units.
- **Ratio:** condenses two series into a single stress metric (such as short-term debt/reserves).
- **Rolling correlation:** reveals regime shifts (relationship changing sign).
""")
