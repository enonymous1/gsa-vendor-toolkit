import pandas as pd
import os
from utils import get_project_root

def generate_exports(sanitized_file):
    root = get_project_root()
    data_path = os.path.join(root, sanitized_file)
    
    if not os.path.exists(data_path):
        print(f"Error: Sanitized file not found. Run data_sanitizer.py first.")
        return

    df = pd.read_csv(data_path)
    
    # Create subdirectories for organization
    output_base = os.path.join(root, "output")
    dirs = {
        "price_lists": os.path.join(output_base, "price_lists"),
        "regional": os.path.join(output_base, "regional"),
        "summaries": os.path.join(output_base, "summaries")
    }
    for d in dirs.values():
        os.makedirs(d, exist_ok=True)

    # Identify Socio-Economic columns
    se_cols = [c for c in df.columns if 'Small Business' in c or 'Owned' in c or '8(a)' in c or 'Hub Zone' in c or 'HUBZone' in c]

    # 1. Price List Export (All)
    price_list_df = df[df['Has_Price_List_Flag'] == 'Yes']
    price_list_df.to_csv(os.path.join(dirs["price_lists"], "all_vendors_with_price_list.csv"), index=False)
    print(f"Exported all price list vendors.")

    # 2. Regional Exports
    unique_states = df['State'].dropna().unique()
    for state_code in unique_states:
        state_dir = os.path.join(dirs["regional"], state_code)
        os.makedirs(state_dir, exist_ok=True)
        
        state_df = df[df['State'] == state_code]
        state_df.to_csv(os.path.join(state_dir, f"all_vendors_{state_code}.csv"), index=False)
        
        # State + Price List
        state_pl_df = state_df[state_df['Has_Price_List_Flag'] == 'Yes']
        if not state_pl_df.empty:
            state_pl_df.to_csv(os.path.join(state_dir, f"vendors_{state_code}_with_price_list.csv"), index=False)
        
        # 3. Deep Dive for VA and DC (Socio-Economic + Price List)
        if state_code in ['VA', 'DC'] and not state_pl_df.empty:
            se_dir = os.path.join(state_dir, "socio_economic_with_price_list")
            os.makedirs(se_dir, exist_ok=True)
            
            for col in se_cols:
                subset = state_pl_df[state_pl_df[col].notna()]
                if not subset.empty:
                    safe_col_name = "".join([c if c.isalnum() else "_" for c in col])
                    subset.to_csv(os.path.join(se_dir, f"{state_code}_PL_{safe_col_name}.csv"), index=False)
        
        # 4. Regional Summaries
        generate_regional_summary(state_df, state_code, dirs["summaries"], se_cols)
    
    print(f"Exports and summaries completed in /output/ regional subdirectories.")

def generate_regional_summary(df, state_code, output_dir, se_cols):
    summary_path = os.path.join(output_dir, f"summary_{state_code}.md")
    
    total = len(df)
    pl_count = len(df[df['Has_Price_List_Flag'] == 'Yes'])
    
    with open(summary_path, "w", encoding="utf-8") as f:
        f.write(f"# Regional Summary: {state_code}\n")
        f.write(f"- **Total Vendors:** {total}\n")
        f.write(f"- **Vendors with Price List:** {pl_count} ({ (pl_count/total*100) if total > 0 else 0:.1f}%)\n\n")
        
        if 'City' in df.columns:
            f.write("## Top Cities\n")
            counts = df['City'].value_counts().head(10)
            for city, count in counts.items():
                f.write(f"- {city}: {count}\n")
        
        f.write("\n## Socio-Economic Breakdown (Price List Preferred)\n")
        # Check counts for each indicator specifically for those with price lists
        pl_df = df[df['Has_Price_List_Flag'] == 'Yes']
        for col in se_cols:
            total_se = df[col].count()
            pl_se = pl_df[col].count()
            if total_se > 0:
                f.write(f"- **{col}**: {total_se} total ({pl_se} with Price List)\n")

if __name__ == "__main__":
    generate_exports(os.path.join('ext_res', 'vendors_sanitized.csv'))

