import pandas as pd
import os
import glob
from utils import get_project_root

def merge_541611_data(states=['VA', 'DC', 'MD']):
    root = get_project_root()
    base_dir = os.path.join(root, "output", "downloads", "541611_by_region")
    output_dir = os.path.join(root, "output", "541611_analysis")
    os.makedirs(output_dir, exist_ok=True)

    for state in states:
        state_dir = os.path.join(base_dir, state.upper())
        if not os.path.exists(state_dir):
            print(f"Skipping {state}: Directory not found.")
            continue

        print(f"Processing 541611 state: {state}...")
        all_data = []
        files_processed = 0
        files_skipped = 0
        
        for city in os.listdir(state_dir):
            city_path = os.path.join(state_dir, city)
            if not os.path.isdir(city_path):
                continue
            
            # Find all excel files
            excel_files = glob.glob(os.path.join(city_path, "*.xls*"))
            
            for file_path in excel_files:
                filename = os.path.basename(file_path)
                try:
                    xl = pd.ExcelFile(file_path)
                    sheet_names = xl.sheet_names
                    
                    target_sheet = None
                    # Search for 'Price List' sheet
                    for s in sheet_names:
                        if "price list" in s.strip().lower():
                            target_sheet = s
                            break
                    
                    if target_sheet:
                        df = pd.read_excel(file_path, sheet_name=target_sheet)
                        
                        # Add Metadata
                        df['Source_State'] = state
                        df['Source_City'] = city
                        df['Source_File'] = filename
                        
                        # Store vendor and contract if possible from filename
                        # Filename logic: safe_vendor_contact#.ext
                        # Strip extension
                        name_part = os.path.splitext(filename)[0]
                        if "_" in name_part:
                            parts = name_part.rsplit("_", 1)
                            df['Metadata_Vendor'] = parts[0]
                            df['Metadata_Contract'] = parts[1]
                        
                        all_data.append(df)
                        files_processed += 1
                        print(f"  [{files_processed}] Added: {filename}", end="\r")
                    else:
                        files_skipped += 1
                except Exception:
                    files_skipped += 1

        print(f"\nFinished {state}: {files_processed} files merged, {files_skipped} skipped.")
        
        if all_data:
            master_df = pd.concat(all_data, ignore_index=True, sort=False)
            csv_out = os.path.join(output_dir, f"{state}_541611_Master_List.csv")
            master_df.to_csv(csv_out, index=False)
            print(f"Saved: {csv_out} ({len(master_df)} rows)")
        else:
            print(f"No data found for {state}.")

if __name__ == "__main__":
    # Expand to common regions for this request
    merge_541611_data(['VA', 'DC', 'MD'])

