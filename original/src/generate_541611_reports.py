import pandas as pd
import os
import json
import shutil
from utils import get_project_root

def generate_541611_reports(states=['VA', 'DC', 'MD', 'National']):
    root = get_project_root()
    metrics_dir = os.path.join(root, "output", "541611_metrics")
    report_dir = os.path.join(root, "output", "541611_reports")
    os.makedirs(report_dir, exist_ok=True)

    for state in states:
        metrics_csv = os.path.join(metrics_dir, f"{state}_541611_Metrics.csv")
        metrics_xlsx = os.path.join(metrics_dir, f"{state}_541611_Metrics.xlsx")
        
        if not os.path.exists(metrics_csv):
            print(f"Skipping {state}: Metrics file not found.")
            continue

        # Copy data files for portability
        shutil.copy2(metrics_csv, os.path.join(report_dir, f"{state}_541611_Role_Metrics.csv"))
        if os.path.exists(metrics_xlsx):
            shutil.copy2(metrics_xlsx, os.path.join(report_dir, f"{state}_541611_Role_Metrics.xlsx"))

        print(f"Generating 541611 reports for {state}...")
        df = pd.read_csv(metrics_csv)
        
        # Dashboard filter logic
        if state == 'National':
            df_display = df[df['Count'] > 1].copy()
            filter_note = f" (Displaying {len(df_display):,} roles with 2+ entries. Niche roles available in Excel.)"
        else:
            df_display = df.copy()
            filter_note = ""

        # Prepare JS Data
        table_data = []
        for _, r in df_display.sort_values('Title_Key').iterrows():
            desc_str = str(r['Descriptions']) if pd.notna(r['Descriptions']) else ""
            descs = [d.strip() for d in desc_str.split("|") if d.strip()][:5]
            desc_html = "<ul>" + "".join([f"<li>{d}</li>" for d in descs])
            if "|" in desc_str:
                total_vars = desc_str.count("|") + 1
                if total_vars > 5:
                    desc_html += f"<li>... and {total_vars-5} more variations in data.</li>"
            desc_html += "</ul>"

            table_data.append({
                "t": str(r['Title_Key']),
                "d_h": desc_html,
                "c": int(r['Count']),
                "m": f"${r['Mean']:,.2f}",
                "mi": f"${r['Min']:,.2f}",
                "ma": f"${r['Max']:,.2f}",
                "me": f"${r['Median']:,.2f}",
                "m_r": float(r['Mean']),
                "mi_r": float(r['Min']),
                "ma_r": float(r['Max']),
                "me_r": float(r['Median'])
            })

        data_js_path = os.path.join(report_dir, f"{state}_541611_data.js")
        with open(data_js_path, 'w', encoding='utf-8') as f:
            f.write(f"const pricingData = {json.dumps(table_data)};")

        # HTML Shell
        html_path = os.path.join(report_dir, f"{state}_541611_Pricing_Full_Report.html")
        html_content = f"""
<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>{state} 541611 Management Consulting Analysis</title>
    <link rel="stylesheet" href="https://cdn.datatables.net/1.13.7/css/jquery.dataTables.min.css">
    <style>
        body {{ font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Helvetica, Arial, sans-serif; background-color: #f6f8fa; margin: 0; padding: 20px; }}
        .header {{ background-color: #24292f; color: white; padding: 2rem; border-radius: 8px 8px 0 0; text-align: center; }}
        .container {{ max-width: 1400px; margin: 0 auto; background: white; padding: 20px; border-radius: 0 0 8px 8px; box-shadow: 0 4px 6px rgba(0,0,0,0.1); }}
        table.dataTable thead {{ background-color: #f0f2f5; }}
        .mean-price {{ font-weight: bold; color: #0969da; }}
        .desc-cell {{ font-size: 0.85rem; color: #57606a; max-width: 400px; overflow: hidden; }}
    </style>
</head>
<body>
    <div class="header">
        <h1>{state} Management Consulting (541611) Pricing</h1>
        <p>{filter_note}</p>
        <div style="margin-top:1.5rem; display: flex; justify-content: center; gap: 10px;">
            <a href="./{state}_541611_Role_Metrics.csv" style="color:white; text-decoration:none; background: rgba(255,255,255,0.1); padding: 8px 16px; border-radius: 6px; border: 1px solid rgba(255,255,255,0.2); font-size: 0.85rem;">📊 CSV</a>
            <a href="./{state}_541611_Role_Metrics.xlsx" style="color:white; text-decoration:none; background: rgba(255,255,255,0.1); padding: 8px 16px; border-radius: 6px; border: 1px solid rgba(255,255,255,0.2); font-size: 0.85rem;">📁 Excel</a>
        </div>
    </div>
    <div class="container">
        <table id="pricingTable" class="display" style="width:100%">
            <thead>
                <tr>
                    <th>Job Title (Normalized)</th>
                    <th>Count</th>
                    <th>Mean Rate</th>
                    <th>Min Rate</th>
                    <th>Max Rate</th>
                    <th>Median Rate</th>
                    <th>Description Variations (Sample)</th>
                </tr>
            </thead>
        </table>
    </div>

    <script src="https://code.jquery.com/jquery-3.7.1.min.js"></script>
    <script src="https://cdn.datatables.net/1.13.7/js/jquery.dataTables.min.js"></script>
    <script src="./{state}_541611_data.js"></script>
    <script>
        $(document).ready(function() {{
            $('#pricingTable').DataTable({{
                data: pricingData,
                deferRender: true,
                pageLength: 25,
                columns: [
                    {{ data: 't' }},
                    {{ data: 'c' }},
                    {{ data: 'm', render: function(data, type, row) {{ return type === 'sort' ? row.m_r : data; }}, className: 'mean-price' }},
                    {{ data: 'mi', render: function(data, type, row) {{ return type === 'sort' ? row.mi_r : data; }} }},
                    {{ data: 'ma', render: function(data, type, row) {{ return type === 'sort' ? row.ma_r : data; }} }},
                    {{ data: 'me', render: function(data, type, row) {{ return type === 'sort' ? row.me_r : data; }} }},
                    {{ data: 'd_h', className: 'desc-cell' }}
                ],
                order: [[1, 'desc']]
            }});
        }});
    </script>
</body>
</html>
"""
        with open(html_path, 'w', encoding='utf-8') as f:
            f.write(html_content)
        print(f"  Generated dashboard: {html_path}")

if __name__ == "__main__":
    generate_541611_reports(['VA', 'DC', 'MD', 'National'])

