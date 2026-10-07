import pandas as pd
import os
import json
import shutil
from utils import get_project_root

def generate_readable_reports(states=['VA', 'DC', 'National']):
    root = get_project_root()
    metrics_dir = os.path.join(root, "output", "it_title_analysis")
    report_dir = os.path.join(root, "output", "reports")
    os.makedirs(report_dir, exist_ok=True)

    for state in states:
        metrics_csv = os.path.join(metrics_dir, f"{state}_IT_Role_Metrics.csv")
        metrics_xlsx = os.path.join(metrics_dir, f"{state}_IT_Role_Metrics.xlsx")
        
        if not os.path.exists(metrics_csv):
            print(f"Skipping {state}: Metrics file not found.")
            continue

        # Copy data files to report directory for easier sharing
        shutil.copy2(metrics_csv, os.path.join(report_dir, f"{state}_IT_Role_Metrics.csv"))
        if os.path.exists(metrics_xlsx):
            shutil.copy2(metrics_xlsx, os.path.join(report_dir, f"{state}_IT_Role_Metrics.xlsx"))

        print(f"Generating optimized high-performance reports for {state}...")
        df = pd.read_csv(metrics_csv)
        
        original_count = len(df)
        if state == 'National':
            # National filter: count > 1 as requested
            df_display = df[df['Count'] > 1].copy()
            filter_note = f" (Displaying {len(df_display):,} roles with 2+ entries. Niche roles available in Excel.)"
        else:
            df_display = df.copy()
            filter_note = ""

        # 1. Generate Markdown Summary (Simple overview)
        md_path = os.path.join(report_dir, f"{state}_IT_Pricing_Executive_Summary.md")
        with open(md_path, 'w', encoding='utf-8') as f:
            f.write(f"# IT Pricing Executive Summary: {state}\n\n")
            f.write(f"- **Total Unique Roles**: {original_count:,}\n")
            f.write(f"- **Dashboard Filter**: {filter_note if filter_note else 'None'}\n\n")
            f.write("## 🏆 Top 10 Roles by Frequency\n")
            f.write("| Job Title | Count | Mean Price |\n| :--- | :---: | :---: |\n")
            for _, row in df.head(10).iterrows():
                f.write(f"| {row['Title_Key']} | {row['Count']} | ${row['Mean_Price']:,.2f} |\n")
            f.write(f"\n[View Full Interactive Report](./{state}_IT_Pricing_Full_Report.html)")

        # 2. Prepare Data for High-Performance JS-based Dashboard
        def get_description_html(desc_str):
            if pd.isna(desc_str) or not str(desc_str).strip():
                return {"count": 0, "html": "<i>No description available.</i>"}
            descs = [d.strip() for d in str(desc_str).split("|") if d.strip()]
            
            # Limit to top 5 as requested
            display_descs = descs[:5]
            html = "<ul>" + "".join([f"<li>{d}</li>" for d in display_descs])
            if len(descs) > 5:
                html += f"<li>... and {len(descs)-5} more variations in the source data.</li>"
            html += "</ul>"
            return {"count": len(descs), "html": html}

        table_data = []
        for _, r in df_display.sort_values('Title_Key').iterrows():
            desc_info = get_description_html(r.get('Merged_Descriptions', ''))
            table_data.append({
                "t": str(r['Title_Key']),
                "d_h": desc_info['html'],
                "d_c": desc_info['count'],
                "c": int(r['Count']),
                "m": f"${r['Mean_Price']:,.2f}",
                "mi": f"${r['Min_Price']:,.2f}",
                "ma": f"${r['Max_Price']:,.2f}",
                "me": f"${r['Median_Price']:,.2f}",
                "r": f"${r['Price_Range']:,.2f}" if r['Count'] > 1 else "-",
                # Raw values for sorting
                "m_r": float(r['Mean_Price']),
                "mi_r": float(r['Min_Price']),
                "ma_r": float(r['Max_Price']),
                "me_r": float(r['Median_Price']),
                "r_r": float(r['Price_Range']) if r['Count'] > 1 else -1.0
            })

        # Save data as a external JS file to minimize HTML size and improve load speed
        data_js_filename = f"{state}_data.js"
        data_js_path = os.path.join(report_dir, data_js_filename)
        with open(data_js_path, 'w', encoding='utf-8') as f:
            f.write(f"const pricingData = {json.dumps(table_data)};")

        # 3. Generate the \"Thin shell\" HTML Wrapper
        html_path = os.path.join(report_dir, f"{state}_IT_Pricing_Full_Report.html")
        html_content = f"""
<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>{state} IT Pricing Analysis</title>
    <link rel="stylesheet" href="https://cdn.datatables.net/1.13.7/css/jquery.dataTables.min.css">
    <link href="https://fonts.googleapis.com/css2?family=Inter:wght@400;600;700&display=swap" rel="stylesheet">
    <style>
        :root {{ --p: #1e3a8a; --s: #f8fafc; --t: #64748b; }}
        body {{ font-family: 'Inter', sans-serif; background: var(--s); margin: 0; color: #1e293b; }}
        .header {{ background: #1e3a8a; color: white; padding: 2.5rem 1rem; text-align: center; }}
        .header h1 {{ margin: 0; font-size: 2rem; }}
        .header p {{ margin: 0.5rem 0 0; opacity: 0.9; }}
        .container {{ max-width: 1400px; margin: -2rem auto 2rem; padding: 1.5rem; background: white; border-radius: 12px; box-shadow: 0 10px 15px -3px rgba(0,0,0,0.1); }}
        
        .title-txt {{ font-weight: 700; color: var(--p); font-size: 0.95rem; }}
        .badge {{ background: #eff6ff; color: var(--p); padding: 4px 10px; border-radius: 9999px; font-size: 0.75rem; font-weight: 700; border: 1px solid #dbeafe; }}
        .price {{ font-family: 'SFMono-Regular', Consolas, 'Liberation Mono', Menlo, monospace; font-weight: 600; color: #0f172a; }}
        
        .desc-box {{ border: 1px solid #e2e8f0; border-radius: 8px; margin-top: 8px; background: #fcfcfd; }}
        .desc-box summary {{ padding: 8px 12px; cursor: pointer; font-size: 0.8rem; color: var(--t); font-weight: 500; list-style: none; }}
        .desc-box summary::-webkit-details-marker {{ display: none; }}
        .desc-box summary:hover {{ background: #f1f5f9; }}
        .desc-box[open] summary {{ border-bottom: 1px solid #e2e8f0; }}
        .desc-list {{ padding: 10px 15px; font-size: 0.8rem; line-height: 1.5; color: #475569; }}
        .desc-list ul {{ margin: 0; padding-left: 20px; }}
        
        table.dataTable.compact thead th {{ background: #f1f5f9; padding: 12px 10px; border-bottom: 2px solid #e2e8f0; font-weight: 700; text-transform: uppercase; font-size: 0.7rem; letter-spacing: 0.05em; color: #475569; }}
        .dt-right {{ text-align: right !important; }}
    </style>
</head>
<body>
    <div class="header">
        <h1>{state} IT Pricing Benchmark</h1>
        <p>{filter_note}</p>
        <div style="margin-top:1.5rem; display: flex; justify-content: center; gap: 10px;">
            <a href="./{state}_IT_Role_Metrics.csv" style="color:white; text-decoration:none; background: rgba(255,255,255,0.1); padding: 8px 16px; border-radius: 6px; border: 1px solid rgba(255,255,255,0.2); font-size: 0.85rem;">📊 Download CSV</a>
            <a href="./{state}_IT_Role_Metrics.xlsx" style="color:white; text-decoration:none; background: rgba(255,255,255,0.1); padding: 8px 16px; border-radius: 6px; border: 1px solid rgba(255,255,255,0.2); font-size: 0.85rem;">📁 Download Excel</a>
        </div>
    </div>
    <div class="container">
        <table id="priceTable" class="display compact hover" style="width:100%">
            <thead>
                <tr>
                    <th>Role & Descriptions</th>
                    <th>Count</th>
                    <th>Mean</th>
                    <th>Min</th>
                    <th>Max</th>
                    <th>Median</th>
                    <th>Range</th>
                </tr>
            </thead>
            <tbody></tbody>
        </table>
    </div>

    <script src="https://code.jquery.com/jquery-3.7.1.min.js"></script>
    <script src="https://cdn.datatables.net/1.13.7/js/jquery.dataTables.min.js"></script>
    <script src="./{data_js_filename}"></script>
    <script>
        $(document).ready(function() {{
            $('#priceTable').DataTable({{
                data: pricingData,
                deferRender: true,
                pageLength: 50,
                order: [[ 0, "asc" ]],
                columns: [
                    {{ 
                        data: "t",
                        width: "40%",
                        render: function(data, type, row) {{
                            if (type === 'display') {{
                                return '<div class="title-txt">' + data + '</div>' +
                                       '<details class="desc-box">' +
                                       '<summary>⊕ ' + row.d_c + ' Job Description Variations</summary>' +
                                       '<div class="desc-list">' + row.d_h + '</div>' +
                                       '</details>';
                            }}
                            return data;
                        }}
                    }},
                    {{ 
                        data: "c", 
                        className: "dt-right",
                        render: d => '<span class="badge">' + d + '</span>'
                    }},
                    {{ data: "m", className: "dt-right price", orderData: [7] }},
                    {{ data: "mi", className: "dt-right price", orderData: [8] }},
                    {{ data: "ma", className: "dt-right price", orderData: [9] }},
                    {{ data: "me", className: "dt-right price", orderData: [10] }},
                    {{ data: "r", className: "dt-right price", orderData: [11] }},
                    {{ data: "m_r", visible: false }},
                    {{ data: "mi_r", visible: false }},
                    {{ data: "ma_r", visible: false }},
                    {{ data: "me_r", visible: false }},
                    {{ data: "r_r", visible: false }}
                ],
                language: {{
                    searchPlaceholder: "Search roles...",
                    search: ""
                }}
            }});
        }});
    </script>
</body>
</html>
"""
        with open(html_path, 'w', encoding='utf-8') as f:
            f.write(html_content)
        print(f"  Successfully generated {state} report and data file.")

if __name__ == "__main__":
    generate_readable_reports()

