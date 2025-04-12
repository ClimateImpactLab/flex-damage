// MapComponent.tsx
// A cleaned-up single-map component with hover interactions to show values in the legend.
// Comments are provided in English for clarity.

import React, { useEffect, useRef, useState, useCallback } from 'react';
import mapboxgl, { Map, MapMouseEvent } from 'mapbox-gl';
import Legend from './Legend';
import DataTable from './DataTable';
import './Map.css';

// Set the Mapbox access token from the environment variable.
mapboxgl.accessToken = import.meta.env.VITE_MAPBOX_ACCESS_TOKEN;

// Define an interface for CSV data rows.
export interface CSVRow {
  period?: string;
  ssp?: string;
  rcp?: string;
  model?: string;
  iso?: string;
  tt?: string;
  [key: string]: any;
}

// Define an interface for hover information.
interface HoverInfo {
  iso: string;
  value: number | null;
}

const MapComponent: React.FC<{
  filters: any;
  csvData: CSVRow[];
  geoData?: any;
  onMaxAbsChange?: (maxAbs: number) => void;
}> = ({ filters, csvData, geoData, onMaxAbsChange }) => {
  // Reference to the HTML container where the map will be rendered.
  const mapContainerRef = useRef<HTMLDivElement | null>(null);
  // Reference to the Mapbox map instance.
  const mapRef = useRef<Map | null>(null);

  // State to store the maximum absolute value used for color scaling.
  const [maxAbs, setMaxAbs] = useState<number>(1);
  // States to store the lowest and highest values for the data table.
  const [lowest, setLowest] = useState<[string, number][]>([]);
  const [highest, setHighest] = useState<[string, number][]>([]);
  // State to store the TT anomaly value if available.
  const [ttAnomaly, setTtAnomaly] = useState<number | null>(null);
  // State to store hover information for the legend.
  const [hoverInfo, setHoverInfo] = useState<HoverInfo | null>(null);

  // Function to remove any existing layers and sources.
  // This is used to refresh the map when new data comes in.
  const removeExistingLayersAndSources = useCallback(() => {
    if (!mapRef.current) return;
    const map = mapRef.current;
    // Remove the "choropleth" layer if it exists.
    if (map.getLayer('choropleth')) {
      try {
        map.removeLayer('choropleth');
      } catch (e) {
        console.error('Error removing layer "choropleth":', e);
      }
    }
    // Remove the "countries" source if it exists.
    if (map.getSource('countries')) {
      try {
        map.removeSource('countries');
      } catch (e) {
        console.error('Error removing source "countries":', e);
      }
    }
  }, []);

  // Initialize the Mapbox map when the component mounts.
  useEffect(() => {
    if (!mapContainerRef.current) return;
    if (!mapRef.current) {
      mapRef.current = new mapboxgl.Map({
        container: mapContainerRef.current,
        style: 'mapbox://styles/mapbox/light-v11',
        center: [0, 0],
        zoom: 1.5,
        projection: 'globe'
      });
      // Add navigation controls (e.g., zoom, rotation).
      mapRef.current.addControl(new mapboxgl.NavigationControl());
      // Once the map style has loaded, hide some default boundary layers for a cleaner view.
      mapRef.current.on('style.load', () => {
        const layersToHide = ['admin-1-boundary', 'admin-0-boundary-disputed', 'admin-0-boundary-bg'];
        layersToHide.forEach(layerId => {
          if (mapRef.current && mapRef.current.getLayer(layerId)) {
            mapRef.current.setLayoutProperty(layerId, 'visibility', 'none');
          }
        });
      });
      // Note: The "moveend" event registration for synchronization was removed.
    }
  }, []);

  // Process the CSV data, update the map source, and add the choropleth layer along with hover listeners.
  useEffect(() => {
    const map = mapRef.current;
    if (!map) return;
    if (csvData.length === 0) {
      console.warn('No CSV data available to process on the map');
      return;
    }

    // Update TT anomaly (if available) from the CSV.
    const anomalyVal = csvData[0].tt ? parseFloat(csvData[0].tt) : null;
    setTtAnomaly(anomalyVal);

    // Convert filter values to lowercase to ensure case-insensitive comparisons.
    const filterPeriod = filters.period.toLowerCase();
    const filterSSP = filters.ssp.toLowerCase();
    const filterRCP = filters.rcp.toLowerCase();
    const filterModel = filters.model.toLowerCase();
    const selectedMetric = filters.metric;

    let valueMap: { [key: string]: number } = {};
    // Iterate over each CSV row and apply the filters.
    csvData.forEach((d: CSVRow) => {
      const cleanedRowPeriod = d.period ? d.period.replace(/"/g, '').trim().toLowerCase() : '';
      const cleanedRowSSP = d.ssp ? d.ssp.replace(/"/g, '').trim().toLowerCase() : '';
      const cleanedRowRCP = d.rcp ? d.rcp.replace(/"/g, '').trim().toLowerCase() : '';
      const cleanedRowModel = d.model ? d.model.replace(/"/g, '').trim().toLowerCase() : '';
      // Process rows only if they match the current filters.
      if (
        cleanedRowPeriod === filterPeriod &&
        cleanedRowSSP === filterSSP &&
        cleanedRowRCP === filterRCP &&
        cleanedRowModel === filterModel
      ) {
        const iso = d.iso ? d.iso.replace(/"/g, '').trim() : '';
        let val = parseFloat(d[selectedMetric]);
        if (iso && !isNaN(val)) {
          // Adjust value for sectors like "combined", "high risk", or "low risk".
          if (['combined', 'high risk', 'low risk'].includes(filters.sector.toLowerCase())) {
            val = val / 60;
          }
          if (!valueMap[iso]) {
            valueMap[iso] = val;
          }
        }
      }
    });

    // Determine the maximum absolute value for color scaling.
    const values: number[] = Object.values(valueMap);
    const computedMaxAbs = Math.max(...values.map(v => Math.abs(v))) || 1;
    setMaxAbs(computedMaxAbs);
    if (onMaxAbsChange) onMaxAbsChange(computedMaxAbs);

    // Determine the lowest and highest five values to display in the data table.
    const sortedEntries = Object.entries(valueMap).sort((a, b) => a[1] - b[1]);
    setLowest(sortedEntries.slice(0, 5) as [string, number][]);
    setHighest(sortedEntries.slice(-5).reverse() as [string, number][]);

    // Remove any existing layers and sources before adding new data.
    removeExistingLayersAndSources();

    // Process GeoJSON data by joining CSV values with GeoJSON features.
    const processGeo = (data: any) => {
      data.features.forEach((feature: any) => {
        const isoCode = feature.properties?.ISO || feature.properties?.iso || '';
        const joinedValue = valueMap[isoCode] ?? null;
        if (feature.properties) {
          feature.properties.value = joinedValue;
        }
      });
      // Add or update the GeoJSON data source.
      if (!map.getSource('countries')) {
        map.addSource('countries', {
          type: 'geojson',
          data: data
        });
      } else {
        const source = map.getSource('countries');
        if (source && 'setData' in source) {
          (source as any).setData(data);
        }
      }
      // Define the color interpolation for the choropleth layer depending on the sector.
      let fillColor;
      if (filters.sector.toLowerCase() === 'mortality') {
        fillColor = [
          'interpolate',
          ['linear'],
          ['coalesce', ['get', 'value'], 0],
          -computedMaxAbs, '#00AEFF',
          -computedMaxAbs / 2, '#00FFEA',
          0, '#FFFFFF',
          computedMaxAbs / 2, '#FF8C00',
          computedMaxAbs, '#FF073A'
        ];
      } else {
        fillColor = [
          'interpolate',
          ['linear'],
          ['coalesce', ['get', 'value'], 0],
          -computedMaxAbs, '#FF073A',
          -computedMaxAbs / 2, '#FF8C00',
          0, '#FFFFFF',
          computedMaxAbs / 2, '#00FFEA',
          computedMaxAbs, '#00AEFF'
        ];
      }
      // Add the choropleth layer if it does not already exist.
      if (!map.getLayer('choropleth')) {
        map.addLayer({
          id: 'choropleth',
          type: 'fill',
          source: 'countries',
          paint: {
            'fill-color': fillColor as any,
            'fill-opacity': 0.7,
            'fill-outline-color': '#ccc'
          }
        });
      }
    };

    // Function to load GeoJSON data from either the provided geoData or via fetch.
    const loadGeoData = () => {
      if (geoData) return Promise.resolve(geoData);
      else {
        const url = 'https://huggingface.co/datasets/c1587s/flex-damage-impacts/resolve/main/geometries/world_countries_simplified.geojson';
        return fetch(url).then(res => res.json());
      }
    };

    // Variable to hold the cleanup function for hover event listeners.
    let cleanupListeners = () => {};

    // Define a helper function to add hover event listeners to the choropleth layer.
    const addHoverListeners = () => {
      const handleMouseMove = (e: MapMouseEvent) => {
        if (!e.features || !e.features.length) return;
        const feature = e.features[0];
        const iso = feature.properties?.ISO || feature.properties?.iso || '';
        // Using null coalescing for cases when the value does not exist.
        const val = feature.properties?.value ?? null;
        setHoverInfo({ iso, value: val });
      };
      const handleMouseLeave = () => {
        setHoverInfo(null);
      };
      map.on('mousemove', 'choropleth', handleMouseMove);
      map.on('mouseleave', 'choropleth', handleMouseLeave);
      // Provide a cleanup function to remove these event listeners.
      cleanupListeners = () => {
        map.off('mousemove', 'choropleth', handleMouseMove);
        map.off('mouseleave', 'choropleth', handleMouseLeave);
      };
    };

    // Load geo data and process it, then add hover event listeners.
    if (!map.isStyleLoaded()) {
      map.once('style.load', () => {
        loadGeoData()
          .then(data => {
            processGeo(data);
            addHoverListeners();
          })
          .catch(error => console.error('Error processing GeoJSON:', error));
      });
    } else {
      loadGeoData()
        .then(data => {
          processGeo(data);
          addHoverListeners();
        })
        .catch(error => console.error('Error processing GeoJSON:', error));
    }

    // Cleanup the hover event listeners when the effect is re-run.
    return () => {
      cleanupListeners();
    };
  }, [csvData, filters, geoData, onMaxAbsChange, removeExistingLayersAndSources]);

  // Render the map container, legend, and data table.
  // The Legend now receives hoverInfo so it will display hovered data.
  return (
    <div ref={mapContainerRef} className="map">
      <Legend
        maxAbs={maxAbs}
        hoverInfo={hoverInfo}
        sector={filters.sector}
        ttAnomaly={ttAnomaly}
      />
      <DataTable lowest={lowest} highest={highest} maxAbs={maxAbs} sector={filters.sector} />
    </div>
  );
};

export default MapComponent;
