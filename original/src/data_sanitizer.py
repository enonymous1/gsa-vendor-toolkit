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
    df = pd.read_csv(input_path)
    sanitized_df = sanitize_df(df)

    os.makedirs(os.path.dirname(output_path), exist_ok=True)
    sanitized_df.to_csv(output_path, index=False)
    print(f"Sanitized source created at: {output_rel_path}")

if __name__ == "__main__":
    # Standardize the source data
    RAW_CSV = os.path.join('ext_res', '2026_02_12_04_10_24.csv')
    CLEAN_CSV = os.path.join('ext_res', 'vendors_sanitized.csv')
    run_sanitization(RAW_CSV, CLEAN_CSV)

