import pandas as pd
import os
import glob

def process_most_data(raw_dir='../../data/raw/MOST', processed_dir='../../data/processed'):
    """
    Processes the raw MOST dataset for external validation.
    Maps the features to be as close to OAI as possible.
    """
    print(f"Looking for MOST datasets in {os.path.abspath(raw_dir)}...")
    
    os.makedirs(processed_dir, exist_ok=True)
    
    all_files = glob.glob(os.path.join(raw_dir, '*.csv')) + glob.glob(os.path.join(raw_dir, '*.txt'))
    if not all_files:
        print(f"No CSV or TXT files found in {raw_dir}. Please ensure you have downloaded the MOST dataset and placed the files in this directory.")
        return
        
    print(f"Found {len(all_files)} files. Attempting to parse and merge...")
    
    dataframes = []
    for file in all_files:
        try:
            df = pd.read_csv(file, sep=None, engine='python')
            
            # Standardize ID column name (MOST uses MOSTID usually)
            id_col = next((col for col in df.columns if col.upper() in ['ID', 'MOSTID', 'SUBJECT_ID']), None)
            
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
        
    print(f"Merged dataset shape: {merged_df.shape}")
    
    # Filter for relevant validation features
    keywords = ['BMI', 'WEIGHT', 'HEIGHT', 'AGE', 'SEX', 'WOMAC', 'PAIN', 'KOOS', 'WALK', 'STRENGTH']
    cols_to_keep = ['SUBJECT_ID'] + [col for col in merged_df.columns if any(kw in col.upper() for kw in keywords)]
    
    cleaned_df = merged_df[cols_to_keep].copy()
    
    # Drop largely empty columns
    threshold = len(cleaned_df) * 0.8
    cleaned_df = cleaned_df.dropna(axis=1, thresh=len(cleaned_df) - threshold)
    
    output_path = os.path.join(processed_dir, 'most_cleaned.csv')
    cleaned_df.to_csv(output_path, index=False)
    print(f"Successfully processed MOST data and saved to {output_path}")
    print(f"Final shape: {cleaned_df.shape}")

if __name__ == "__main__":
    process_most_data()
