import pandas as pd
import geopandas as gpd
import fiona
import os

# Define base directories
BASE_DIR = os.getcwd()  # Get the current working directory
DATA_DIR = os.path.join(BASE_DIR, '..', 'data')  # Define the data directory path

# Load the mortality data
data_path = os.path.join(DATA_DIR, "mortality", "mortality_damage_eoc.csv")
mortality_df = pd.read_csv(data_path)  # Read mortality data into a Pandas DataFrame

# Define the path for geographic data
geography_base_path = os.path.join(DATA_DIR, "geographies")
geographies_path = os.path.join(geography_base_path, "ne_10m_admin_0_countries", "ne_10m_admin_0_countries.shp")

# Load the shapefile as a GeoDataFrame using Fiona
with fiona.open(geographies_path) as src:
    gdf_countries = gpd.GeoDataFrame.from_features(src, crs=src.crs)  # Convert features to a GeoDataFrame

# Merge the mortality data with country geometries using the ISO country code
merged_df = mortality_df.merge(
    gdf_countries[['SOV_A3', 'geometry']],  # Select relevant columns
    left_on='iso',  # Match mortality data country codes
    right_on='SOV_A3',  # Match geography data country codes
    how='left'  # Keep all rows from the mortality dataset
)

# Convert the merged DataFrame into a GeoDataFrame
merged_gdf = gpd.GeoDataFrame(merged_df, geometry='geometry', crs=gdf_countries.crs)

# The coordinate reference system (CRS) is already EPSG:4326 (WGS 84), which is suitable for web mapping

# Save the final dataset as a GeoJSON file for use in visualization tools
geojson_path = os.path.join(geography_base_path, "mortality_damage_eoc.geojson")
merged_gdf.to_file(geojson_path, driver="GeoJSON")

print(f"GeoJSON saved at: {geojson_path}")
