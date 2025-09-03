import streamlit as st
import pandas as pd
import plotly.express as px

st.set_page_config(page_title="Risk Analysis Tool", layout="wide")
st.title("Risk Analysis Tool")

# === 1. Load files directly from repo ===
export = pd.read_excel("Export.xlsx")
product_registry = pd.read_excel("Product Registry.xlsx")
mapping_ba = pd.read_excel("Mapping BA.xlsx", usecols=[0, 1], names=["Customer Name", "Alliance"], header=0)
mapping_ia = pd.read_excel("Mapping IA.xlsx", usecols=[0, 1], names=["Customer Name", "Alliance"], header=0)
corridors = pd.read_excel("Corridors.xlsx")
mapping_area = pd.read_excel("Mapping Area.xlsx")

# === 2. Alliance toggle (3 options) ===
alliance_type = st.sidebar.radio("Alliance Mapping", ["Buying Alliance", "International Alliance", "Modern Trade"])

calc = export.copy()

if alliance_type == "Buying Alliance":
    mapping = mapping_ba
    calc = calc.merge(
        mapping,
        how="left",
        left_on="Customer Hierarchy - Customer",
        right_on="Customer Name"
    ).drop(columns=["Customer Name"])

elif alliance_type == "International Alliance":
    mapping = mapping_ia
    calc = calc.merge(
        mapping,
        how="left",
        left_on="Customer Hierarchy - Customer",
        right_on="Customer Name"
    ).drop(columns=["Customer Name"])

else:  # Modern Trade
    calc["Alliance"] = calc["Customer Hierarchy - Customer"].apply(
        lambda x: "Modern Trade" if str(x).strip().lower() == "modern trade" else None
    )

# Exclude rows with NaN in Alliance by default
calc = calc[calc["Alliance"].notna()].copy()

# === 3. Build Calculations ===
# Comparable
calc = calc.merge(
    product_registry[["Product Hierarchy - Product", "Product Hierarchy - Comparable Product"]],
    how="left",
    on="Product Hierarchy - Product"
).rename(columns={"Product Hierarchy - Comparable Product": "Comparable"})

# Category
comp_to_cat = product_registry[[
    "Product Hierarchy - Comparable Product", "Product Hierarchy - Category"
]].drop_duplicates().rename(columns={
    "Product Hierarchy - Comparable Product": "Comparable",
    "Product Hierarchy - Category": "Category"
})
calc = calc.merge(comp_to_cat, how="left", on="Comparable")

# Mapping Area
calc = calc.merge(
    mapping_area.rename(columns={"Country": "Sellin Country Hierarchy - Country"}),
    how="left",
    on="Sellin Country Hierarchy - Country"
)

# Prepare corridors lookup
corridors_lookup = corridors[["Country", "Attribute", "Corridor Min", "Corridor Max"]]


# === Helper function to recalculate after filters ===
def recalculate(df, flag):
    df = df.copy()

    # Comparable Volumes & Prices
    df["Comparable Volumes"] = df.groupby(
        ["Comparable", "Sellin Country Hierarchy - Country", "Customer Hierarchy - Customer"]
    )["Volumes [q]"].transform("sum")

    df["Weighted Price Sum"] = df["3Net Price [EUR/kg]"] * df["Volumes [q]"]
    grouped_price = df.groupby(
        ["Comparable", "Sellin Country Hierarchy - Country", "Customer Hierarchy - Customer"]
    )["Weighted Price Sum"].transform("sum")
    df["Comparable Price"] = grouped_price / df["Comparable Volumes"]

    # Min Price + Min Country + Min Customer (recalculated each time)
    df["Min Price"] = df.groupby(["Comparable", "Alliance"])["Comparable Price"].transform("min")

    min_price_country = df.loc[
        df.groupby(["Comparable", "Alliance"])["Comparable Price"].idxmin(),
        ["Comparable", "Alliance", "Sellin Country Hierarchy - Country"]
    ].rename(columns={"Sellin Country Hierarchy - Country": "Generating Country"})

    min_price_customer = df.loc[
        df.groupby(["Comparable", "Alliance"])["Comparable Price"].idxmin(),
        ["Comparable", "Alliance", "Customer Hierarchy - Customer"]
    ].rename(columns={"Customer Hierarchy - Customer": "Generating Customer"})

    df = df.drop(columns=["Generating Country", "Generating Customer"], errors="ignore")
    df = df.merge(min_price_country, how="left", on=["Comparable", "Alliance"])
    df = df.merge(min_price_customer, how="left", on=["Comparable", "Alliance"])

    # Corridors - join twice
    # Max Corridor by Suffering Country
    df = df.merge(
        corridors_lookup[["Country", "Attribute", "Corridor Max"]].rename(columns={"Corridor Max": "Max Corridor"}),
        how="left",
        left_on=["Sellin Country Hierarchy - Country", "Category"],
        right_on=["Country", "Attribute"]
    ).drop(columns=["Country", "Attribute"], errors="ignore")

    # Min Corridor by Generating Country
    df = df.merge(
        corridors_lookup[["Country", "Attribute", "Corridor Min"]].rename(columns={"Corridor Min": "Min Corridor"}),
        how="left",
        left_on=["Generating Country", "Category"],
        right_on=["Country", "Attribute"]
    ).drop(columns=["Country", "Attribute"], errors="ignore")

    # Calculations
    df["Operating Corridor"] = df["Max Corridor"] / df["Min Corridor"]
    df["Net Sales"] = df["Comparable Price"] * df["Volumes [q]"]
    df["Min Price Net Sales"] = df["Min Price"] * df["Volumes [q]"]
    df["Risk"] = (df["Net Sales"] - df["Min Price Net Sales"] * df["Operating Corridor"]).clip(lower=0).fillna(0)
    df["% Risk"] = df["Risk"] / df["Net Sales"]

    # Rename for display
    df = df.rename(columns={
        "Sellin Country Hierarchy - Country": "Suffering Country",
        "Customer Hierarchy - Customer": "Suffering Customer"
    })

    return df


