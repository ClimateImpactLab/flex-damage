## Mortality Damage Functions API

This API provides access to climate damage data, specifically mortality damage projections under different climate scenarios, socioeconomic pathways, and modeling parameters.

## Technical Overview

- **Framework**: FastAPI
- **Data Source**: CSV files containing climate damage projections
- **Authentication**: None (currently open access)
- **CORS**: Enabled for all origins

## Data Structure

The API serves data from the CSV file `mortality_damage_eoc.csv` with the following key columns:

- **iso**: Country ISO code
- **rcp**: Representative Concentration Pathway (climate scenario)
- **ssp**: Shared Socioeconomic Pathway
- **model**: Economic growth model used
- **case_gamma**: Parameter for damage function curvature
- **case_population**: Population weighting approach
- **impact_source**: Source of climate impact data
- **flextotal**: Flexible total damage estimate
- **rawtotal**: Raw total damage estimate

## API Endpoints

### GET /api/data

Returns filtered climate damage data based on query parameters.

**Query Parameters:**

| Parameter       | Description        | Example Values                                         |
|---------------|------------------|--------------------------------------------------|
| rcp           | RCP value         | "rcp45", "rcp85"                               |
| ssp           | SSP value         | "SSP1", "SSP2", "SSP3", "SSP4", "SSP5"         |
| model         | Model name        | "OECD Env-Growth", "IIASA GDP"                 |
| case_gamma   | Case Gamma        | "all_gamma_values", "positive_gamma_only"      |
| case_population | Case Population | "population_weighted", "unweighted"           |
| impact_source  | Impact Source    | "data_meantas", "fixed_to_2", "fixed_to_3", "fixed_to_4", "data_meantas_country" |

**Response Format:**

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
      "rawtotal": 3.21
    },
    
  ]
}

```

## GET /api/countries

Returns a list of all available country ISO codes in the dataset.

```json
{
  "countries": ["AFG", "ALB", "DZA", ...]
}
```

##  Usage Examples

- Python use case:

```python
import requests

# Get data for RCP 4.5, SSP3, with OECD model
response = requests.get(
    "http://localhost:5000/api/data",
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


# JavaScript/React

This API is utilized by a React-based visualization (`../map/src/App.tsx`)component that displays the climate damage data on a world map. The component:

- Provides UI controls for filtering data by RCP, SSP, model, etc.
- Fetches filtered data from the API based on user selections.
- Renders a choropleth map with countries colored according to damage values.
- Displays top/bottom country rankings and tooltips with detailed information.

## Example of fetching data in the React component:

```json
// Example of how the React component fetches data
const fetchApiData = () => {
  const query = new URLSearchParams();
  Object.entries(filters).forEach(([key, value]) => {
    if (value) query.append(key, value);
  });
  
  fetch(`http://localhost:5000/api/data?${query.toString()}`)
    .then((res) => res.json())
    .then((data) => {
      setApiData(data.data);
    })
    .catch((err) => {
      console.error('Error fetching API data:', err);
    });
};
```

## Development Setup

To run the API locally:

```python
uvicorn mortality:app --host 0.0.0.0 --port 5000 --reload
```

## Error Handling
The API returns standard HTTP status codes:

- 200: Success
- 404: Endpoint not found
- 500: Server error
