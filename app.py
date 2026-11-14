# Streamlit app: enter a patient's info to get their predicted breast cancer survival
import streamlit as st #used for the web app
from lifelines import CoxPHFitter #implementation of the Cox model in lifelines
import pandas as pd #used for data set
import numpy as np #used for math functions
import matplotlib.pyplot as plt #used for visuals
from sklearn.model_selection import train_test_split #used to split data into training and test sets
from pathlib import Path #used to find the data file next to app.py

# Load, clean, and fit the model once (cached so it doesn't retrain every time an input changes)
@st.cache_resource
def train_model():
    # Read the data file that sits next to app.py in the repo
    # (a local path keeps working even if the repo is renamed, unlike a GitHub URL)
    data_path = Path(__file__).parent / "data" / "brca_metabric_clinical_data.tsv"
    data = pd.read_csv(data_path, sep='\t')

    # Map survival status to 0 and 1 (overall survival: death from any cause counts as an event)
    data["Patient's Vital Status"] = data["Patient's Vital Status"].map({
        'Living': 0,
        'Died of Disease': 1,
        'Died of Other Causes': 1
    })

    # Select relevant columns
    data_cols = data[['Age at Diagnosis',
                      'Tumor Size',
                      'Lymph nodes examined positive',
                      'Neoplasm Histologic Grade',
                      'ER status measured by IHC',
                      'Overall Survival (Months)',
                      "Patient's Vital Status"
                     ]].copy()

    # Convert numerical columns to numbers
    for col in ['Age at Diagnosis', 'Tumor Size',
                'Lymph nodes examined positive',
                'Neoplasm Histologic Grade',
                'Overall Survival (Months)']:
        data_cols[col] = pd.to_numeric(data_cols[col], errors='coerce')

    # Remove missing values
    data_cols = data_cols.dropna()

    # Convert categorical variables into 0 and 1 (Negative and Positive, respectively)
    data_cols = pd.get_dummies(data_cols, columns=['ER status measured by IHC'],
                               drop_first=True, dtype=int)

    # Group grade into high (3) vs low/intermediate (1-2) so every stratum has enough patients
    data_cols['High grade (3)'] = (data_cols['Neoplasm Histologic Grade'] == 3).astype(int)
    data_cols = data_cols.drop(columns=['Neoplasm Histologic Grade'])

    surv_time = 'Overall Survival (Months)'
    surv_status = "Patient's Vital Status"

    # Same 80/20 split as the notebook, so the app uses the exact same trained model
    train_df, test_df = train_test_split(data_cols, test_size=0.2, shuffle=True,
                                         random_state=42, stratify=data_cols[surv_status])

    # Fit the final model on the training set: stratified by ER status and grade, spline for age
    cph = CoxPHFitter()
    cph.fit(train_df, duration_col=surv_time, event_col=surv_status,
            strata=['ER status measured by IHC_Positve', 'High grade (3)'],
            formula="bs(`Age at Diagnosis`, df=4, extrapolation='clip') + `Tumor Size` + `Lymph nodes examined positive`")
    return cph

cph = train_model()

st.title("Breast Cancer Survival Predictor")
st.write("Enter a patient's information at diagnosis to see their predicted chance "
         "of being alive over the next 20 years.")

# Input boxes for each variable the model was trained on
col1, col2 = st.columns(2)
age = col1.number_input("Age at diagnosis (years)", min_value=20.0, max_value=100.0, value=55.0, step=1.0)
size = col2.number_input("Tumor size (mm)", min_value=1.0, max_value=200.0, value=20.0, step=1.0)
nodes = col1.number_input("Positive lymph nodes", min_value=0, max_value=50, value=0, step=1)
grade = col2.selectbox("Histologic grade", [1, 2, 3], index=1)
er = st.radio("ER status", ["Positive", "Negative"], horizontal=True)

# Put the inputs into a one-row table with the same column names as the training data
patient = pd.DataFrame([{
    'Age at Diagnosis': age,
    'Tumor Size': size,
    'Lymph nodes examined positive': nodes,
    'High grade (3)': 1 if grade == 3 else 0,
    'ER status measured by IHC_Positve': 1 if er == "Positive" else 0
}])

# Predicted chance of being alive (from any cause), month by month for 20 years
# (capped at 240 months because few patients were followed longer than that)
months = np.arange(0, 241)
surv = cph.predict_survival_function(patient, times=months).iloc[:, 0]

# Median survival: the first month the predicted survival chance drops to 50% or below
below_half = surv[surv <= 0.5]
if len(below_half) > 0:
    median = f"{below_half.index[0] / 12:.1f} years"
else:
    median = "> 20 years"

# Show the results side by side
r1, r2, r3 = st.columns(3)
r1.metric("5-year survival", f"{surv.loc[60]:.1%}")
r2.metric("10-year survival", f"{surv.loc[120]:.1%}")
r3.metric("Median survival", median)

# Plot the patient's predicted survival curve
fig, ax = plt.subplots(figsize=(7, 3.8))
ax.step(months / 12, surv, where='post')
ax.axhline(0.5, linestyle='--', color='gray', linewidth=1)
ax.set_ylim(0, 1.02)
ax.set_xlabel('Years since diagnosis')
ax.set_ylabel('Probability of survival')
ax.set_title('Predicted overall survival')
fig.tight_layout()
st.pyplot(fig)

st.caption("Cox proportional hazards model for overall survival, stratified by ER status and grade "
           "(3 vs 1-2) with a spline for age, trained on 1,434 METABRIC patients "
           "(5-fold CV C-index 0.676, test C-index 0.665). Student capstone project, not a clinical tool.")
