import pandas as pd
import json
import os
import sys

def run_audit(file_path):
    # Base directory is the project root (one level up from /src)
    project_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    
    # Resolve absolute path for input file
    if not os.path.isabs(file_path):
        data_path = os.path.join(project_root, file_path)
    else:
        data_path = file_path
        
    if not os.path.exists(data_path):
        print(f"Error: File not found at {data_path}")
        return

    # GSA Code Mapping for better readability
    GSA_MAP = {
        's': 'Small Business',
        'o': 'Other Than Small Business',
        'w': 'Women Owned',
        'wo': 'Women Owned (WOSB)',
        'ed': 'Women Owned (EDWOSB)',
        'v': 'Veteran Owned',
        'dv': 'Service Disabled Veteran Owned',
        'd': 'Small Disadv',
        '8a': '8(a)',
        '8aS': '8(a) Sole Source Pool',
        'h': 'HUBZone',
        'to': 'Tribally Owned',
        'ai': 'American Indian Owned',
        'anc': 'Alaskan Native Corporation Owned',
        'nho': 'Native Hawaiian Organization Owned',
        '8ajv': '8(a) Joint Venture Eligible',
        'wojv': 'Women Owned Joint Venture Eligible',
        'dvjv': 'Service Disabled Veteran Owned Joint Venture Eligible',
        'hjv': 'HUBZone Joint Venture Eligible',
        'Y': 'Yes',
        'N': 'No'
    }

    try:
        # Define and create output directories relative to project root
        output_dir = os.path.join(project_root, "output")
        selections_dir = os.path.join(output_dir, "column_selections")
        os.makedirs(selections_dir, exist_ok=True)
        
        # 1. Use pandas to read the CSV file
        df = pd.read_csv(data_path)

        # Rename the ambiguous "Unnamed" columns
        df = df.rename(columns={
            'Unnamed: 39': 'Has_T_and_C_Flag',
            'Unnamed: 40': 'Has_Price_List_Flag'
        })

        summary_lines = []
        summary_lines.append("# DATA AUDIT SUMMARY")
        
        # 3a. Total row count
        summary_lines.append(f"\n**Total Row Count:** {len(df)}")

        if 'Price List' in df.columns:
            price_list_count = df['Price List'].count()
            summary_lines.append(f"**Vendors with Price List:** {price_list_count}")

        # Geographic Focus: VA & DC
        summary_lines.append("\n## Geographic Focus: VA & DC")
        if 'State' in df.columns:
            va_vendors = df[df['State'] == 'VA']
            dc_vendors = df[df['State'] == 'DC']
            
            summary_lines.append(f"### Virginia (VA)")
            summary_lines.append(f"- **Total VA Vendors:** {len(va_vendors)}")
            if not va_vendors.empty and 'City' in df.columns:
                summary_lines.append("- **Breakdown by City (Top 15):**")
                city_counts = va_vendors['City'].value_counts().head(15)
                for city, count in city_counts.items():
                    summary_lines.append(f"  - {city}: {count}")

            summary_lines.append(f"\n### Washington DC (DC)")
            summary_lines.append(f"- **Total DC Vendors:** {len(dc_vendors)}")

        # 3b. Numbered list of Column Headers with counts
        summary_lines.append("\n## Column Headers (Non-Null Values)")
        for i, col in enumerate(df.columns, 1):
            val_count = df[col].count()
            summary_lines.append(f"{i}. {col} ({val_count} entries)")

        # Unique Selections Generation
        skip_columns = [
            'Vendor', 'Address 1', 'Address 2', 'Phone', 'Email', 'URL', 
            'SAM UEI', 'Contact #', 'T&Cs', 'Price List', 'View Catalog', 'Zip'
        ]
        
        summary_lines.append("\n## Categorical Values (Exported to /output/column_selections/)")
        
        for col in df.columns:
            if col in skip_columns:
                continue
                
            unique_raw = df[col].dropna().unique()
            if 0 < len(unique_raw) <= 150:
                # Map values if they exist in GSA_MAP, else keep original
                mapped_vals = sorted([GSA_MAP.get(str(v), str(v)) for v in unique_raw])
                
                summary_lines.append(f"- **{col}**: {len(mapped_vals)} unique values found.")
                
                # Create a safe filename and export to JSON
                safe_name = "".join([c if c.isalnum() else "_" for c in col])
                selection_path = os.path.join(selections_dir, f"{safe_name}.json")
                
                with open(selection_path, "w", encoding="utf-8") as sel_f:
                    json.dump({
                        "column": col,
                        "unique_count": len(mapped_vals),
                        "values": mapped_vals
                    }, sel_f, indent=4)

        # 3c. First 3 rows in JSON format
        summary_lines.append("\n## First 3 Rows (Sample Data)")
        first_3_rows = df.head(3).to_dict(orient='records')
        summary_lines.append("```json")
        summary_lines.append(json.dumps(first_3_rows, indent=4))
        summary_lines.append("```")

        # Write summary file
        output_path = os.path.join(output_dir, "audit_summary.md")
        with open(output_path, "w", encoding="utf-8") as f:
            f.write("\n".join(summary_lines))
        
        print(f"Audit completed. Summary saved to: {output_path}")
        print(f"Selection JSONs saved to: {selections_dir}")

    except Exception as e:
        print(f"An error occurred during audit: {e}")

if __name__ == "__main__":
    # Path relative to project root
    CSV_PATH = os.path.join('ext_res', '2026_02_12_04_10_24.csv')
    run_audit(CSV_PATH)

if __name__ == "__main__":
    CSV_PATH = os.path.join('ext_res', '2026_02_12_04_10_24.csv')
    run_audit(CSV_PATH)

