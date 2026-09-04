import pandas as pd
import os
import glob

def process_oai_data():
    base_dir = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
    raw_dir = os.path.join(base_dir, 'data', 'raw', 'OAI')
    processed_dir = os.path.join(base_dir, 'data', 'processed')
    """
    Processes the raw OAI dataset to extract Anthropometry, Clinical information,
    Pain, Physical activity, Physical performance, and Longitudinal information.
    """
    print(f"Looking for OAI datasets in {os.path.abspath(raw_dir)}...")
    
    # Ensure processed directory exists
    os.makedirs(processed_dir, exist_ok=True)
    
    # In a real scenario, OAI datasets are split across multiple files 
    # (e.g., Clinical data, Enrollees, Outcomes). We will simulate loading 
    # and merging them based on subject ID ('id').
    
    all_files = glob.glob(os.path.join(raw_dir, '*.csv')) + glob.glob(os.path.join(raw_dir, '*.txt'))
    if not all_files:
        print(f"No CSV or TXT files found in {raw_dir}. Please ensure you have downloaded the OAI dataset and placed the files in this directory.")
        return
        
    print(f"Found {len(all_files)} files. Attempting to parse and merge...")
    
    # Example logic: Load all CSVs/TXTs, assuming they all have an 'ID' or 'V00ID' column
    dataframes = []
    for file in all_files:
        try:
            # The NDA text files are tab-separated and have a description in the second row
            df = pd.read_csv(file, sep='\t', skiprows=[1], low_memory=False, on_bad_lines='skip')
            
            # Standardize ID column name (NDA uses src_subject_id usually)
            id_col = next((col for col in df.columns if col.upper() in ['ID', 'V00ID', 'SUBJECT_ID', 'SRC_SUBJECT_ID']), None)
            
            if id_col:
                df = df.rename(columns={id_col: 'SUBJECT_ID'})
                df['SUBJECT_ID'] = df['SUBJECT_ID'].astype(str)
                # We can also keep track of the timepoint (V00, V01, etc.) for longitudinal tracking
                dataframes.append(df)
            else:
                print(f"Skipping {os.path.basename(file)}: No recognized ID column found.")
        except Exception as e:
            print(f"Error processing {file}: {e}")
            
    if not dataframes:
        print("No valid datasets to process.")
        return
        
    # Merge datasets on SUBJECT_ID
    # Note: Outer join is used to keep all records. In a real pipeline, careful 
    # longitudinal merging (on ID + Timepoint) is required.
    merged_df = dataframes[0]
    for df in dataframes[1:]:
        # Avoid duplicate columns
        cols_to_use = df.columns.difference(merged_df.columns).tolist() + ['SUBJECT_ID']
        merged_df = pd.merge(merged_df, df[cols_to_use], on='SUBJECT_ID', how='outer')
        
    print(f"Merged dataset shape: {merged_df.shape}")
    
    # Filter for relevant feature categories (Anthropometry, Pain, Physical Performance, etc.)
    # Note: Replace these keywords with actual OAI column names (e.g., 'V00BMI', 'WOMAC', etc.)
    keywords = ['BMI', 'WEIGHT', 'HEIGHT', 'AGE', 'SEX', 'WOMAC', 'PAIN', 'KOOS', 'PASE', 'WALK', 'STRENGTH']
    
    # Select columns that match our keywords (case-insensitive) or are the subject ID
    cols_to_keep = ['SUBJECT_ID'] + [col for col in merged_df.columns if any(kw in col.upper() for kw in keywords)]
    
    # Clean the dataset
    cleaned_df = merged_df[cols_to_keep].copy()
    
    # Basic cleaning: drop columns with more than 80% missing data
    threshold = len(cleaned_df) * 0.8
    cleaned_df = cleaned_df.dropna(axis=1, thresh=len(cleaned_df) - threshold)
    
    # Save the processed data
    output_path = os.path.join(processed_dir, 'oai_cleaned.csv')
    cleaned_df.to_csv(output_path, index=False)
    print(f"Successfully processed OAI data and saved to {output_path}")
    print(f"Final shape: {cleaned_df.shape}")

if __name__ == "__main__":
    # Assuming script is run from scripts/data_processing/
    process_oai_data()
