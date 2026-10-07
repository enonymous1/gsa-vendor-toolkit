import pandas as pd
import os
from utils import get_project_root, sanitize_df

def run_sanitization(input_rel_path, output_rel_path):
    root = get_project_root()
    input_path = os.path.join(root, input_rel_path)
    output_path = os.path.join(root, output_rel_path)

    if not os.path.exists(input_path):
        print(f"Error: Raw file not found at {input_path}")
        return

    print(f"Sanitizing {input_rel_path}...")
    # Low memory False to handle mixed types in large GSA CSVs
    df = pd.read_csv(input_path, low_memory=False)
    
    # Ensure 'Category' exists and filter for 541611 before sanitizing to save time?
    # No, sanitize first to keep standard flow, but the user is specific about 541611.
    # Let's filter for 541611 right here since we are starting a new project branch.
    
    if 'Category' in df.columns:
        print("Filtering for SIN 541611 (Management Consulting)...")
        df = df[df['Category'].astype(str).str.contains('541611', na=False)].copy()
        print(f"Found {len(df)} vendors for 541611.")
    
    sanitized_df = sanitize_df(df)

    os.makedirs(os.path.dirname(output_path), exist_ok=True)
    sanitized_df.to_csv(output_path, index=False)
    print(f"Sanitized 541611 source created at: {output_rel_path}")

if __name__ == "__main__":
    # Updated for March 2nd file and Management Consulting SIN
    RAW_CSV = os.path.join('ext_res', '2026_03_02_08_18_31.csv')
    CLEAN_CSV = os.path.join('ext_res', 'vendors_541611_sanitized.csv')
    run_sanitization(RAW_CSV, CLEAN_CSV)

