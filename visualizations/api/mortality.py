import os
import numpy as np
import pandas as pd
from fastapi import FastAPI, Query
from fastapi.middleware.cors import CORSMiddleware
from typing import Optional

# Create the FastAPI application
app = FastAPI()

# Enable CORS (adjust allow_origins in production)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # In production, restrict this to your frontend's domain(s)
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Define base directories and the path to the CSV file
BASE_DIR = os.getcwd()
DATA_DIR = os.path.join(BASE_DIR, '..', 'data')
data_path = os.path.join(DATA_DIR, "mortality", "mortality_damage_eoc.csv")

# Load the CSV file into a DataFrame (loaded once on startup)
mortality_df = pd.read_csv(data_path)
print("Data loaded:")
print(mortality_df.head())

@app.get("/api/data")
def get_data(
    rcp: Optional[str] = Query(None, description="RCP value"),
    ssp: Optional[str] = Query(None, description="SSP value"),
    model: Optional[str] = Query(None, description="Model name"),
    case_gamma: Optional[str] = Query(None, description="Case Gamma"),
    case_population: Optional[str] = Query(None, description="Case Population"),
    impact_source: Optional[str] = Query(None, description="Impact Source")
):
    """
    Return filtered CSV records based on the provided query parameters.
    All NaN or infinite values are converted to None so that JSON encoding works.
    """
    # Make a copy of the DataFrame to apply filters without modifying the original
    df_filtered = mortality_df.copy()

    # Apply filters if provided
    if rcp is not None:
        df_filtered = df_filtered[df_filtered["rcp"] == rcp]
    if ssp is not None:
        df_filtered = df_filtered[df_filtered["ssp"] == ssp]
    if model is not None:
        df_filtered = df_filtered[df_filtered["model"] == model]
    if case_gamma is not None:
        df_filtered = df_filtered[df_filtered["case_gamma"] == case_gamma]
    if case_population is not None:
        df_filtered = df_filtered[df_filtered["case_population"] == case_population]
    if impact_source is not None:
        df_filtered = df_filtered[df_filtered["impact_source"] == impact_source]

    # Replace NaN, positive infinity, and negative infinity with None
    df_filtered = df_filtered.replace({np.nan: None, np.inf: None, -np.inf: None})

    # Convert the DataFrame to a list of dictionaries
    data = df_filtered.to_dict(orient="records")
    return {"data": data}

@app.get("/api/countries")
def get_countries():
    """
    Return a sorted list of unique country ISO codes.
    """
    countries = mortality_df["iso"].unique().tolist()
    return {"countries": sorted(countries)}

if __name__ == "__main__":
    import uvicorn
    print("Starting FastAPI server...")
    uvicorn.run(app, host="127.0.0.1", port=5000, reload=True)


    # uvicorn mortality:app --host 0.0.0.0 --port 5000 --reload  # Restart FastAPI
