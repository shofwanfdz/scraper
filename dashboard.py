"""
Scraping Dashboard - Complete Interactive Analytics
Supports both Blibli and Shopee data.
Run: streamlit run dashboard.py
"""
import streamlit as st
import pandas as pd
import plotly.express as px
import glob
import os
import re

# ============================================================
# PAGE CONFIG
# ============================================================
st.set_page_config(
    page_title="Scraping Dashboard",
    page_icon="🕷️",
    layout="wide",
    initial_sidebar_state="expanded",
)

# ============================================================
# HELPERS
# ============================================================

KNOWN_BRANDS = [
    "ASUS", "HP", "Lenovo", "Acer", "Dell", "MSI", "Apple", "MacBook",
    "Samsung", "Toshiba", "Axioo", "Polytron", "Infinix", "Realme",
    "Xiaomi", "OPPO", "Vivo", "Huawei", "Sony", "LG",
    "Adidas", "Nike", "Puma", "New Balance", "Asics", "Converse",
    "Logitech", "Razer", "SteelSeries", "Corsair",
    "Canon", "Nikon", "Fujifilm", "Philips", "Panasonic", "Sharp",
]


def extract_brand(name):
    if not name or not isinstance(name, str):
        return "Lainnya"
    for brand in KNOWN_BRANDS:
        if brand.upper() in name.upper():
            if brand.upper() in ("MACBOOK",):
                return "Apple"
            return brand.upper() if len(brand) <= 4 else brand
    return "Lainnya"


@st.cache_data
def load_excel(filepath):
    df = pd.read_excel(filepath, sheet_name="Products")
    if "harga_angka" in df.columns:
        df["harga_angka"] = pd.to_numeric(df["harga_angka"], errors="coerce")
    elif "harga" in df.columns:
        df["harga_angka"] = df["harga"].apply(
            lambda x: int(re.sub(r"[^\d]", "", str(x))) if pd.notna(x) and re.search(r"\d", str(x)) else None)
        df["harga_angka"] = pd.to_numeric(df["harga_angka"], errors="coerce")
    if "terjual" in df.columns:
        df["terjual"] = pd.to_numeric(df["terjual"], errors="coerce")
    if "rating" in df.columns:
        df["rating"] = pd.to_numeric(df["rating"], errors="coerce")
    if "brand" not in df.columns:
        df["brand"] = df["nama_produk"].apply(extract_brand)
    if "harga_sebelum_diskon" in df.columns:
        df["harga_asli_angka"] = df["harga_sebelum_diskon"].apply(
            lambda x: int(re.sub(r"[^\d]", "", str(x))) if pd.notna(x) and re.search(r"\d", str(x)) else None)
        df["harga_asli_angka"] = pd.to_numeric(df["harga_asli_angka"], errors="coerce")
        mask = df["harga_angka"].notna() & df["harga_asli_angka"].notna() & (df["harga_asli_angka"] > 0)
        df["diskon_persen"] = None
        df.loc[mask, "diskon_persen"] = round(
            (1 - df.loc[mask, "harga_angka"] / df.loc[mask, "harga_asli_angka"]) * 100, 1)
        df["diskon_persen"] = pd.to_numeric(df["diskon_persen"], errors="coerce")
    else:
        df["diskon_persen"] = None
    return df


# ============================================================
# SIDEBAR - FILE & FILTERS
# ============================================================

st.sidebar.title("\U0001f577\ufe0f Scraping Dashboard")
st.sidebar.markdown("---")

# Load files from BOTH marketplaces
hasil_blibli = [f for f in glob.glob("hasil/blibli/*.xlsx") if not os.path.basename(f).startswith("~")]
hasil_shopee = [f for f in glob.glob("hasil/shopee/*.xlsx") if not os.path.basename(f).startswith("~")]
excel_files = sorted(hasil_blibli + hasil_shopee, key=os.path.getmtime, reverse=True)

if not excel_files:
    st.error("\u274c Tidak ada file Excel di folder hasil/")
    st.stop()

file_options = {os.path.basename(f): f for f in excel_files}
selected_file = st.sidebar.selectbox("📁 Pilih File Data", list(file_options.keys()))
df = load_excel(file_options[selected_file])

