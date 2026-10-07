import pandas as pd
import os
import shutil
from utils import get_project_root

def organize_price_lists(sanitized_file):
    root = get_project_root()
    data_path = os.path.join(root, sanitized_file)
    
    if not os.path.exists(data_path):
        print(f"Error: Sanitized file not found.")
        return

    # Source directory
    source_dir = os.path.join(root, "output", "downloads", "price_lists")
    # Target root directory
    target_root = os.path.join(root, "output", "downloads", "price_lists_by_region")
    
    if not os.path.exists(source_dir):
        print(f"Error: Source directory {source_dir} does not exist.")
        return

    df = pd.read_csv(data_path, dtype={'Contact #': str})
    
    # Filter only those that have a price list (as those are what we downloaded)
    df = df[df['Price List'].notna()].copy()
    
    print(f"Found {len(df)} vendors with price lists to organize...")

    files_moved = 0
    errors = 0

    for index, row in df.iterrows():
        vendor = str(row['Vendor']).strip()
        contact_num = str(row['Contact #']).strip()
        state = str(row['State']).strip().upper() if pd.notna(row['State']) else "UNKNOWN_STATE"
        city = "".join([c if c.isalnum() or c == ' ' else "_" for c in str(row['City']).strip()]) if pd.notna(row['City']) else "UNKNOWN_CITY"
        
        # Reconstruct the filename handle (from download_price_lists.py logic)
        safe_vendor = "".join([c if c.isalnum() else "_" for c in vendor])
        
        # We don't know the exact extension (.pdf, .xlsx, .xls) so we check all 3
        found_file = None
        for ext in ['.pdf', '.xlsx', '.xls']:
            filename = f"{safe_vendor}_{contact_num}{ext}"
            potential_path = os.path.join(source_dir, filename)
            if os.path.exists(potential_path):
                found_file = filename
                break
        
        if found_file:
            # Create target directory: State/City
            target_dir = os.path.join(target_root, state, city)
            os.makedirs(target_dir, exist_ok=True)
            
            # Destination path
            dest_path = os.path.join(target_dir, found_file)
            
            try:
                # Copy instead of move for safety initially, or move if user prefers
                # Let's move to clean up the flat folder
                shutil.move(os.path.join(source_dir, found_file), dest_path)
                files_moved += 1
                if files_moved % 100 == 0:
                    print(f"Progress: Organized {files_moved} files...", end="\r")
            except Exception as e:
                print(f"\nError moving {found_file}: {e}")
                errors += 1
        
    print(f"\nOrganization complete!")
    print(f"Successfully moved: {files_moved}")
    print(f"Errors: {errors}")
    print(f"Organized files are located in: output/downloads/price_lists_by_region/")

if __name__ == "__main__":
    CLEAN_CSV = os.path.join('ext_res', 'vendors_sanitized.csv')
    organize_price_lists(CLEAN_CSV)

