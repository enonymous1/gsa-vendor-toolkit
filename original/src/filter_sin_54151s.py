import pandas as pd
import os
from utils import get_project_root

def filter_sin_54151s(states=['VA', 'DC']):
    root = get_project_root()
    input_dir = os.path.join(root, "output", "merged")
    output_dir = os.path.join(root, "output", "merged_filtered")
    os.makedirs(output_dir, exist_ok=True)
    
    target_sin = "54151S"

    for state in states:
        input_csv = os.path.join(input_dir, f"{state}_Master_Price_List.csv")
        if not os.path.exists(input_csv):
            print(f"Skipping {state}: Merged file not found.")
            continue

        print(f"Filtering {state} for SIN {target_sin}...")
        
        # Using low_memory=False for large mixed-type files
        df = pd.read_csv(input_csv, low_memory=False)
        
        if 'SIN' not in df.columns:
            print(f"  Error: 'SIN' column not found in {state} file.")
            continue

        # Filter for the specific SIN
        # SINs can sometimes be comma-separated or have whitespace
        filtered_df = df[df['SIN'].astype(str).str.contains(target_sin, na=False)].copy()
        
        count = len(filtered_df)
        total = len(df)
        print(f"  Found {count} rows matching {target_sin} (out of {total} total).")

        if count > 0:
            csv_out = os.path.join(output_dir, f"{state}_SIN_54151S_Only.csv")
            xlsx_out = os.path.join(output_dir, f"{state}_SIN_54151S_Only.xlsx")
            
            filtered_df.to_csv(csv_out, index=False)
            
            # Save Excel if it's within reasonable limits
            if count < 1000000:
                try:
                    filtered_df.to_excel(xlsx_out, index=False)
                    print(f"  Saved: {xlsx_out}")
                except Exception as e:
                    print(f"  Excel save failed: {e}")
            
            print(f"  Saved: {csv_out}")
        else:
            print(f"  No rows found for SIN {target_sin} in {state}.")

if __name__ == "__main__":
    filter_sin_54151s(['VA', 'DC'])