st.sidebar.markdown("---")
st.sidebar.subheader("🔍 Filter")

# Brand
all_brands = sorted(df["brand"].dropna().unique().tolist())
selected_brands = st.sidebar.multiselect("Brand", all_brands, default=all_brands)

# Price
min_p = int(df["harga_angka"].min()) if df["harga_angka"].notna().any() else 0
max_p = int(df["harga_angka"].max()) if df["harga_angka"].notna().any() else 100000000
price_range = st.sidebar.slider("Rentang Harga", min_p, max_p, (min_p, max_p), step=500000, format="Rp%d")

# Rating
min_rating = st.sidebar.slider("Rating Minimum", 0.0, 5.0, 0.0, 0.5)

# Seller
if "penjual" in df.columns:
    all_sellers = sorted(df["penjual"].dropna().unique().tolist())
    selected_sellers = st.sidebar.multiselect("Penjual", all_sellers, default=all_sellers)
else:
    selected_sellers = []

# Location
if "kota" in df.columns:
    all_kota = sorted(df["kota"].dropna().unique().tolist())
    selected_kota = st.sidebar.multiselect("Lokasi", all_kota, default=all_kota)
else:
    selected_kota = []

# Apply filters
df_f = df.copy()
df_f = df_f[df_f["brand"].isin(selected_brands)]
df_f = df_f[(df_f["harga_angka"] >= price_range[0]) & (df_f["harga_angka"] <= price_range[1])]
if min_rating > 0 and "rating" in df_f.columns:
    df_f = df_f[df_f["rating"] >= min_rating]
if selected_sellers and "penjual" in df_f.columns:
    df_f = df_f[df_f["penjual"].isin(selected_sellers)]
if selected_kota and "kota" in df_f.columns:
    df_f = df_f[df_f["kota"].isin(selected_kota)]

st.sidebar.markdown("---")
st.sidebar.metric("Produk Ditampilkan", f"{len(df_f)} / {len(df)}")

# Detect marketplace
marketplace_name = "Shopee" if "shopee" in selected_file.lower() else "Blibli"

# Download
csv = df_f.to_csv(index=False).encode("utf-8")
st.sidebar.download_button("📥 Download CSV", csv, f"{marketplace_name.lower()}_filtered.csv", "text/csv")


# ============================================================
# MAIN - TABS
# ============================================================

st.title(f"🕷️ {marketplace_name} Scraping Dashboard")
st.caption(f"File: {selected_file} | Showing: {len(df_f)} produk")

# Key Metrics
c1, c2, c3, c4, c5, c6 = st.columns(6)
c1.metric("Total Produk", len(df_f))
c2.metric("Avg Harga", f"Rp{df_f['harga_angka'].mean():,.0f}" if df_f["harga_angka"].notna().any() else "N/A")
c3.metric("Min Harga", f"Rp{df_f['harga_angka'].min():,.0f}" if df_f["harga_angka"].notna().any() else "N/A")
c4.metric("Max Harga", f"Rp{df_f['harga_angka'].max():,.0f}" if df_f["harga_angka"].notna().any() else "N/A")
c5.metric("Avg Rating", f"{df_f['rating'].mean():.2f}" if "rating" in df_f.columns and df_f["rating"].notna().any() else "N/A")
c6.metric("Total Terjual", f"{int(df_f['terjual'].sum()):,}" if "terjual" in df_f.columns and df_f["terjual"].notna().any() else "N/A")

st.markdown("---")

# Tabs
tab1, tab2, tab3, tab4, tab5, tab6, tab7, tab8 = st.tabs([
    "📊 Harga", "🏪 Seller", "📍 Lokasi", "📈 Penjualan", "🏷️ Diskon", "🏷️ Brand", "💎 Best Value", "💡 Rekomendasi"
])

