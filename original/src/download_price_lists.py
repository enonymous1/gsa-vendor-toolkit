import pandas as pd
import os
import requests
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from threading import Lock
from utils import get_project_root

def download_item(row, download_dir):
    """
    Downloads a single price list item and returns the result.
    """
    url = row['Price List']
    vendor = str(row['Vendor']).strip()
    contact_num = str(row['Contact #']).strip()
    
    ext = ".xlsx"
    if ".pdf" in url.lower(): ext = ".pdf"
    elif ".xls" in url.lower() and ".xlsx" not in url.lower(): ext = ".xls"
    
    safe_vendor = "".join([c if c.isalnum() else "_" for c in vendor])
    filename = f"{safe_vendor}_{contact_num}{ext}"
    filepath = os.path.join(download_dir, filename)

    # Check if file exists
    if os.path.exists(filepath):
        return contact_num, 'Success', ''

    success = False
    error_msg = ""
    max_retries = 3
    retry_count = 0
    
    while retry_count < max_retries and not success:
        try:
            # Use a slightly longer timeout for concurrent downloads
            response = requests.get(url, timeout=20, stream=True)
            if response.status_code == 200:
                with open(filepath, 'wb') as f:
                    for chunk in response.iter_content(chunk_size=8192):
                        f.write(chunk)
                success = True
            else:
                error_msg = f"HTTP {response.status_code}"
                retry_count += 1
                time.sleep(1)
        except Exception as e:
            error_msg = str(e)
            retry_count += 1
            time.sleep(1)
    
    if success:
        return contact_num, 'Success', ''
    else:
        return contact_num, 'Failed', error_msg

def download_price_lists(sanitized_file, limit=None, max_workers=10):
    root = get_project_root()
    data_path = os.path.join(root, sanitized_file)
    
    if not os.path.exists(data_path):
        print(f"Error: Sanitized file not found. Run data_sanitizer.py first.")
        return

    # Create directories
    download_dir = os.path.join(root, "output", "downloads", "price_lists")
    os.makedirs(download_dir, exist_ok=True)
    
    manifest_path = os.path.join(root, "output", "summaries", "download_manifest.csv")
    os.makedirs(os.path.dirname(manifest_path), exist_ok=True)

    df = pd.read_csv(data_path, dtype={'Contact #': str})
    to_download = df[df['Price List'].notna()].copy()
    
    # Initialize or load manifest
    if os.path.exists(manifest_path):
        manifest_df = pd.read_csv(manifest_path, dtype={'Contact #': str})
        # Merge to keep track of previous attempts
        to_download = to_download.merge(manifest_df[['Contact #', 'Download_Status', 'Last_Error']], on='Contact #', how='left')
        
        # Fill NaNs from merge
        to_download['Download_Status'] = to_download['Download_Status'].fillna('Pending').astype(str)
        to_download['Last_Error'] = to_download['Last_Error'].fillna('').astype(str)
        
        # Print current Progress
        stats = to_download['Download_Status'].value_counts()
        print(f"Current Progress: {stats.get('Success', 0)} Successes, {stats.get('Failed', 0)} Failures, {stats.get('Pending', 0)} Pending.")
    else:
        to_download['Download_Status'] = 'Pending'
        to_download['Last_Error'] = ''
        to_download['Download_Status'] = to_download['Download_Status'].astype(str)
        to_download['Last_Error'] = to_download['Last_Error'].astype(str)

    if limit:
        pending = to_download[to_download['Download_Status'] != 'Success'].head(limit)
        print(f"Limiting download to first {limit} pending entries.")
    else:
        pending = to_download[to_download['Download_Status'] != 'Success']

    total = len(pending)
    if total == 0:
        print("All files already downloaded according to manifest.")
        return

    print(f"Starting/Resuming concurrent download of {total} price lists (Workers: {max_workers})...")
    
    manifest_lock = Lock()
    count = 0

    with ThreadPoolExecutor(max_workers=max_workers) as executor:
        futures = {executor.submit(download_item, row, download_dir): row for _, row in pending.iterrows()}
        
        for future in as_completed(futures):
            contact_num, status, error = future.result()
            vendor = futures[future]['Vendor']
            
            with manifest_lock:
                to_download.loc[to_download['Contact #'] == contact_num, 'Download_Status'] = status
                to_download.loc[to_download['Contact #'] == contact_num, 'Last_Error'] = error
                count += 1
                
                # Print progress update
                if status == 'Success':
                    print(f"[{count}/{total}] Downloaded: {vendor}", end="\r")
                else:
                    print(f"\n[{count}/{total}] Failed: {vendor} - {error}")
                
                # Save manifest every 10 downloads or at the end
                if count % 10 == 0 or count == total:
                    to_download[['Vendor', 'Contact #', 'Price List', 'Download_Status', 'Last_Error']].to_csv(manifest_path, index=False)

    print(f"\nDownload process complete. Manifest updated at: output/summaries/download_manifest.csv")

if __name__ == "__main__":
    CLEAN_CSV = os.path.join('ext_res', 'vendors_sanitized.csv')
    # Increased workers for parallel downloads
    download_price_lists(CLEAN_CSV, limit=None, max_workers=10)

