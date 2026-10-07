import pandas as pd
import os
from utils import get_project_root

def analyze_cardinality(file_path, region_name):
    if not os.path.exists(file_path):
        print(f"File not found: {file_path}")
        return

    print(f"\n--- Analysis for {region_name} Master Price List ---")
    # Using low_memory=False because these files can be large and have mixed types
    df = pd.read_csv(file_path, low_memory=False)
    
    if 'Title' not in df.columns:
        print(f"Column 'Title' not found in {file_path}")
        return

    # Clean the titles for better aggregation
    df['Title_Clean'] = df['Title'].astype(str).str.strip().str.upper()
    
    total_rows = len(df)
    unique_titles = df['Title_Clean'].nunique()
    
    print(f"Total Rows: {total_rows}")
    print(f"Unique Titles (Case-Insensitive): {unique_titles}")
    
    print("\nTop 20 Most Common Job Titles:")
    counts = df['Title_Clean'].value_counts().head(20)
    
    # Calculate percentage
    for title, count in counts.items():
        percentage = (count / total_rows) * 100
        print(f" - {title}: {count} ({percentage:.2f}%)")

    # Cardinality of SINs as well
    if 'SIN' in df.columns:
        print("\nTop 5 SINs (Special Item Numbers):")
        sin_counts = df['SIN'].astype(str).str.strip().value_counts().head(5)
        for sin, count in sin_counts.items():
            print(f" - {sin}: {count}")

if __name__ == "__main__":
    root = get_project_root()
    va_file = os.path.join(root, "output", "merged", "VA_Master_Price_List.csv")
    dc_file = os.path.join(root, "output", "merged", "DC_Master_Price_List.csv")
    
    analyze_cardinality(va_file, "VA")
    analyze_cardinality(dc_file, "DC")

