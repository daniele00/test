import streamlit as st
import pandas as pd

st.set_page_config(page_title="Risk Analysis Tool", layout="wide")
st.title("📊 Risk Analysis Tool")

# === Caricamento file direttamente dal repo ===
export = pd.read_excel("Export.xlsx")
product_registry = pd.read_excel("Product Registry.xlsx")
mappatura = pd.read_excel("Mappatura.xlsx", usecols=[0, 1], names=["Customer Name", "Buying Alliance"], header=0)
corridors = pd.read_excel("Corridors.xlsx")

# === 1. Upload dei file ===
st.sidebar.header("Carica i file necessari")
export_file = st.sidebar.file_uploader("Export.xlsx", type="xlsx")
product_file = st.sidebar.file_uploader("Product Registry.xlsx", type="xlsx")
mappatura_file = st.sidebar.file_uploader("Mappatura.xlsx", type="xlsx")
corridors_file = st.sidebar.file_uploader("Corridors.xlsx", type="xlsx")

if export_file and product_file and mappatura_file and corridors_file:
    # === 2. Lettura file ===
    export = pd.read_excel(export_file)
    product_registry = pd.read_excel(product_file)
    mappatura = pd.read_excel(mappatura_file, usecols=[0, 1], names=["Customer Name", "Buying Alliance"], header=0)
    corridors = pd.read_excel(corridors_file)

    # === 3. Costruzione Calculations ===
    calc = export.copy()

    # Comparable
    calc = calc.merge(
        product_registry[["Product Hierarchy - Product", "Product Hierarchy - Comparable Product"]],
        how="left",
        on="Product Hierarchy - Product"
    ).rename(columns={"Product Hierarchy - Comparable Product": "Comparable"})

    # Buying Alliance
    calc = calc.merge(
        mappatura,
        how="left",
        left_on="Customer Hierarchy - Customer",
        right_on="Customer Name"
    ).drop(columns=["Customer Name"])

    # Category
    comp_to_cat = product_registry[[
        "Product Hierarchy - Comparable Product", "Product Hierarchy - Category"
    ]].drop_duplicates().rename(columns={
        "Product Hierarchy - Comparable Product": "Comparable",
        "Product Hierarchy - Category": "Category"
    })
    calc = calc.merge(comp_to_cat, how="left", on="Comparable")

    # Corridors
    corridors_lookup = corridors[["Country", "Attribute", "Corridor Min", "Corridor Max"]].rename(columns={
        "Corridor Min": "Min Corridor",
        "Corridor Max": "Max Corridor"
    })
    calc = calc.merge(
        corridors_lookup,
        how="left",
        left_on=["Sellin Country Hierarchy - Country", "Category"],
        right_on=["Country", "Attribute"]
    ).drop(columns=["Country", "Attribute"])

    # Calcoli
    calc["Comparable Volumes"] = calc.groupby(
        ["Comparable", "Sellin Country Hierarchy - Country", "Customer Hierarchy - Customer"]
    )["Volumes [q]"].transform("sum")

    calc["Weighted Price Sum"] = calc["3Net Price [EUR/kg]"] * calc["Volumes [q]"]
    grouped_price = calc.groupby(
        ["Comparable", "Sellin Country Hierarchy - Country", "Customer Hierarchy - Customer"]
    )["Weighted Price Sum"].transform("sum")
    calc["Comparable Price"] = grouped_price / calc["Comparable Volumes"]

    calc["Min Price"] = calc.groupby(["Comparable", "Buying Alliance"])["Comparable Price"].transform("min")

    calc["Operating Corridor"] = calc["Max Corridor"] / calc["Min Corridor"]
    calc["Net Sales"] = calc["Comparable Price"] * calc["Volumes [q]"]
    calc["Min Price Net Sales"] = calc["Min Price"] * calc["Volumes [q]"]
    calc["Risk"] = (calc["Net Sales"] - calc["Min Price Net Sales"] * calc["Operating Corridor"]).clip(lower=0).fillna(0)
    calc["% Risk"] = calc["Risk"] / calc["Net Sales"]

    # === 4. Filtri ===
    st.sidebar.subheader("Filtri")
    paesi = st.sidebar.multiselect("Paesi", sorted(calc["Sellin Country Hierarchy - Country"].dropna().unique()))
    categorie = st.sidebar.multiselect("Categorie", sorted(calc["Category"].dropna().unique()))
    alleanze = st.sidebar.multiselect("Buying Alliance", sorted(calc["Buying Alliance"].dropna().unique()))
    flag = st.sidebar.radio("Tipo di Rischio", ["sofferto", "generato"])

    df = calc.copy()
    if paesi: df = df[df["Sellin Country Hierarchy - Country"].isin(paesi)]
    if categorie: df = df[df["Category"].isin(categorie)]
    if alleanze: df = df[df["Buying Alliance"].isin(alleanze)]

    # === 5. Tabella aggregata ===
    if flag == "sofferto":
        group_col = "Sellin Country Hierarchy - Country"
    else:
        group_col = "Min Price Country"

    agg = df.groupby(group_col).agg({
        "Net Sales": "sum",
        "Risk": "sum"
    }).reset_index()
    agg["% Risk"] = agg["Risk"] / agg["Net Sales"]

    grand_total = pd.DataFrame({
        group_col: ["Grand Total"],
        "Net Sales": [agg["Net Sales"].sum()],
        "Risk": [agg["Risk"].sum()],
        "% Risk": [agg["Risk"].sum() / agg["Net Sales"].sum() if agg["Net Sales"].sum() else 0]
    })
    agg = pd.concat([agg, grand_total], ignore_index=True)

    st.subheader("📊 Rischio Aggregato per Paese")
    st.dataframe(agg.style.format({"Net Sales": "{:,.0f}", "Risk": "{:,.0f}", "% Risk": "{:.2%}"}))

    # === 6. Tabella di dettaglio ===
    st.subheader("📋 Dettaglio Rischio")

    dettaglio_cols = [
        "Sellin Country Hierarchy - Country",
        "Min Price Country",
        "Customer Hierarchy - Customer",
        "Category",
        "Comparable",
        "Comparable Price",
        "3Net Price [EUR/kg]",
        "Min Price",
        "Net Sales",
        "Risk",
        "% Risk"
    ]

    for col in dettaglio_cols:
        if col not in df.columns:
            df[col] = None

    st.dataframe(df[dettaglio_cols].style.format({
        "Comparable Price": "{:,.2f}",
        "3Net Price [EUR/kg]": "{:,.2f}",
        "Min Price": "{:,.2f}",
        "Net Sales": "{:,.0f}",
        "Risk": "{:,.0f}",
        "% Risk": "{:.2%}"
    }))
else:
    st.info("⬅️ Carica tutti e 4 i file Excel per iniziare")