# ============================================================
# TAB 1: ANALISIS HARGA
# ============================================================
with tab1:
    st.header("📊 Analisis Harga")

    col1, col2 = st.columns(2)
    with col1:
        st.subheader("Distribusi Harga")
        fig = px.histogram(df_f, x="harga_angka", nbins=15, labels={"harga_angka": "Harga (Rp)"},
                           color_discrete_sequence=["#1F4E79"])
        fig.update_layout(showlegend=False, height=350)
        st.plotly_chart(fig, use_container_width=True)

    with col2:
        st.subheader("Segmentasi Harga")
        harga = df_f["harga_angka"].dropna()
        segs = {"Budget (<5jt)": int((harga < 5e6).sum()), "Mid (5-10jt)": int(((harga >= 5e6) & (harga < 10e6)).sum()),
                "High (10-20jt)": int(((harga >= 10e6) & (harga < 20e6)).sum()), "Premium (>20jt)": int((harga >= 20e6).sum())}
        segs = {k: v for k, v in segs.items() if v > 0}
        fig = px.pie(values=list(segs.values()), names=list(segs.keys()),
                     color_discrete_sequence=["#5B9BD5", "#ED7D31", "#A5A5A5", "#FFC000"])
        fig.update_traces(textposition="inside", textinfo="percent+label")
        fig.update_layout(height=350)
        st.plotly_chart(fig, use_container_width=True)

    # Top Termurah & Termahal
    col3, col4 = st.columns(2)
    with col3:
        st.subheader("Top 10 Termurah")
        cheap = df_f.nsmallest(10, "harga_angka")[["nama_produk", "harga", "brand", "penjual"]].reset_index(drop=True)
        st.dataframe(cheap, use_container_width=True, hide_index=True)
    with col4:
        st.subheader("Top 10 Termahal")
        exp = df_f.nlargest(10, "harga_angka")[["nama_produk", "harga", "brand", "penjual"]].reset_index(drop=True)
        st.dataframe(exp, use_container_width=True, hide_index=True)

    # Harga per Lokasi
    st.subheader("Harga Rata-rata per Lokasi")
    if "kota" in df_f.columns:
        avg_loc = df_f.groupby("kota")["harga_angka"].agg(["mean", "min", "max", "count"]).sort_values("mean", ascending=False).reset_index()
        avg_loc.columns = ["Kota", "Rata-rata", "Min", "Max", "Produk"]
        fig = px.bar(avg_loc, x="Rata-rata", y="Kota", orientation="h",
                     color_discrete_sequence=["#2E75B6"], labels={"Rata-rata": "Harga Rata-rata (Rp)"})
        fig.update_layout(height=350, yaxis=dict(autorange="reversed"))
        st.plotly_chart(fig, use_container_width=True)
        st.dataframe(avg_loc, use_container_width=True, hide_index=True)

# ============================================================
# TAB 2: ANALISIS SELLER
# ============================================================
with tab2:
    st.header("🏪 Analisis Seller")

    col1, col2 = st.columns(2)
    with col1:
        st.subheader("Top 10 Seller (Jumlah Produk)")
        seller_counts = df_f["penjual"].value_counts().head(10)
        fig = px.bar(x=seller_counts.values, y=seller_counts.index, orientation="h",
                     labels={"x": "Jumlah Produk", "y": "Seller"}, color_discrete_sequence=["#2E75B6"])
        fig.update_layout(height=400, yaxis=dict(autorange="reversed"))
        st.plotly_chart(fig, use_container_width=True)

    with col2:
        st.subheader("Distribusi Tipe Seller")
        flagship = int(df_f["penjual"].str.contains("Flagship|Official|Blibli", case=False, na=False).sum())
        individu = int((df_f["penjual"] == "Seller Individu").sum())
        regular = len(df_f) - flagship - individu
        tipe_data = {"Flagship/Official": flagship, "Regular": regular, "Individu": individu}
        tipe_data = {k: v for k, v in tipe_data.items() if v > 0}
        fig = px.pie(values=list(tipe_data.values()), names=list(tipe_data.keys()),
                     color_discrete_sequence=["#4472C4", "#ED7D31", "#A5A5A5"])
        fig.update_traces(textposition="inside", textinfo="percent+label+value")
        fig.update_layout(height=400)
        st.plotly_chart(fig, use_container_width=True)

    col3, col4 = st.columns(2)
    with col3:
        st.subheader("Rata-rata Rating per Seller")
        if "rating" in df_f.columns:
            avg_rat = df_f.groupby("penjual")["rating"].mean().sort_values(ascending=False).head(10)
            fig = px.bar(x=avg_rat.values, y=avg_rat.index, orientation="h",
                         labels={"x": "Avg Rating", "y": "Seller"}, color_discrete_sequence=["#FFC000"])
            fig.update_layout(height=400, yaxis=dict(autorange="reversed"))
            st.plotly_chart(fig, use_container_width=True)

    with col4:
        st.subheader("Seller Total Penjualan Tertinggi")
        if "terjual" in df_f.columns and df_f["terjual"].notna().any():
            seller_sales = df_f.groupby("penjual")["terjual"].sum().sort_values(ascending=False).head(10)
            fig = px.bar(x=seller_sales.values, y=seller_sales.index, orientation="h",
                         labels={"x": "Total Terjual", "y": "Seller"}, color_discrete_sequence=["#70AD47"])
            fig.update_layout(height=400, yaxis=dict(autorange="reversed"))
            st.plotly_chart(fig, use_container_width=True)

