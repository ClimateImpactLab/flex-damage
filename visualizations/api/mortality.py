"""
Climate Damage Data API
=======================

This API provides access to climate damage data, specifically mortality damage projections 
under different climate scenarios, socioeconomic pathways, and modeling parameters.

The API is deployed on Heroku at: https://flex-damage-api-425e80ae6f2d.herokuapp.com

Technical Overview
-----------------
- Framework: FastAPI
- Data Source: CSV files containing climate damage projections
- Authentication: None (currently open access)
- CORS: Enabled for all origins (should be restricted in production)

Base Data Structure
------------------
The API serves data from a CSV file with the following key columns:
- iso: Country ISO code
- rcp: Representative Concentration Pathway (climate scenario)
- ssp: Shared Socioeconomic Pathway
- model: Economic growth model used
- case_gamma: Parameter for damage function curvature
- case_population: Population weighting approach
- impact_source: Source of climate impact data
- flextotal: Flexible total damage estimate
- rawtotal: Raw total damage estimate

Endpoints
---------

GET /api/data
-------------
Returns filtered climate damage data based on query parameters.

Query Parameters:
* rcp (string, optional): RCP value (e.g., "rcp45", "rcp85")
* ssp (string, optional): SSP value (e.g., "SSP1", "SSP2", "SSP3", "SSP4", "SSP5")
* model (string, optional): Model name (e.g., "OECD Env-Growth", "IIASA GDP")
* case_gamma (string, optional): Case Gamma (e.g., "all_gamma_values", "positive_gamma_only")
* case_population (string, optional): Case Population (e.g., "population_weighted", "unweighted")
* impact_source (string, optional): Impact Source (e.g., "data_meantas", "fixed_to_2", "fixed_to_3", "fixed_to_4", "data_meantas_country")

Response Format:
```json
{
  "data": [
    {
      "iso": "USA",
      "rcp": "rcp45",
      "ssp": "SSP3",
      "model": "OECD Env-Growth",
      "case_gamma": "all_gamma_values",
      "case_population": "population_weighted",
      "impact_source": "data_meantas",
      "flextotal": 2.34,
      "rawtotal": 3.21,
    },
    // Additional country records
  ]
}
```

GET /api/countries
-----------------
Returns a list of all available country ISO codes in the dataset.

Response Format:
```json
{
  "countries": ["AFG", "ALB", "DZA", ...]
}
```

Error Handling
-------------
The API returns standard HTTP status codes:
- 200: Success
- 404: Endpoint not found
- 500: Server error

Data Processing Notes
--------------------
- All NaN and infinity values in the source data are converted to null in the JSON response
- No aggregation is performed server-side; all filtering is done on the raw data
- The complete dataset is loaded into memory at startup for fast query response

Usage Example
------------
```python
import requests

# Get data for RCP 4.5, SSP3, with OECD model
response = requests.get(
    "https://flex-damage-api-425e80ae6f2d.herokuapp.com/api/data",
    params={
        "rcp": "rcp45",
        "ssp": "SSP3",
        "model": "OECD Env-Growth",
        "case_gamma": "all_gamma_values",
        "case_population": "population_weighted"}
)

if response.status_code == 200:
    data = response.json()
    print(f"Retrieved {len(data['data'])} records")
```

Deployment Information
---------------------
The API is deployed on Heroku. To update the deployment:

1. Push changes to the main branch
2. Heroku will automatically build and deploy the new version
3. Verify deployment with: `heroku logs --tail --app flex-damage-api-425e80ae6f2d`

Development Setup
----------------
To run the API locally:

1. Clone the repository
2. Install dependencies: `pip install -r requirements.txt`
3. Run the development server: `uvicorn mortality:app --host 0.0.0.0 --port 5000 --reload`
"""

import os
import numpy as np
import pandas as pd
from fastapi import FastAPI, Query, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from typing import Optional, List, Dict, Any, Union
from pydantic import BaseModel

# Create the FastAPI application with metadata
app = FastAPI(
    version="1.0.0",
    contact={
        "url": "https://github.com/ClimateImpactLab/flex-damage/tree/countries-flex-damage",
    },
)

# Enable CORS (adjust allow_origins in production)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"], 
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Define base directories and the path to the CSV file
BASE_DIR = os.getcwd()
DATA_DIR = os.path.join(BASE_DIR, '..', 'data')
data_path = os.path.join(DATA_DIR, "mortality", "mortality_damage_eoc.csv")

# Define data model for validation and documentation
class ClimateDataItem(BaseModel):
    iso: str
    rcp: str
    ssp: str
    model: str
    case_gamma: str
    case_population: str
    impact_source: str
    flextotal: Optional[float]
    rawtotal: Optional[float]
    # Additional fields could be defined here

class ClimateDataResponse(BaseModel):
    data: List[Dict[str, Any]]

class CountriesResponse(BaseModel):
    countries: List[str]

# Load the CSV file into a DataFrame (loaded once on startup)
try:
    mortality_df = pd.read_csv(data_path)
    print(f"Data loaded successfully. Shape: {mortality_df.shape}")
except Exception as e:
    print(f"Error loading data: {e}")
    # Initialize with empty DataFrame as fallback
    mortality_df = pd.DataFrame()