# === 4. Sidebar filters ===
st.sidebar.header("Filters")
areas = st.sidebar.multiselect("Areas", sorted(calc["Area"].dropna().unique()))
paesi = st.sidebar.multiselect("Countries", sorted(calc["Sellin Country Hierarchy - Country"].dropna().unique()))
categorie = st.sidebar.multiselect("Categories", sorted(calc["Category"].dropna().unique()))
alliances_list = sorted([x for x in calc["Alliance"].dropna().unique()])
alleanze = st.sidebar.multiselect("Alliance", alliances_list)
flag = st.sidebar.radio("Risk Type", ["suffered", "generated"])

df = calc.copy()
if areas:
    df = df[df["Area"].isin(areas)]
if paesi:
    df = df[df["Sellin Country Hierarchy - Country"].isin(paesi)]
if categorie:
    df = df[df["Category"].isin(categorie)]
if alleanze:
    df = df[df["Alliance"].isin(alleanze)]

df = recalculate(df, flag)

# === 5. Aggregated by Country ===
if flag == "suffered":
    group_col = "Suffering Country"
else:
    group_col = "Generating Country"

agg = df.groupby(group_col).agg({
    "Net Sales": "sum",
    "Risk": "sum"
}).reset_index()
agg["% Risk"] = agg["Risk"] / agg["Net Sales"]

# Totals in title
total_risk = agg["Risk"].sum()
total_net_sales = agg["Net Sales"].sum()
total_pct = total_risk / total_net_sales if total_net_sales else 0

st.subheader("Aggregated Risk by Country")
st.markdown(f"**Total Risk: {total_risk:,.0f} | Total Net Sales: {total_net_sales:,.0f} | % Risk: {total_pct:.2%}**")
st.dataframe(agg.reset_index(drop=True).style.format({"Net Sales": "{:,.0f}", "Risk": "{:,.0f}", "% Risk": "{:.2%}"}))

# === Bar chart ===
fig = px.bar(
    agg,
    x=group_col,
    y=["Net Sales", "Risk"],
    barmode="overlay",
    title="Net Sales vs Risk by Country",
    color_discrete_map={
        "Net Sales": "steelblue",
        "Risk": "crimson"
    }
)
fig.update_traces(opacity=0.8)
st.plotly_chart(fig, use_container_width=True)


# === 6. Aggregated by Country + Category ===
agg2 = df.groupby([group_col, "Category"]).agg({
    "Net Sales": "sum",
    "Risk": "sum"
}).reset_index()
agg2["% Risk"] = agg2["Risk"] / agg2["Net Sales"]

# Totals in title
total_risk2 = agg2["Risk"].sum()
total_net_sales2 = agg2["Net Sales"].sum()
total_pct2 = total_risk2 / total_net_sales2 if total_net_sales2 else 0

st.subheader("Aggregated Risk by Country and Category")
st.markdown(f"**Total Risk: {total_risk2:,.0f} | Total Net Sales: {total_net_sales2:,.0f} | % Risk: {total_pct2:.2%}**")
st.dataframe(agg2.reset_index(drop=True).style.format({"Net Sales": "{:,.0f}", "Risk": "{:,.0f}", "% Risk": "{:.2%}"}))


# === 7. Detailed Table ===
st.subheader("Detailed Risk Table")

# Show all columns for sense check
all_cols = df.columns.tolist()
st.dataframe(df[all_cols].reset_index(drop=True).style.format({
    "Comparable Price": "{:,.2f}",
    "3Net Price [EUR/kg]": "{:,.2f}",
    "Min Price": "{:,.2f}",
    "Net Sales": "{:,.0f}",
    "Min Price Net Sales": "{:,.0f}",
    "Risk": "{:,.0f}",
    "% Risk": "{:.2%}",
    "Operating Corridor": "{:,.2f}",
    "Comparable Volumes": "{:,.0f}"
}))
