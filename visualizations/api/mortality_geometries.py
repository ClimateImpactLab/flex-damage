import os
import json
import numpy as np
from fastapi import FastAPI, Query
from fastapi.middleware.cors import CORSMiddleware
from typing import Optional
import math

# Create a FastAPI application
app = FastAPI()

# Enable CORS to allow requests from frontend
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # Change this to the frontend's domain in production
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# --- Define file paths ---
BASE_DIR = os.path.dirname(__file__)
DATA_DIR = os.path.join(BASE_DIR, "..", "data", "geographies")
GEOJSON_PATH = os.path.join(DATA_DIR, "mortality_damage_eoc_optimized.geojson")

# --- Load the GeoJSON file into memory only when needed ---
def load_geojson():
    """Lazy load GeoJSON data when needed."""
    with open(GEOJSON_PATH, "r", encoding="utf-8") as f:
        return json.load(f)

# --- Get all available countries ---
@app.get("/api/countries")
def get_countries():
    """Return a list of all available country ISO codes."""
    geojson_data = load_geojson()
    countries = [feature["properties"]["iso"] for feature in geojson_data["features"]]
    return {"countries": sorted(set(countries))}

# --- Define the main API endpoint ---
import math

@app.get("/api/data")
def get_data(
    rcp: Optional[str] = Query(None),
    ssp: Optional[str] = Query(None),
    model: Optional[str] = Query(None),
    case_gamma: Optional[str] = Query(None),
    case_population: Optional[str] = Query(None),
    impact_source: Optional[str] = Query(None)
):
    """API endpoint to filter and return geojson data based on query parameters."""
    
    geojson_data = load_geojson()

    # Create filter dictionary (remove None values)
    filters = {k: v for k, v in locals().items() if v is not None}

    filtered_features = []

    # Iterate through all country features
    for feature in geojson_data["features"]:
        properties = feature["properties"]

        if "data" not in properties:
            continue

        # Apply filtering logic (partial match)
        filtered_data = [
            entry for entry in properties["data"]
            if any(entry.get(k) == v for k, v in filters.items())
        ]

        # Convert NaN to None
        for entry in filtered_data:
            for key, value in entry.items():
                if isinstance(value, float) and math.isnan(value):  # ✅ Convert NaN to None
                    entry[key] = None

        if filtered_data:
            new_feature = feature.copy()
            new_feature["properties"]["data"] = filtered_data
            filtered_features.append(new_feature)

    return {"type": "FeatureCollection", "features": filtered_features}


# --- Run the application ---
if __name__ == "__main__":
    import uvicorn
    print("Starting FastAPI server...")
    uvicorn.run(app, host="127.0.0.1", port=5000, reload=True)