# ============================================================
# TAB 3: ANALISIS LOKASI
# ============================================================
with tab3:
    st.header("📍 Analisis Lokasi")

    col1, col2 = st.columns(2)
    with col1:
        st.subheader("Distribusi Produk per Kota")
        kota_counts = df_f["kota"].value_counts().head(10)
        fig = px.bar(x=kota_counts.values, y=kota_counts.index, orientation="h",
                     labels={"x": "Jumlah Produk", "y": "Kota"}, color_discrete_sequence=["#70AD47"])
        fig.update_layout(height=400, yaxis=dict(autorange="reversed"))
        st.plotly_chart(fig, use_container_width=True)

    with col2:
        st.subheader("Seller Unik per Kota")
        if "penjual" in df_f.columns:
            kota_seller = df_f.groupby("kota")["penjual"].nunique().sort_values(ascending=False).head(10)
            fig = px.bar(x=kota_seller.values, y=kota_seller.index, orientation="h",
                         labels={"x": "Jumlah Seller", "y": "Kota"}, color_discrete_sequence=["#9B57A0"])
            fig.update_layout(height=400, yaxis=dict(autorange="reversed"))
            st.plotly_chart(fig, use_container_width=True)

    st.subheader("Detail Harga per Kota")
    detail_kota = df_f.groupby("kota")["harga_angka"].agg(["count", "mean", "min", "max"]).sort_values("mean", ascending=False).reset_index()
    detail_kota.columns = ["Kota", "Produk", "Rata-rata", "Termurah", "Termahal"]
    detail_kota["Rata-rata"] = detail_kota["Rata-rata"].apply(lambda x: f"Rp{x:,.0f}")
    detail_kota["Termurah"] = detail_kota["Termurah"].apply(lambda x: f"Rp{x:,.0f}")
    detail_kota["Termahal"] = detail_kota["Termahal"].apply(lambda x: f"Rp{x:,.0f}")
    st.dataframe(detail_kota, use_container_width=True, hide_index=True)

