import pandas as pd
import os
import glob
from utils import get_project_root

def merge_state_price_lists(states=['VA', 'DC']):
    root = get_project_root()
    base_dir = os.path.join(root, "output", "downloads", "price_lists_by_region")
    output_dir = os.path.join(root, "output", "merged")
    os.makedirs(output_dir, exist_ok=True)

    # We also need the sanitized data to get official vendor names if possible, 
    # but the folder structure and filename already have vendor/contact info.
    # We'll use the filename/folder for metadata.

    for state in states:
        state_dir = os.path.join(base_dir, state.upper())
        if not os.path.exists(state_dir):
            print(f"Skipping {state}: Directory not found.")
            continue

        print(f"Processing state: {state}...")
        all_data = []
        files_processed = 0
        files_skipped = 0
        
        # Walk through all cities in the state
        for city in os.listdir(state_dir):
            city_path = os.path.join(state_dir, city)
            if not os.path.isdir(city_path):
                continue
            
            # Find all excel files
            excel_files = glob.glob(os.path.join(city_path, "*.xls*"))
            
            for file_path in excel_files:
                filename = os.path.basename(file_path)
                # Attempt to extract vendor name from filename (SafeVendor_Contact#.ext)
                # We'll just use the filename as a source reference
                
                try:
                    # Load the Excel file
                    # We use None for sheet_name to get a dict of all sheets first 
                    # OR we just try to load "Price List" directly
                    xl = pd.ExcelFile(file_path)
                    sheet_names = xl.sheet_names
                    
                    target_sheet = None
                    # Look for exact match or case-insensitive match
                    for s in sheet_names:
                        if s.strip().lower() == "price list":
                            target_sheet = s
                            break
                    
                    if target_sheet:
                        df = pd.read_excel(file_path, sheet_name=target_sheet)
                        
                        # Add Metadata
                        df['Source_State'] = state
                        df['Source_City'] = city
                        df['Source_File'] = filename
                        
                        # Basic cleaning: remove completely empty rows/cols
                        df = df.dropna(how='all').dropna(axis=1, how='all')
                        
                        all_data.append(df)
                        files_processed += 1
                        print(f"  [{files_processed}] Added: {filename}", end="\r")
                    else:
                        # print(f"  Skipped: {filename} (No 'Price List' sheet found)")
                        files_skipped += 1
                except Exception as e:
                    print(f"\n  Error reading {filename}: {e}")
                    files_skipped += 1

        print(f"\nFinished {state}: {files_processed} files merged, {files_skipped} skipped.")
        
        if all_data:
            print(f"Combining data for {state}...")
            # Use sort=False to keep column order as much as possible
            master_df = pd.concat(all_data, ignore_index=True, sort=False)
            
            # Save to CSV (more reliable for large merges) and Excel
            csv_out = os.path.join(output_dir, f"{state}_Master_Price_List.csv")
            xlsx_out = os.path.join(output_dir, f"{state}_Master_Price_List.xlsx")
            
            master_df.to_csv(csv_out, index=False)
            
            # Excel has a row limit of ~1M, check if we exceeded it
            if len(master_df) < 1000000:
                try:
                    master_df.to_excel(xlsx_out, index=False)
                    print(f"Saved: {xlsx_out}")
                except Exception as e:
                    print(f"Could not save Excel for {state}: {e}")
            else:
                print(f"Warning: {state} data too large for Excel ({len(master_df)} rows). Saved CSV only.")
            
            print(f"Saved: {csv_out}")
        else:
            print(f"No data found to merge for {state}.")

if __name__ == "__main__":
    merge_state_price_lists(['VA', 'DC'])