@app.get("/api/data", response_model=ClimateDataResponse, 
         summary="Get climate damage data",
         description="Retrieve climate damage data filtered by various parameters")
def get_data(
    rcp: Optional[str] = Query(None, 
                              description="RCP value (e.g., 'rcp45', 'rcp85')"),
    ssp: Optional[str] = Query(None, 
                              description="SSP value (e.g., 'SSP1', 'SSP2', 'SSP3', 'SSP4', 'SSP5')"),
    model: Optional[str] = Query(None, 
                                description="Model name (e.g., 'OECD Env-Growth', 'IIASA GDP')"),
    case_gamma: Optional[str] = Query(None, 
                                     description="Case Gamma (e.g., 'all_gamma_values', 'positive_gamma_only')"),
    case_population: Optional[str] = Query(None, 
                                          description="Case Population (e.g., 'population_weighted', 'unweighted')"),
    impact_source: Optional[str] = Query(None, 
                                        description="Impact Source (e.g., 'data_meantas', 'fixed_to_2')")
) -> ClimateDataResponse:
    """
    Retrieve climate damage data with optional filtering.
    
    This endpoint allows querying the climate damage database with specific filter criteria.
    All filter parameters are optional - if none are provided, all data will be returned.
    
    The data includes projections of climate damage across different countries under various 
    scenarios, socioeconomic pathways, and modeling assumptions.
    
    Notes:
    - All NaN or infinite values are converted to None in the response
    - Response size varies based on filter parameters, from a few records to thousands
    - Performance is optimized by loading data into memory at startup
    
    Examples:
    - `/api/data?rcp=rcp45` - Get all data for RCP 4.5 scenario
    - `/api/data?rcp=rcp45&ssp=SSP3` - Get data for RCP 4.5, SSP3 combination
    """
    if mortality_df.empty:
        raise HTTPException(status_code=500, detail="Data source not available")
        
    # Make a copy of the DataFrame to apply filters without modifying the original
    df_filtered = mortality_df.copy()
    
    # Track applied filters for logging/debugging
    applied_filters = {}
    
    # Apply filters if provided
    if rcp is not None:
        df_filtered = df_filtered[df_filtered["rcp"] == rcp]
        applied_filters["rcp"] = rcp
    if ssp is not None:
        df_filtered = df_filtered[df_filtered["ssp"] == ssp]
        applied_filters["ssp"] = ssp
    if model is not None:
        df_filtered = df_filtered[df_filtered["model"] == model]
        applied_filters["model"] = model
    if case_gamma is not None:
        df_filtered = df_filtered[df_filtered["case_gamma"] == case_gamma]
        applied_filters["case_gamma"] = case_gamma
    if case_population is not None:
        df_filtered = df_filtered[df_filtered["case_population"] == case_population]
        applied_filters["case_population"] = case_population
    if impact_source is not None:
        df_filtered = df_filtered[df_filtered["impact_source"] == impact_source]
        applied_filters["impact_source"] = impact_source
    
    print(f"Applied filters: {applied_filters}. Records remaining: {len(df_filtered)}")
    
    # Replace NaN, positive infinity, and negative infinity with None
    df_filtered = df_filtered.replace({np.nan: None, np.inf: None, -np.inf: None})
    
    # Convert the DataFrame to a list of dictionaries
    data = df_filtered.to_dict(orient="records")
    
    return {"data": data}

@app.get("/api/countries", response_model=CountriesResponse,
         summary="Get list of countries",
         description="Returns a sorted list of unique country ISO codes available in the dataset")
def get_countries() -> CountriesResponse:
    """
    Retrieve a list of all country ISO codes available in the dataset.
    
    This endpoint returns a sorted list of all unique country identifiers (ISO codes)
    that are available in the climate damage dataset. This can be useful for building
    UI selection components or for validating country inputs.
    
    The response is a simple JSON object with a single "countries" field containing
    an array of ISO code strings.
    
    Example response:
    ```json
    {
      "countries": ["AFG", "ALB", "DZA", "AND", ...]
    }
    ```
    """
    if mortality_df.empty:
        raise HTTPException(status_code=500, detail="Data source not available")
        
    countries = mortality_df["iso"].unique().tolist()
    return {"countries": sorted(countries)}

@app.get("/health", 
         summary="Health check",
         description="Basic health check endpoint to verify API is running")
def health_check():
    """
    Simple health check endpoint.
    
    Returns status information about the API including:
    - Status: Whether the API is operational
    - Data availability: Whether the climate data was successfully loaded
    - Record count: Total number of records in the dataset
    
    This endpoint is useful for monitoring and deployment verification.
    """
    return {
        "status": "ok",
        "data_available": not mortality_df.empty,
        "record_count": len(mortality_df) if not mortality_df.empty else 0,
        "columns": mortality_df.columns.tolist() if not mortality_df.empty else []
    }

if __name__ == "__main__":
    import uvicorn
    print("Starting FastAPI server...")
    uvicorn.run(app, host="127.0.0.1", port=5000, reload=True)
    # Alternative command:
    # uvicorn mortality:app --host 0.0.0.0 --port 5000 --reload