# ============================================================
# TAB 4: ANALISIS PENJUALAN
# ============================================================
with tab4:
    st.header("📈 Analisis Penjualan")

    col1, col2 = st.columns(2)
    with col1:
        st.subheader("Top 10 Produk Terlaris")
        if "terjual" in df_f.columns and df_f["terjual"].notna().any():
            terlaris = df_f[df_f["terjual"].notna()].nlargest(10, "terjual")
            fig = px.bar(terlaris, x="terjual", y="nama_produk", orientation="h",
                         labels={"terjual": "Terjual", "nama_produk": ""},
                         color_discrete_sequence=["#4472C4"])
            fig.update_layout(height=450, yaxis=dict(autorange="reversed"))
            fig.update_yaxes(ticktext=[n[:35] for n in terlaris["nama_produk"]], tickvals=terlaris["nama_produk"])
            st.plotly_chart(fig, use_container_width=True)

    with col2:
        st.subheader("Distribusi Rating")
        if "rating" in df_f.columns and df_f["rating"].notna().any():
            rating_counts = df_f["rating"].value_counts().sort_index()
            fig = px.pie(values=rating_counts.values, names=[str(r) for r in rating_counts.index],
                         color_discrete_sequence=px.colors.qualitative.Set2)
            fig.update_traces(textposition="inside", textinfo="percent+label+value")
            fig.update_layout(height=450)
            st.plotly_chart(fig, use_container_width=True)

    st.subheader("Korelasi Harga vs Terjual")
    if "terjual" in df_f.columns and df_f["terjual"].notna().any():
        scatter_df = df_f[df_f["terjual"].notna() & df_f["harga_angka"].notna()]
        fig = px.scatter(scatter_df, x="harga_angka", y="terjual", color="brand",
                         hover_data=["nama_produk", "penjual"],
                         labels={"harga_angka": "Harga (Rp)", "terjual": "Terjual"},
                         color_discrete_sequence=px.colors.qualitative.Set1)
        fig.update_layout(height=400)
        st.plotly_chart(fig, use_container_width=True)

# ============================================================
# TAB 5: ANALISIS DISKON
# ============================================================
with tab5:
    st.header("🏷️ Analisis Diskon")

    has_diskon = df_f["diskon_persen"].notna()
    count_diskon = int(has_diskon.sum())
    count_no = len(df_f) - count_diskon

    col1, col2 = st.columns(2)
    with col1:
        st.subheader("Proporsi Produk Diskon")
        fig = px.pie(values=[count_diskon, count_no], names=["Diskon", "Tanpa Diskon"],
                     color_discrete_sequence=["#ED7D31", "#A5A5A5"])
        fig.update_traces(textposition="inside", textinfo="percent+label+value")
        fig.update_layout(height=350)
        st.plotly_chart(fig, use_container_width=True)

    with col2:
        st.subheader("Rata-rata Diskon per Seller")
        df_diskon = df_f[has_diskon]
        if len(df_diskon) > 0:
            avg_d = df_diskon.groupby("penjual")["diskon_persen"].mean().sort_values(ascending=False).head(10)
            fig = px.bar(x=avg_d.values, y=avg_d.index, orientation="h",
                         labels={"x": "Avg Diskon %", "y": "Seller"}, color_discrete_sequence=["#ED7D31"])
            fig.update_layout(height=350, yaxis=dict(autorange="reversed"))
            st.plotly_chart(fig, use_container_width=True)

    st.subheader("Top 10 Diskon Terbesar")
    if len(df_diskon) > 0:
        top_d = df_diskon.nlargest(10, "diskon_persen")[["nama_produk", "harga", "harga_sebelum_diskon", "diskon_persen", "penjual"]].reset_index(drop=True)
        top_d["diskon_persen"] = top_d["diskon_persen"].apply(lambda x: f"{x:.1f}%")
        st.dataframe(top_d, use_container_width=True, hide_index=True)
    else:
        st.info("Tidak ada produk diskon dalam filter saat ini")

