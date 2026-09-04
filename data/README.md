# Dataset Download Instructions

This project requires three medical datasets for the Multimodal Osteoarthritis Prediction Architecture. Due to privacy and Data Use Agreements (DUAs), these cannot be downloaded automatically. Please follow the instructions below to download and place them correctly.

## 1. OAI (Osteoarthritis Initiative)
Used as the primary dataset.
- **Where to Access:** [NIMH Data Archive (NDA)](https://nda.nih.gov/oai)
- **Requirements:** An NDA account (via eRA Commons or Login.gov) and an approved Data Use Agreement.
- **What to Download:** Clinical data files containing Anthropometry, Clinical Information, Pain, Physical Activity, Physical Performance, and Longitudinal outcomes.
- **Where to Place:** Download the CSV or SAS files and place them inside the `data/raw/OAI/` directory.

## 2. MOST (Multicenter Osteoarthritis Study)
Used for external validation.
- **Where to Access:** [AgingResearchBiobank](https://agingresearchbiobank.nia.nih.gov/)
- **Requirements:** Registration and Data Use Agreement through the Biobank.
- **What to Download:** Clinical data matching the OAI features (pain, physical performance, etc.).
- **Where to Place:** Download the CSV or SAS files and place them inside the `data/raw/MOST/` directory.

## 3. KNOAP2020
Used as a benchmark and for feature selection.
- **Where to Access:** [KNOAP2020 Grand Challenge](https://knoap2020.grand-challenge.org/)
- **Requirements:** Registration on the Grand Challenge platform and acceptance of the challenge terms.
- **What to Download:** The clinical data portion of the challenge dataset (typically the training set if the test set is blinded).
- **Where to Place:** Extract the downloaded files and place the CSVs inside the `data/raw/KNOAP2020/` directory.

---
**After downloading the files:** 
Run the preprocessing scripts in `scripts/data_processing/` to clean and standardize the data into the `data/processed/` directory.
