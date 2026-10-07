import pandas as pd
import os
import numpy as np
from utils import get_project_root

def analyze_541611_pricing(states=['VA', 'DC', 'MD', 'National']):
    root = get_project_root()
    input_dir = os.path.join(root, "output", "541611_analysis")
    output_dir = os.path.join(root, "output", "541611_metrics")
    os.makedirs(output_dir, exist_ok=True)
    
    price_col = 'GSA Price with IFF  - as of price list generation date'

    for state in states:
        if state == 'National':
            # Create National file by combining VA, DC, MD if it doesn't exist
            national_csv = os.path.join(input_dir, "National_541611_Master_List.csv")
            if not os.path.exists(national_csv):
                print(f"Creating National 541611 Master List...")
                all_shards = []
                for s in ['VA', 'DC', 'MD']:
                    shard_path = os.path.join(input_dir, f"{s}_541611_Master_List.csv")
                    if os.path.exists(shard_path):
                        all_shards.append(pd.read_csv(shard_path, low_memory=False))
                if all_shards:
                    df = pd.concat(all_shards, ignore_index=True)
                    df.to_csv(national_csv, index=False)
                else:
                    print("Skipping National: No state shards found.")
                    continue
            else:
                df = pd.read_csv(national_csv, low_memory=False)
        else:
            input_csv = os.path.join(input_dir, f"{state}_541611_Master_List.csv")
            if not os.path.exists(input_csv):
                print(f"Skipping {state}: Input CSV not found.")
                continue
            df = pd.read_csv(input_csv, low_memory=False)

        print(f"Analyzing Management Consulting roles for {state}...")
        
        # Clean columns
        df['Title'] = df['Title'].fillna('').astype(str).str.strip()
        df['Title_Key'] = df['Title'].str.upper()
        df['Description'] = df['Description'].fillna('').astype(str).str.strip()
        
        # Numeric Price Conversion
        if price_col not in df.columns:
            # Re-detect price col if name shifted
            price_guess = [c for c in df.columns if 'GSA' in str(c) and 'Price' in str(c)]
            actual_price_col = price_guess[0] if price_guess else None
        else:
            actual_price_col = price_col

        if not actual_price_col:
            print(f"  Warning: No price column found for {state}. Check Excel sheet structure.")
            continue

        df['Price_Numeric'] = pd.to_numeric(df[actual_price_col].astype(str).str.replace('$', '').str.replace(',', '').str.strip(), errors='coerce')
        df = df.dropna(subset=['Price_Numeric'])

        # Aggregate metrics
        agg_map = {
            'Price_Numeric': ['count', 'min', 'max', 'mean', 'median'],
            'Description': lambda x: " | ".join(sorted(list(set([str(v) for v in x if v]))))[:5000]
        }
        
        metrics = df.groupby('Title_Key').agg(agg_map)
        metrics.columns = ['Count', 'Min', 'Max', 'Mean', 'Median', 'Descriptions']
        metrics = metrics.reset_index().sort_values(by='Count', ascending=False)

        # Save metrics
        csv_out = os.path.join(output_dir, f"{state}_541611_Metrics.csv")
        xlsx_out = os.path.join(output_dir, f"{state}_541611_Metrics.xlsx")
        metrics.to_csv(csv_out, index=False)
        metrics.to_excel(xlsx_out, index=False)
        print(f"  Processed {len(metrics)} roles for {state}. Metrics saved to {output_dir}.")

if __name__ == "__main__":
    analyze_541611_pricing(['VA', 'DC', 'MD', 'National'])