# ============================================================
# TAB 6: ANALISIS BRAND
# ============================================================
with tab6:
    st.header("🏷️ Analisis Brand")

    col1, col2 = st.columns(2)
    with col1:
        st.subheader("Market Share per Brand")
        brand_counts = df_f["brand"].value_counts().head(10)
        fig = px.pie(values=brand_counts.values, names=brand_counts.index, hole=0.4,
                     color_discrete_sequence=px.colors.qualitative.Set2)
        fig.update_traces(textposition="inside", textinfo="percent+label")
        fig.update_layout(height=400)
        st.plotly_chart(fig, use_container_width=True)

    with col2:
        st.subheader("Harga Rata-rata per Brand")
        avg_brand = df_f.groupby("brand")["harga_angka"].mean().sort_values(ascending=False).head(10)
        fig = px.bar(x=avg_brand.values, y=avg_brand.index, orientation="h",
                     labels={"x": "Rata-rata Harga (Rp)", "y": "Brand"}, color_discrete_sequence=["#ED7D31"])
        fig.update_layout(height=400, yaxis=dict(autorange="reversed"))
        st.plotly_chart(fig, use_container_width=True)

    col3, col4 = st.columns(2)
    with col3:
        st.subheader("Rating per Brand")
        if "rating" in df_f.columns:
            avg_rat_brand = df_f.groupby("brand")["rating"].mean().sort_values(ascending=False).head(10)
            fig = px.bar(x=avg_rat_brand.values, y=avg_rat_brand.index, orientation="h",
                         labels={"x": "Avg Rating", "y": "Brand"}, color_discrete_sequence=["#FFC000"])
            fig.update_layout(height=400, yaxis=dict(autorange="reversed"))
            st.plotly_chart(fig, use_container_width=True)

    with col4:
        st.subheader("Jumlah Produk per Brand")
        fig = px.bar(x=brand_counts.values, y=brand_counts.index, orientation="h",
                     labels={"x": "Jumlah Produk", "y": "Brand"}, color_discrete_sequence=["#4472C4"])
        fig.update_layout(height=400, yaxis=dict(autorange="reversed"))
        st.plotly_chart(fig, use_container_width=True)

    # Detail per Brand
    st.subheader("Detail Harga per Brand")
    brand_detail = df_f.groupby("brand")["harga_angka"].agg(["count", "mean", "min", "max"]).sort_values("count", ascending=False).reset_index()
    brand_detail.columns = ["Brand", "Produk", "Rata-rata", "Termurah", "Termahal"]
    brand_detail["Rata-rata"] = brand_detail["Rata-rata"].apply(lambda x: f"Rp{x:,.0f}")
    brand_detail["Termurah"] = brand_detail["Termurah"].apply(lambda x: f"Rp{x:,.0f}")
    brand_detail["Termahal"] = brand_detail["Termahal"].apply(lambda x: f"Rp{x:,.0f}")
    st.dataframe(brand_detail, use_container_width=True, hide_index=True)

    # Seller Termurah per Brand
    st.subheader("Seller Termurah per Brand")
    rows = []
    for brand in df_f["brand"].unique():
        bdf = df_f[df_f["brand"] == brand]
        if len(bdf) > 0 and bdf["harga_angka"].notna().any():
            cheapest = bdf.loc[bdf["harga_angka"].idxmin()]
            rows.append({"Brand": brand, "Produk": str(cheapest.get("nama_produk", ""))[:50],
                         "Harga": str(cheapest.get("harga", "")), "Seller": str(cheapest.get("penjual", ""))})
    if rows:
        st.dataframe(pd.DataFrame(rows), use_container_width=True, hide_index=True)

# ============================================================
# TAB 7: BEST VALUE
# ============================================================
with tab7:
    st.header("💎 Best Value")
    st.caption("Skor = (Rating × Terjual) / (Harga / 1 Juta) — Semakin tinggi semakin worth it")

    bv = df_f.copy()
    bv["terjual_safe"] = pd.to_numeric(bv.get("terjual"), errors="coerce").fillna(0)
    bv["rating_safe"] = pd.to_numeric(bv.get("rating"), errors="coerce").fillna(0)
    bv["value_score"] = round((bv["rating_safe"] * (bv["terjual_safe"] + 1)) / (bv["harga_angka"] / 1e6), 2)

    col1, col2 = st.columns(2)
    with col1:
        st.subheader("Top 15 Best Value")
        top_bv = bv[bv["value_score"] > 0].nlargest(15, "value_score")
        fig = px.bar(top_bv, x="value_score", y="nama_produk", orientation="h",
                     labels={"value_score": "Value Score", "nama_produk": ""},
                     color_discrete_sequence=["#70AD47"])
        fig.update_layout(height=500, yaxis=dict(autorange="reversed"))
        fig.update_yaxes(ticktext=[n[:30] for n in top_bv["nama_produk"]], tickvals=top_bv["nama_produk"])
        st.plotly_chart(fig, use_container_width=True)

    with col2:
        st.subheader("Korelasi Diskon vs Rating")
        if df_f["diskon_persen"].notna().any() and "rating" in df_f.columns:
            scat = df_f[df_f["diskon_persen"].notna() & df_f["rating"].notna()]
            fig = px.scatter(scat, x="diskon_persen", y="rating", color="brand",
                             hover_data=["nama_produk"],
                             labels={"diskon_persen": "Diskon (%)", "rating": "Rating"})
            fig.update_layout(height=500)
            st.plotly_chart(fig, use_container_width=True)
        else:
            st.info("Tidak ada data diskon")

    # Best Value per Brand
    st.subheader("Best Value per Brand")
    rows = []
    for brand in bv["brand"].unique():
        bdf = bv[bv["brand"] == brand]
        if len(bdf) > 0 and bdf["value_score"].max() > 0:
            best = bdf.loc[bdf["value_score"].idxmax()]
            rows.append({"Brand": brand, "Produk": str(best.get("nama_produk", ""))[:50],
                         "Harga": str(best.get("harga", "")), "Rating": best["rating_safe"],
                         "Terjual": int(best["terjual_safe"]), "Score": best["value_score"]})
    if rows:
        st.dataframe(pd.DataFrame(rows).sort_values("Score", ascending=False), use_container_width=True, hide_index=True)

    # Full table
    st.subheader("Top 15 Detail")
    display = top_bv[["nama_produk", "brand", "harga", "rating", "terjual", "value_score"]].reset_index(drop=True)
    st.dataframe(display, use_container_width=True, hide_index=True)

