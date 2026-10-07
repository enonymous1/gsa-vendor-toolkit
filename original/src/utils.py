import pandas as pd
import os

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

def get_project_root():
    return os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

def sanitize_df(df):
    # Rename ambiguous columns
    df = df.rename(columns={
        'Unnamed: 39': 'Has_T_and_C_Flag',
        'Unnamed: 40': 'Has_Price_List_Flag'
    })

    # Sanitize categorical values
    cols_to_map = [col for col in df.columns if col not in [
        'Vendor', 'Address 1', 'Address 2', 'City', 'Phone', 'Email', 'URL', 
        'SAM UEI', 'Contact #', 'T&Cs', 'Price List', 'View Catalog', 'Zip'
    ]]
    
    for col in cols_to_map:
        if col in df.columns:
            df[col] = df[col].apply(lambda x: GSA_MAP.get(str(x), x) if pd.notnull(x) else x)
            
    return df

