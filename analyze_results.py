"""Analyze scraping results for data quality issues"""
import pandas as pd
import glob
import os

print("=" * 70)
print("  ANALISIS HASIL SCRAPING")
print("=" * 70)

# === LAPTOP FILE (120 produk - versi lama dengan semua kolom) ===
files = [f for f in glob.glob("hasil/blibli/*laptop*153719*.xlsx") if not os.path.basename(f).startswith("~")]
if files:
    df = pd.read_excel(files[0], sheet_name="Products")
    print("\n--- FILE: blibli_laptop_153719.xlsx (versi lama, 120 produk) ---")
    print("Columns:", list(df.columns))
    print("Total:", len(df), "rows")
    print()

    # Check diskon data
    if "harga_asli" in df.columns:
        has_asli = df["harga_asli"].notna().sum()
        print("Produk dengan harga_asli (sebelum diskon):", has_asli, "/", len(df))
        if has_asli > 0:
            sample = df[df["harga_asli"].notna()][["nama_produk", "harga", "harga_asli", "diskon"]].head(5)
            print(sample.to_string())
            print()

    if "diskon" in df.columns:
        has_diskon = df[(df["diskon"].notna()) & (df["diskon"] != "")].shape[0]
        print("Produk dengan kolom diskon terisi:", has_diskon, "/", len(df))
        if has_diskon > 0:
            sample = df[(df["diskon"].notna()) & (df["diskon"] != "")][["nama_produk", "harga", "harga_asli", "diskon"]].head(10)
            print(sample.to_string())

print()
print("=" * 70)

# === SEPATU FILE (20 produk - versi baru) ===
files2 = [f for f in glob.glob("hasil/blibli/*sepatu*.xlsx") if not os.path.basename(f).startswith("~")]
if files2:
    df2 = pd.read_excel(files2[0], sheet_name="Products")
    print("\n--- FILE: blibli_sepatu.xlsx (20 produk) ---")
    print("Columns:", list(df2.columns))
    print("Total:", len(df2), "rows")
    print()

    print("Missing data per kolom:")
    for col in df2.columns:
        missing = df2[col].isna().sum()
        empty_str = 0
        if df2[col].dtype == "object":
            empty_str = (df2[col] == "").sum()
        total_empty = missing + empty_str
        if total_empty > 0:
            print("  {}: {}/{} kosong ({:.1f}%)".format(col, total_empty, len(df2), total_empty/len(df2)*100))

    print()
    print("Detail PENJUAL:")
    for idx, row in df2.iterrows():
        penjual = row.get("penjual", "")
        kota = row.get("kota", "")
        nama = str(row.get("nama_produk", ""))[:50]
        penjual_str = str(penjual) if pd.notna(penjual) and penjual != "" else "(KOSONG)"
        print("  [{}] {} | seller: {} | kota: {}".format(idx, nama, penjual_str, kota))

print()
print("=" * 70)

# === LAPTOP FILE TERBARU (30 produk - versi baru dengan Rp format) ===
files3 = [f for f in glob.glob("hasil/blibli/*laptop*155651*.xlsx") if not os.path.basename(f).startswith("~")]
if files3:
    df3 = pd.read_excel(files3[0], sheet_name="Products")
    print("\n--- FILE: blibli_laptop_155651.xlsx (versi baru, 30 produk) ---")
    print("Columns:", list(df3.columns))
    print()
    print("harga_sebelum_diskon terisi:", df3["harga_sebelum_diskon"].notna().sum(), "/", len(df3))
    print()
    print("Sample data:")
    print(df3[["nama_produk", "harga", "harga_sebelum_diskon"]].head(5).to_string())
