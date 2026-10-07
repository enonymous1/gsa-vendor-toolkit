import pandas as pd
import os
import numpy as np
from utils import get_project_root
from scipy import stats

def aggregate_it_titles_analysis(states=['VA', 'DC', 'National']):
    root = get_project_root()
    output_dir = os.path.join(root, "output", "it_title_analysis")
    os.makedirs(output_dir, exist_ok=True)
    
    # We'll use this column for the actual price
    price_col = 'GSA Price with IFF  - as of price list generation date'

    for state in states:
        if state == 'National':
            input_csv = os.path.join(root, "output", "merged_national", "National_IT_Master_Price_List.csv")
        else:
            input_csv = os.path.join(root, "output", "merged_filtered", f"{state}_SIN_54151S_Only.csv")
        
        if not os.path.exists(input_csv):
            print(f"Skipping {state}: Input file not found at {input_csv}.")
            continue

        print(f"Analyzing Job Title metrics for {state} IT Roles...")
        df = pd.read_csv(input_csv, low_memory=False)
        
        # Standardize Price Column naming if possible or use the primary one
        # Handle cases where multiple price columns might exist by focusing on the primary detected one
        if price_col not in df.columns:
            # Fallback to look for anything containing 'GSA Price'
            fallback = [c for c in df.columns if 'GSA Price' in str(c) and 'with IFF' in str(c)]
            actual_price_col = fallback[0] if fallback else None
        else:
            actual_price_col = price_col

        if not actual_price_col:
            print(f"  Error: Price column not found for {state}.")
            continue

        # Clean Title and Description
        df['Title_Key'] = df['Title'].astype(str).str.strip().str.upper()
        df['Description'] = df['Description'].fillna('').astype(str).str.strip()
        
        # Convert Price to numeric, forcing errors to NaN
        # GSA prices often have $ or commas
        if df[actual_price_col].dtype == object:
            df['Price_Numeric'] = df[actual_price_col].astype(str).str.replace('$', '').str.replace(',', '').str.strip()
            df['Price_Numeric'] = pd.to_numeric(df['Price_Numeric'], errors='coerce')
        else:
            df['Price_Numeric'] = pd.to_numeric(df[actual_price_col], errors='coerce')
        
        # Drop rows where price couldn't be parsed for numeric analysis
        numeric_df = df.dropna(subset=['Price_Numeric']).copy()

        def get_mode(x):
            if x.empty: return np.nan
            m = x.mode()
            return m.iloc[0] if not m.empty else np.nan

        # Aggregation functions
        agg_functions = {
            'Price_Numeric': ['count', 'min', 'max', 'mean', 'median', get_mode],
            'Description': lambda x: " | ".join(sorted(list(set([str(v).strip() for v in x if pd.notna(v) and str(v).strip()]))))[:5000]
        }

        # Perform the GroupBy
        analysis_df = numeric_df.groupby('Title_Key').agg(agg_functions)
        
        # Flatten MultiIndex columns
        analysis_df.columns = [
            'Count', 'Min_Price', 'Max_Price', 'Mean_Price', 'Median_Price', 'Mode_Price', 'Merged_Descriptions'
        ]
        
        # Calculate Range
        analysis_df['Price_Range'] = analysis_df['Max_Price'] - analysis_df['Min_Price']
        
        # Reset index to bring Title back
        analysis_df = analysis_df.reset_index()
        analysis_df = analysis_df.sort_values(by='Count', ascending=False)

        # Output formats
        csv_out = os.path.join(output_dir, f"{state}_IT_Role_Metrics.csv")
        xlsx_out = os.path.join(output_dir, f"{state}_IT_Role_Metrics.xlsx")
        
        analysis_df.to_csv(csv_out, index=False)
        
        # Save Excel (within limits)
        try:
            # Cap cell size for Excel descriptions to avoid errors
            excel_df = analysis_df.copy()
            excel_df['Merged_Descriptions'] = excel_df['Merged_Descriptions'].str.slice(0, 32000)
            excel_df.to_excel(xlsx_out, index=False)
            print(f"  Saved Metrics to: {xlsx_out}")
        except Exception as e:
            print(f"  Excel save failed: {e}")

        print(f"  Processed {len(analysis_df)} unique IT titles for {state}.")

if __name__ == "__main__":
    aggregate_it_titles_analysis(['VA', 'DC', 'National'])

