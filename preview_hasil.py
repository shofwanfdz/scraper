"""Preview the latest scraping result"""
import os
import glob
import pandas as pd

# Find latest Excel file (exclude temp files)
files = [f for f in glob.glob('hasil/blibli/*.xlsx') if not os.path.basename(f).startswith('~$')]
if not files:
    print("No Excel files found in hasil/blibli/")
    exit()

latest = max(files, key=os.path.getmtime)
print(f"File: {latest}")
print(f"Size: {os.path.getsize(latest):,} bytes")
print()

df = pd.read_excel(latest, sheet_name='Products')
print(f"Total rows: {len(df)}")
print(f"Columns: {list(df.columns)}")
print()

print("=" * 80)
print("  TOP 10 PRODUCTS")
print("=" * 80)
cols = ['nama_produk', 'harga', 'penjual', 'terjual', 'rating']
existing = [c for c in cols if c in df.columns]
print(df[existing].head(10).to_string())

print()
print("=" * 80)
print("  PRICE STATISTICS")
print("=" * 80)
if 'harga' in df.columns:
    harga = df['harga'].dropna()
    print(f"  Min Price:    Rp {harga.min():>12,.0f}")
    print(f"  Max Price:    Rp {harga.max():>12,.0f}")
    print(f"  Avg Price:    Rp {harga.mean():>12,.0f}")
    print(f"  Median Price: Rp {harga.median():>12,.0f}")

print()
print("=" * 80)
print("  TOP SELLERS")
print("=" * 80)
if 'penjual' in df.columns:
    top = df['penjual'].value_counts().head(10)
    for seller, count in top.items():
        print(f"  {seller:<40} ({count} products)")

print()
print("=" * 80)
print("  LOCATION DISTRIBUTION")
print("=" * 80)
if 'kota' in df.columns:
    locs = df['kota'].value_counts().head(10)
    for loc, count in locs.items():
        print(f"  {loc:<40} ({count} products)")
