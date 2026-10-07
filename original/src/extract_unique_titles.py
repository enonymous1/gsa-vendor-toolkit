import pandas as pd
import os
import json
from utils import get_project_root

def extract_unique_titles(states=['VA', 'DC']):
    root = get_project_root()
    input_dir = os.path.join(root, "output", "merged_filtered")
    output_dir = os.path.join(root, "output", "unique_titles")
    os.makedirs(output_dir, exist_ok=True)
    
    summary_report = ["# Unique IT Titles (SIN 54151S)\n"]

    for state in states:
        input_csv = os.path.join(input_dir, f"{state}_SIN_54151S_Only.csv")
        if not os.path.exists(input_csv):
            print(f"Skipping {state}: Filtered file not found.")
            continue

        print(f"Extracting unique titles for {state}...")
        df = pd.read_csv(input_csv, low_memory=False)
        
        if 'Title' not in df.columns:
            print(f"  Error: 'Title' column not found in {state} file.")
            continue

        # Get unique values, sorted, case-normed
        # We'll preserve original case but group by upper for uniqueness
        unique_titles = df['Title'].astype(str).str.strip().unique().tolist()
        unique_titles.sort()
        
        # Save as JSON for programmatic use
        json_out = os.path.join(output_dir, f"{state}_Unique_IT_Titles.json")
        with open(json_out, 'w') as f:
            json.dump(unique_titles, f, indent=4)
            
        # Add to summary
        count = len(unique_titles)
        summary_report.append(f"## {state}")
        summary_report.append(f"- **Total Rows (IT Only)**: {len(df)}")
        summary_report.append(f"- **Unique Titles**: {count}")
        summary_report.append(f"- **JSON List**: [{os.path.basename(json_out)}]({os.path.basename(json_out)})\n")
        
        print(f"  Found {count} unique IT titles. Saved to {json_out}")

    # Write summary report
    report_path = os.path.join(output_dir, "unique_titles_summary.md")
    with open(report_path, 'w') as f:
        f.write("\n".join(summary_report))
    
    print(f"\nSummary report generated at: {report_path}")

if __name__ == "__main__":
    extract_unique_titles(['VA', 'DC'])

