# Public datasets: sources and licences

**Real third-party data, used only to test ingestion and models. It is never presented as client data.**
The data files themselves are not in git (both folders are listed in `.gitignore`); only this record is meant to be kept with the project.
Files are kept exactly as downloaded, including the names the browser gave them (spaces and one file with no extension).

Download date for everything below: **2026-10-10** (from the files' timestamps; downloaded by the project owner).

---

## 1. Fast-disintegrating-tablet formulations (literature dataset)

Folder: `data/public/formulation_literature/`

| | |
|---|---|
| Name | Final Data All Excipients (Fast-Disintegrating Tablet Formulations Dataset): 1,982 formulations collected from peer-reviewed articles |
| DOI | https://doi.org/10.7910/DVN/TUSJYB (Harvard Dataverse) |
| Licence | **CC0 1.0 Universal** (public domain; no restrictions, citation appreciated) |
| Dataset citation | Momeni M. Final Data All Excipients [dataset]. Harvard Dataverse; 2023. https://doi.org/10.7910/DVN/TUSJYB |
| Article the authors ask users to cite | Momeni M. Fast disintegrating tablet formulation data: a comprehensive dataset for pharmaceutical development. *BMC Research Notes*. 2023;16(1):225. https://doi.org/10.1186/s13104-023-06416-w |
| Published | 2023 (the dataset's own metadata says 2023-07-06 in one place and 2023-07-01 in another) |
| Use here | Real third-party data used only to test ingestion and models, never presented as client data |

Files:

| File | Size (bytes) | SHA-256 |
|---|---|---|
| `final Data All Exipients.csv` | 414,999 | `a972774dfe187f9f67931e0e8d1a431e85ac5a015063ead54e3226bd021a66c7` |
| `Method` (a Word .docx saved without its extension; describes how the data were collected) | 150,263 | `5fc866b8811fd2e3b8e30d0c201feba37626a84f752c685dd6c475ad0d892749` |
| `dataverse_files.zip` (Dataverse's bundle: the same CSV and Method, a data dictionary, a list of APIs, metadata and a README; **not extracted**) | 274,761 | `5316262793b83fb96806e1d4d1bcc267ef28f58006d2f79badf1432bccac5482` |

---

## 2. Tablet production batches (manufacturing dataset)

Folder: `data/public/batch_production/`

| | |
|---|---|
| Name | Big data collection in pharmaceutical manufacturing: 1,005 production batches of one tablet product (raw-material quality, compression process data and final product quality) |
| DOI | https://doi.org/10.6084/m9.figshare.c.5645578 (figshare collection) |
| Licence | **CC BY 4.0** (attribution is required whenever this data or anything derived from it is shared or published). Confirmed by the project owner from the article's "Rights and permissions" section. |
| Citation | Žagar J, Mihelič J. Big data collection in pharmaceutical manufacturing and its use for product quality predictions. *Scientific Data*. 2022;9:99. https://doi.org/10.1038/s41597-022-01203-x |
| Authors | Janja Žagar and Jurij Mihelič (Lek Pharmaceuticals d.d. and University of Ljubljana). Verified by the project owner against the article. |
| Paper | *Scientific Data*, volume 9, article 99 (2022; published 2022-03-23) |
| Suggested attribution | Data from Žagar J, Mihelič J, "Big data collection in pharmaceutical manufacturing and its use for product quality predictions", Scientific Data 9, 99 (2022), https://doi.org/10.1038/s41597-022-01203-x; dataset https://doi.org/10.6084/m9.figshare.c.5645578, used under CC BY 4.0. Changes (reading, cleaning, modelling) were made by this project. |
| Use here | Real third-party data used only to test ingestion and models, never presented as client data |

Files in the folder:

| File | Size (bytes) | SHA-256 |
|---|---|---|
| `Laboratory.csv` (raw-material and final-product laboratory results, one row per batch) | 293,492 | `a3b0f16c7c3fa8052b38d767e38fda731a751acc4ec139b52d01577b32dc6483` |
| `Process.csv` (features extracted from each batch's process sensors, one row per batch) | 257,208 | `68382e88104beb679acf66d0ec35177e0880e67c7a3d7e72dc60b1e3388410ce` |
| `Normalization.csv` (normalisation factor per product code and batch size) | 433 | `957bae7af3266b5317eb8eda49a8a65f587d33f04794cda25f1062f12265eaa6` |
| `Code availability.docx` (the authors' description of their data-processing code) | 36,219 | `1e2254046bd8323369d5a6411977edc7c70c1d3b2d29b186188ba1ee181403a9` |

### Not in this project: the raw sensor time series

`Process.zip` is the raw per-batch sensor time series from the same dataset. It was **deliberately left in the Downloads folder** and was not moved or extracted.

| | |
|---|---|
| Location | `C:\Users\pranaysaxena\Downloads\Process.zip` |
| DOI | same collection: https://doi.org/10.6084/m9.figshare.c.5645578 |
| Licence | CC BY 4.0 (as above) |
| Size | 29,811,605 bytes compressed; 25 CSV files, about 346 MB uncompressed (checked by listing only) |
| SHA-256 | `8a401f1c7ac9880c763e3350f595c45c90487c0950db48caa9cda729582f5c25` |
| Why it is not here | `Process.csv` already holds the features extracted from it that this project needs |

---

## Rules for using these files

- Never tune a model to these files and then report that fit as a result about real tablets or about a client.
- Any output that uses them says so and is labelled "real public data, not client data".
- Do not mix them with `data/client/` and do not put them anywhere that is committed or uploaded.
- Keep the licence and attribution above with any report or file that uses them (required for the CC BY 4.0 dataset).