# ============================================================
# TAB 8: REKOMENDASI
# ============================================================
with tab8:
    st.header("💡 Rekomendasi Produk")
    st.caption("Skor = (Terjual 30% | Rating 15% | Harga 15% | Favorit 15% | Diskon 10% | Ulasan 10% | Stock 5%)")

    df_rec = df_f.copy()
    df_rec["rating_safe"] = pd.to_numeric(df_rec.get("rating"), errors="coerce").fillna(0)
    df_rec["terjual_safe"] = pd.to_numeric(df_rec.get("terjual"), errors="coerce").fillna(0)
    df_rec["harga_safe"] = df_rec["harga_angka"].fillna(1)
    df_rec["liked_safe"] = pd.to_numeric(df_rec.get("liked_count"), errors="coerce").fillna(0)
    df_rec["cmc_safe"] = pd.to_numeric(df_rec.get("comment_count"), errors="coerce").fillna(0)
    df_rec["diskon_safe"] = pd.to_numeric(df_rec.get("diskon_persen"), errors="coerce").fillna(0)
    df_rec["stock_safe"] = pd.to_numeric(df_rec.get("stock"), errors="coerce").fillna(0)

    def norm(series, higher=True):
        mn, mx = series.min(), series.max()
        if mx == mn:
            return pd.Series(50, index=series.index)
        normed = (series - mn) / (mx - mn) * 100
        return normed if higher else 100 - normed

    df_rec["r_rating"] = norm(df_rec["rating_safe"])
    df_rec["r_terjual"] = norm(df_rec["terjual_safe"])
    df_rec["r_liked"] = norm(df_rec["liked_safe"])
    df_rec["r_cmc"] = norm(df_rec["cmc_safe"])
    df_rec["r_harga"] = norm(df_rec["harga_safe"], higher=False)
    df_rec["r_diskon"] = norm(df_rec["diskon_safe"])
    df_rec["r_stock"] = norm(df_rec["stock_safe"])

    df_rec["rekomendasi_score"] = round(
        df_rec["r_rating"] * 0.15
        + df_rec["r_terjual"] * 0.30
        + df_rec["r_liked"] * 0.15
        + df_rec["r_cmc"] * 0.10
        + df_rec["r_harga"] * 0.15
        + df_rec["r_diskon"] * 0.10
        + df_rec["r_stock"] * 0.05,
        2
    )

    col1, col2 = st.columns(2)
    with col1:
        st.subheader("Top 20 Rekomendasi")
        top_rec = df_rec[df_rec["rekomendasi_score"] > 0].nlargest(20, "rekomendasi_score")
        fig = px.bar(top_rec, x="rekomendasi_score", y="nama_produk", orientation="h",
                     labels={"rekomendasi_score": "Skor", "nama_produk": ""},
                     color_discrete_sequence=["#2E75B6"])
        fig.update_layout(height=550, yaxis=dict(autorange="reversed"))
        fig.update_yaxes(ticktext=[n[:35] for n in top_rec["nama_produk"]], tickvals=top_rec["nama_produk"])
        st.plotly_chart(fig, use_container_width=True)

    with col2:
        st.subheader("Engagement Tertinggi (Favorit + Ulasan)")
        df_rec["engagement_score"] = df_rec["liked_safe"] + df_rec["cmc_safe"]
        top_eng = df_rec[df_rec["engagement_score"] > 0].nlargest(20, "engagement_score")
        fig2 = px.bar(top_eng, x="engagement_score", y="nama_produk", orientation="h",
                      labels={"engagement_score": "Engagement", "nama_produk": ""},
                      color_discrete_sequence=["#70AD47"])
        fig2.update_layout(height=550, yaxis=dict(autorange="reversed"))
        fig2.update_yaxes(ticktext=[n[:35] for n in top_eng["nama_produk"]], tickvals=top_eng["nama_produk"])
        st.plotly_chart(fig2, use_container_width=True)

    # Segmentasi budget/mid/premium
    st.subheader("Rekomendasi per Segmen Harga")
    seg_col1, seg_col2, seg_col3 = st.columns(3)
    for seg_idx, (seg_label, seg_df) in enumerate([
        ("Budget < 5jt", df_rec[df_rec["harga_angka"] < 5_000_000]),
        ("Mid-Range 5-15jt", df_rec[(df_rec["harga_angka"] >= 5_000_000) & (df_rec["harga_angka"] < 15_000_000)]),
        ("Premium > 15jt", df_rec[df_rec["harga_angka"] >= 15_000_000]),
    ]):
        with [seg_col1, seg_col2, seg_col3][seg_idx]:
            best_seg = seg_df[seg_df["rekomendasi_score"] > 0].nlargest(5, "rekomendasi_score")
            st.markdown(f"**{seg_label}**")
            rows_data = []
            for _, r in best_seg.iterrows():
                rows_data.append({
                    "Produk": str(r.get("nama_produk", ""))[:40],
                    "Harga": str(r.get("harga", "")),
                    "Rating": float(r["rating_safe"]) if r["rating_safe"] > 0 else "-",
                    "Terjual": int(r["terjual_safe"]) if r["terjual_safe"] > 0 else "-",
                    "Score": float(r["rekomendasi_score"]),
                })
            st.dataframe(pd.DataFrame(rows_data), use_container_width=True, hide_index=True)

    # Detail table
    st.subheader("Detail Top 20 Rekomendasi")
    disp_rec = top_rec[["nama_produk", "brand", "harga", "rating_safe", "terjual_safe",
                        "liked_safe", "cmc_safe", "diskon_safe", "rekomendasi_score"]].reset_index(drop=True)
    disp_rec.columns = ["Nama Produk", "Brand", "Harga", "Rating", "Terjual", "Total Favorit", "Jumlah Ulasan", "Diskon %", "Score"]
    st.dataframe(disp_rec, use_container_width=True, hide_index=True)

# ============================================================
# DATA COMPLETENESS (footer)
# ============================================================
st.markdown("---")
with st.expander("📋 Kelengkapan Data & Data Lengkap"):
    col1, col2 = st.columns([1, 3])
    with col1:
        st.subheader("Kelengkapan")
        total = len(df_f)
        for field in ["nama_produk", "harga", "penjual", "kota", "terjual", "rating"]:
            if field in df_f.columns:
                complete = int(df_f[field].notna().sum())
                if df_f[field].dtype == "object":
                    complete = int((df_f[field].notna() & (df_f[field] != "")).sum())
                st.write(f"**{field}**: {complete}/{total} ({complete/total*100:.0f}%)")
    with col2:
        st.subheader("Data Lengkap")
        show_cols = ["nama_produk", "brand", "harga", "harga_sebelum_diskon", "penjual", "kota", "terjual", "rating"]
        existing = [c for c in show_cols if c in df_f.columns]
        st.dataframe(df_f[existing], use_container_width=True, hide_index=True, height=400)
