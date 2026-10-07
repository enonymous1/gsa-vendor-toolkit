import pandas as pd
import os
import requests
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from utils import get_project_root

def download_item(row, download_dir):
    url = row['Price List']
    vendor = str(row['Vendor']).strip()
    contact_num = str(row['Contact #']).strip()
    
    ext = ".xlsx"
    if ".pdf" in url.lower(): ext = ".pdf"
    elif ".xls" in url.lower() and ".xlsx" not in url.lower(): ext = ".xls"
    elif ".doc" in url.lower(): ext = ".doc"
    
    safe_vendor = "".join([c if c.isalnum() else "_" for c in vendor])[:50]
    filename = f"{safe_vendor}_{contact_num}{ext}"
    filepath = os.path.join(download_dir, filename)

    if os.path.exists(filepath):
        return contact_num, 'Success', ''

    success = False
    error_msg = ""
    max_retries = 2
    retry_count = 0
    
    while retry_count < max_retries and not success:
        try:
            response = requests.get(url, timeout=15, stream=True)
            if response.status_code == 200:
                with open(filepath, 'wb') as f:
                    for chunk in response.iter_content(chunk_size=8192):
                        f.write(chunk)
                success = True
            else:
                error_msg = f"HTTP {response.status_code}"
                retry_count += 1
                time.sleep(0.5)
        except Exception as e:
            error_msg = str(e)
            retry_count += 1
            time.sleep(0.5)
    
    if success:
        return contact_num, 'Success', ''
    else:
        return contact_num, 'Failed', error_msg

def download_541611(sanitized_file, limit=None, max_workers=15):
    root = get_project_root()
    data_path = os.path.join(root, sanitized_file)
    
    # New directory for these specific price lists
    download_dir = os.path.join(root, "output", "downloads", "541611_price_lists")
    os.makedirs(download_dir, exist_ok=True)
    
    manifest_path = os.path.join(root, "output", "summaries", "download_541611_manifest.csv")
    os.makedirs(os.path.dirname(manifest_path), exist_ok=True)

    df = pd.read_csv(data_path, dtype={'Contact #': str}, low_memory=False)
    to_download = df[df['Price List'].notna()].copy()
    
    if limit:
        to_download = to_download.head(limit)

    to_download['Download_Status'] = 'Pending'
    to_download['Last_Error'] = ''

    print(f"Attempting to download {len(to_download)} price lists for 541611...")
    
    with ThreadPoolExecutor(max_workers=max_workers) as executor:
        future_map = {executor.submit(download_item, row, download_dir): idx for idx, row in to_download.iterrows()}
        
        for future in as_completed(future_map):
            idx = future_map[future]
            contact, status, error = future.result()
            to_download.loc[idx, 'Download_Status'] = status
            to_download.loc[idx, 'Last_Error'] = error
            if status == 'Failed':
                print(f"  FAILED {contact}: {error}")

    to_download.to_csv(manifest_path, index=False)
    print(f"Manifest written to: {manifest_path}")
    print(f"Successes: {len(to_download[to_download['Download_Status']=='Success'])}")

if __name__ == "__main__":
    CLEAN_CSV = os.path.join('ext_res', 'vendors_541611_sanitized.csv')
    # Limit to 3000 to keep it manageable and fast for this run
    download_541611(CLEAN_CSV, limit=3000)

