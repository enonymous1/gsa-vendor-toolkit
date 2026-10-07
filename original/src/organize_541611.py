import pandas as pd
import os
import shutil
from utils import get_project_root

def organize_541611(sanitized_file):
    root = get_project_root()
    data_path = os.path.join(root, sanitized_file)
    
    # Source directory (from download_541611 script)
    source_dir = os.path.join(root, "output", "downloads", "541611_price_lists")
    # Target root directory for Regional 541611
    target_root = os.path.join(root, "output", "downloads", "541611_by_region")
    
    if not os.path.exists(source_dir):
        print(f"Error: Source directory {source_dir} does not exist.")
        return

    df = pd.read_csv(data_path, dtype={'Contact #': str}, low_memory=False)
    
    # Only process those with price lists
    df = df[df['Price List'].notna()].copy()
    
    print(f"Found {len(df)} 541611 vendors with price lists to organize...")

    files_moved = 0
    errors = 0

    for index, row in df.iterrows():
        vendor = str(row['Vendor']).strip()
        contact_num = str(row['Contact #']).strip()
        state = str(row['State']).strip().upper() if pd.notna(row['State']) else "UNKNOWN_STATE"
        city = "".join([c if c.isalnum() or c == ' ' else "_" for c in str(row['City']).strip()]) if pd.notna(row['City']) else "UNKNOWN_CITY"
        
        # Consistent with download script logic
        safe_vendor = "".join([c if c.isalnum() else "_" for c in vendor])[:50]
        
        found_file = None
        for ext in ['.pdf', '.xlsx', '.xls', '.doc']:
            filename = f"{safe_vendor}_{contact_num}{ext}"
            potential_path = os.path.join(source_dir, filename)
            if os.path.exists(potential_path):
                found_file = filename
                break
        
        if found_file:
            target_dir = os.path.join(target_root, state, city)
            os.makedirs(target_dir, exist_ok=True)
            
            try:
                # Copying so we keep the original flat folder for easier re-runs if needed
                shutil.copy2(os.path.join(source_dir, found_file), os.path.join(target_dir, found_file))
                files_moved += 1
                if files_moved % 200 == 0:
                    print(f"Progress: Organized {files_moved} files...", end="\r")
            except Exception as e:
                print(f"\nError copying {found_file}: {e}")
                errors += 1
        
    print(f"\nOrganization complete!")
    print(f"Successfully copied: {files_moved}")
    print(f"Organized files are located in: output/downloads/541611_by_region/")

if __name__ == "__main__":
    CLEAN_CSV = os.path.join('ext_res', 'vendors_541611_sanitized.csv')
    organize_541611(CLEAN_CSV)

