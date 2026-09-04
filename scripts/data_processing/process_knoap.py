import pandas as pd
import os
import glob

def process_knoap2020_data(raw_dir='../../data/raw/KNOAP2020', processed_dir='../../data/processed'):
    """
    Processes the raw KNOAP2020 benchmark dataset.
    Useful as an OA progression/prediction benchmark and for feature selection.
    """
    print(f"Looking for KNOAP2020 datasets in {os.path.abspath(raw_dir)}...")
    
    os.makedirs(processed_dir, exist_ok=True)
    
    all_files = glob.glob(os.path.join(raw_dir, '*.csv')) + glob.glob(os.path.join(raw_dir, '*.txt'))
    if not all_files:
        print(f"No CSV or TXT files found in {raw_dir}. Please ensure you have downloaded the KNOAP2020 dataset and placed the files in this directory.")
        return
        
    print(f"Found {len(all_files)} files. Parsing...")
    
    # Typically KNOAP has a clinical risk factors file and a labels file
    # We will assume they are named appropriately or are just separate CSVs to be merged on ID
    
    dataframes = []
    for file in all_files:
        try:
            df = pd.read_csv(file, sep=None, engine='python')
            
            # Standardize ID column name (KNOAP usually uses Knee_ID or Patient_ID)
            id_col = next((col for col in df.columns if col.upper() in ['ID', 'KNEE_ID', 'PATIENT_ID', 'SUBJECT_ID']), None)
            
            if id_col:
                df = df.rename(columns={id_col: 'SUBJECT_ID'})
                dataframes.append(df)
            else:
                print(f"Skipping {os.path.basename(file)}: No recognized ID column found.")
        except Exception as e:
            print(f"Error processing {file}: {e}")
            
    if not dataframes:
        print("No valid datasets to process.")
        return
        
    merged_df = dataframes[0]
    for df in dataframes[1:]:
        cols_to_use = df.columns.difference(merged_df.columns).tolist() + ['SUBJECT_ID']
        merged_df = pd.merge(merged_df, df[cols_to_use], on='SUBJECT_ID', how='outer')
        
    print(f"Merged KNOAP2020 dataset shape: {merged_df.shape}")
    
    # Check if target variable (incident OA) exists
    target_cols = [col for col in merged_df.columns if 'INCIDENT' in col.upper() or 'PROGRESSION' in col.upper() or 'OA' in col.upper()]
    if target_cols:
        print(f"Found potential target columns: {target_cols}")
    else:
        print("Warning: Did not find obvious target columns. If this is the blinded test set, labels might be missing.")
        
    # Clean up empty columns
    threshold = len(merged_df) * 0.8
    cleaned_df = merged_df.dropna(axis=1, thresh=len(merged_df) - threshold)
    
    output_path = os.path.join(processed_dir, 'knoap2020_cleaned.csv')
    cleaned_df.to_csv(output_path, index=False)
    print(f"Successfully processed KNOAP2020 data and saved to {output_path}")
    print(f"Final shape: {cleaned_df.shape}")

if __name__ == "__main__":
    process_knoap2020_data()
