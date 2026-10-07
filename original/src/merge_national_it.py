import pandas as pd
import os
import glob
from utils import get_project_root

def merge_national_it_price_lists():
    root = get_project_root()
    manifest_path = os.path.join(root, "output", "summaries", "download_manifest.csv")
    vendors_path = os.path.join(root, "ext_res", "vendors_sanitized.csv")
    base_dir = os.path.join(root, "output", "downloads", "price_lists_by_region")
    output_dir = os.path.join(root, "output", "merged_national")
    os.makedirs(output_dir, exist_ok=True)

    if not os.path.exists(manifest_path) or not os.path.exists(vendors_path):
        print("Required CSV files (manifest/vendors) not found.")
        return

    print("Loading data catalogs...")
    manifest = pd.read_csv(manifest_path)
    vendors = pd.read_csv(vendors_path)

    # Cast Contact # to string for joining
    manifest['Contact #'] = manifest['Contact #'].astype(str)
    vendors['Contact #'] = vendors['Contact #'].astype(str)

    # Join manifest with vendors to get State/City and SIN info
    # Note: State/City in manifest is from the download process, 
    # but vendors CSV has them too. We need the path mapping.
    df_merged = manifest.merge(
        vendors[['Vendor', 'Contact #', 'Category', 'State', 'City']], 
        on=['Vendor', 'Contact #'], 
        how='left'
    )

    # Filter for Success and SIN 54151S
    it_df = df_merged[
        (df_merged['Download_Status'] == 'Success') & 
        (df_merged['Category'].str.contains('54151S', na=False))
    ].copy()

    print(f"Found {len(it_df)} successful IT (54151S) downloads to merge.")

    all_data = []
    files_processed = 0
    files_skipped = 0

    for idx, row in it_df.iterrows():
        vendor_safe = "".join([c if c.isalnum() else "_" for c in str(row['Vendor'])])
        filename = f"{vendor_safe}_{row['Contact #']}.xlsx"
        
        # Build path based on State/City from the vendor record (as used in organization)
        state = str(row['State']).strip().upper() if pd.notna(row['State']) else "UNKNOWN"
        city = str(row['City']).strip() if pd.notna(row['City']) else "UNKNOWN"
        
        file_path = os.path.join(base_dir, state, city, filename)
        
        # Try .xls if .xlsx doesn't exist
        if not os.path.exists(file_path):
            file_path = file_path.replace(".xlsx", ".xls")

        if not os.path.exists(file_path):
            # Try to find it manually in case naming was different
            files_skipped += 1
            continue

        try:
            xl = pd.ExcelFile(file_path)
            target_sheet = None
            for s in xl.sheet_names:
                if s.strip().lower() == "price list":
                    target_sheet = s
                    break
            
            if target_sheet:
                df = pd.read_excel(file_path, sheet_name=target_sheet)
                
                # Add Metadata
                df['Source_Vendor'] = row['Vendor']
                df['Source_Contact_Num'] = row['Contact #']
                df['Source_State'] = state
                df['Source_City'] = city
                
                # Basic cleaning
                df = df.dropna(how='all').dropna(axis=1, how='all')
                
                all_data.append(df)
                files_processed += 1
                if files_processed % 50 == 0:
                    print(f"  Processed {files_processed} files...")
            else:
                files_skipped += 1
        except Exception as e:
            # print(f"Error reading {filename}: {e}")
            files_skipped += 1

    print(f"\nFinished merging: {files_processed} files processed, {files_skipped} skipped/missing.")

    if all_data:
        print("Combining all data (this may take a moment)...")
        master_df = pd.concat(all_data, ignore_index=True, sort=False)
        
        # Save to CSV
        csv_out = os.path.join(output_dir, "National_IT_Master_Price_List.csv")
        master_df.to_csv(csv_out, index=False)
        print(f"Saved National Master: {csv_out} ({len(master_df):,} rows)")
    else:
        print("No data found to merge.")

if __name__ == "__main__":
    merge_national_it_price_lists()

