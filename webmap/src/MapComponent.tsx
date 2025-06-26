// MapComponent.tsx
import React, { useEffect, useRef, useState, useCallback } from 'react';
import mapboxgl, { Map, MapMouseEvent } from 'mapbox-gl';
import Legend from './Legend';
import DataTable from './DataTable';
import LayerToggle from './LayerToggle';
import ProjectionSelector, { ProjectionType } from './ProjectionSelector';
import WinsorizationPanel, { WinsorizationSettings } from './WinsorizationPanel';
import { winsorizeMap } from './utils/winsorization';
import './Map.css';

mapboxgl.accessToken = import.meta.env.VITE_MAPBOX_ACCESS_TOKEN;
// builds [value, color] stops evenly spaced from –max to +max
const makeStops = (cols: string[], max: number) =>
  cols
    .map((c, i) => {
      const v = -max + (2 * max * i) / (cols.length - 1);
      return [v, c];
    })
    .flat();

export interface CSVRow {
  period?: string;
  ssp?: string;
  rcp?: string;
  model?: string;
  iso?: string;
  tt?: string;
  flextotal?: string;
  rawtotal?: string;
  [key: string]: any;
}

interface HoverInfo {
  iso: string;
  value: number | null;
}

type LayerMode = 'flex' | 'raw' | 'difference';

interface MapComponentProps {
  filters: any;
  csvData: CSVRow[];
  geoData?: any;
  onMaxAbsChange?: (maxAbs: number) => void;
  isLoading?: boolean;
  animate?: boolean;
}

const MapComponent: React.FC<MapComponentProps> = ({
  filters,
  csvData,
  geoData,
  onMaxAbsChange,
  isLoading = false
}) => {
  // const isMortality = filters.sector?.toLowerCase() === 'mortality';
  const mapContainerRef = useRef<HTMLDivElement | null>(null);
  const mapRef = useRef<Map | null>(null);

  const [layerMode, setLayerMode] = useState<LayerMode>('flex');
  const [projection, setProjection] = useState<ProjectionType>('naturalEarth');
  const [winsorizationSettings, setWinsorizationSettings] = useState<WinsorizationSettings>({
    enabled: false,
    lowerPercentile: 2,
    upperPercentile: 98,
    topCoding: true  // Default to top coding enabled
  });
  const [maxAbs, setMaxAbs] = useState<number>(1);
  const [diffScale, setDiffScale] = useState<number>(1);
  const [lowest, setLowest] = useState<[string, number][]>([]);
  const [highest, setHighest] = useState<[string, number][]>([]);
  const [ttAnomaly, setTtAnomaly] = useState<number | null>(null);
  const [hoverInfo, setHoverInfo] = useState<HoverInfo | null>(null);
  const [finalFlexMap, setFinalFlexMap] = useState<{ [iso: string]: number }>({});
  const [finalRawMap, setFinalRawMap] = useState<{ [iso: string]: number }>({});
  const [finalDiffMap, setFinalDiffMap] = useState<{ [iso: string]: number }>({});
  const [highlightedCountry, setHighlightedCountry] = useState<string | null>(null);

  const removeExistingLayersAndSources = useCallback(() => {
    if (!mapRef.current) return;
    const map = mapRef.current;
    
    // Remove highlight layers
    if (map.getLayer('country-highlight-border')) {
      try {
        map.removeLayer('country-highlight-border');
      } catch (e) {
        console.error('Error removing layer "country-highlight-border":', e);
      }
    }
    
    if (map.getLayer('country-highlight-fill')) {
      try {
        map.removeLayer('country-highlight-fill');
      } catch (e) {
        console.error('Error removing layer "country-highlight-fill":', e);
      }
    }
    
    if (map.getLayer('choropleth')) {
      try {
        map.removeLayer('choropleth');
      } catch (e) {
        console.error('Error removing layer "choropleth":', e);
      }
    }
    
    if (map.getSource('countries')) {
      try {
        map.removeSource('countries');
      } catch (e) {
        console.error('Error removing source "countries":', e);
      }
    }
  }, []);

  useEffect(() => {
    if (!mapContainerRef.current) return;
    if (!mapRef.current) {
      mapRef.current = new mapboxgl.Map({
        container: mapContainerRef.current,
        style: 'mapbox://styles/mapbox/light-v11',
        center: [0, 0],
        zoom: 1.8,
        projection: projection
      });
      mapRef.current.addControl(new mapboxgl.NavigationControl());
      
      // Add custom recenter button with image
      const recenterButton = document.createElement('button');
      recenterButton.className = 'mapboxgl-ctrl-icon mapboxgl-ctrl-recenter';
      recenterButton.title = 'Recenter map';
      
      // Create image element
      const recenterImg = document.createElement('img');
      recenterImg.src = '/recenter.png';
      recenterImg.alt = 'Recenter';
      recenterImg.style.cssText = `
        width: 20px;
        height: 20px;
        filter: invert(1);
      `;
      
      recenterButton.appendChild(recenterImg);
      recenterButton.style.cssText = `
        position: absolute;
        bottom: 200px;
        right: 10px;
        z-index: 10;
        background: rgba(0, 0, 0, 0.6);
        border: none;
        border-radius: 4px;
        padding: 8px;
        cursor: pointer;
        box-shadow: 0 2px 8px rgba(0, 0, 0, 0.15);
        transition: background-color 0.2s ease;
        display: flex;
        align-items: center;
        justify-content: center;
      `;
      
      recenterButton.addEventListener('mouseenter', () => {
        recenterButton.style.background = 'rgba(0, 0, 0, 0.8)';
      });
      
      recenterButton.addEventListener('mouseleave', () => {
        recenterButton.style.background = 'rgba(0, 0, 0, 0.6)';
      });
      
      recenterButton.addEventListener('click', () => {
        if (mapRef.current) {
          mapRef.current.flyTo({
            center: [0, 0],
            zoom: 1.8,
            pitch: 0,
            bearing: 0,
            duration: 1000
          });
        }
      });
      
      mapContainerRef.current?.appendChild(recenterButton);
      mapRef.current.on('style.load', () => {
        const layersToHide = ['admin-1-boundary', 'admin-0-boundary-disputed', 'admin-0-boundary-bg'];
        layersToHide.forEach(layerId => {
          if (mapRef.current?.getLayer(layerId)) {
            mapRef.current.setLayoutProperty(layerId, 'visibility', 'none');
          }
        });
        
        // Change background and water colors to white
        if (mapRef.current?.getLayer('background')) {
          mapRef.current.setPaintProperty('background', 'background-color', '#ffffff');
        }
        if (mapRef.current?.getLayer('water')) {
          mapRef.current.setPaintProperty('water', 'fill-color', '#ffffff');
        }
        if (mapRef.current?.getLayer('waterway')) {
          mapRef.current.setPaintProperty('waterway', 'line-color', '#ffffff');
        }
      });
    }
  }, [projection]);

  // Handle projection changes - reload data when projection changes
  const handleProjectionChange = useCallback((newProjection: ProjectionType) => {
    setProjection(newProjection);
    if (mapRef.current) {
      mapRef.current.setProjection(newProjection);
    }
  }, []);

  // Handle country hover from table
  const handleCountryHover = useCallback((iso: string | null) => {
    console.log('handleCountryHover called with:', iso);
    setHighlightedCountry(iso);
    
    if (mapRef.current) {
      console.log('Map ref exists, border layer available:', {
        borderLayer: !!mapRef.current.getLayer('country-highlight-border')
      });
      
      // Update border highlight only (no fill)
      if (mapRef.current.getLayer('country-highlight-border')) {
        console.log('Updating border highlight for:', iso);
        if (iso) {
          mapRef.current.setFilter('country-highlight-border', ['==', ['get', 'ISO'], iso]);
          mapRef.current.setPaintProperty('country-highlight-border', 'line-opacity', 1);
        } else {
          mapRef.current.setFilter('country-highlight-border', ['==', ['get', 'ISO'], '']);
        }
      } else {
        console.log('country-highlight-border layer not found');
      }
    } else {
      console.log('Map ref is null');
    }
  }, []);

  const addHoverListeners = (map: Map) => {
    const handleMouseMove = (e: MapMouseEvent) => {
      if (!e.features || !e.features.length) return;
      const feature = e.features[0];
      let value: number | null = null;
      // Use original values for hover display (not processed/winsorized values)
      if (layerMode === 'difference') {
        value = feature.properties?.originalDiff ?? null;
      } else {
        const originalProp = `original${layerMode.charAt(0).toUpperCase() + layerMode.slice(1)}`;
        value = feature.properties ? feature.properties[originalProp] ?? null : null;
      }
      const iso = feature.properties?.ISO || feature.properties?.iso || '';
      setHoverInfo({ iso, value });
    };
  
    const handleMouseLeave = () => {
      setHoverInfo(null);
    };
  
    // NUEVOS handlers para cursor
    const handleMouseEnterCursor = () => {
      map.getCanvas().style.cursor = 'pointer';
    };
  
    const handleMouseLeaveCursor = () => {
      map.getCanvas().style.cursor = '';
    };
  
    map.on('mousemove', 'choropleth', handleMouseMove);
    map.on('mouseleave', 'choropleth', handleMouseLeave);
    map.on('mouseenter', 'choropleth', handleMouseEnterCursor);
    map.on('mouseleave', 'choropleth', handleMouseLeaveCursor);
  
    return () => {
      map.off('mousemove', 'choropleth', handleMouseMove);
      map.off('mouseleave', 'choropleth', handleMouseLeave);
      map.off('mouseenter', 'choropleth', handleMouseEnterCursor);
      map.off('mouseleave', 'choropleth', handleMouseLeaveCursor);
    };
  };
  

  useEffect(() => {
    const map = mapRef.current;
    if (!map) return;
    if (csvData.length === 0) {
      console.warn('No CSV data to process');
      return;
    }

    const matchingRow = csvData.find((d: CSVRow) => {
      const matchesModel = d.model?.replace(/"/g, '').trim().toLowerCase() === filters.model.toLowerCase();
      const matchesSSP = d.ssp?.replace(/"/g, '').trim().toLowerCase() === filters.ssp.toLowerCase();
      const matchesRCP = d.rcp?.replace(/"/g, '').trim().toLowerCase() === filters.rcp.toLowerCase();
      const matchesPeriod = d.period?.replace(/"/g, '').trim().toLowerCase() === filters.period.toLowerCase();
    
      return matchesModel && matchesSSP && matchesRCP && matchesPeriod;
    });
    
    const anomalyVal = matchingRow?.tt ? parseFloat(matchingRow.tt) : null;
    setTtAnomaly(anomalyVal);    

    const filterPeriod = filters.period.toLowerCase();
    const filterSSP = filters.ssp.toLowerCase();
    const filterRCP = filters.rcp.toLowerCase();
    
    // Map model names for energy sector
    const getModelName = (model: string, sector: string): string => {
      if (sector.toLowerCase() === 'energy') {
        if (model.toLowerCase() === 'high') return 'OECD Env-Growth';
        if (model.toLowerCase() === 'low') return 'IIASA GDP';
      }
      return model.toLowerCase();
    };
    
    const filterModel = getModelName(filters.model, filters.sector);



    let flexMap: { [iso: string]: number } = {};
    let rawMap: { [iso: string]: number } = {};

        csvData.forEach((d: CSVRow) => {
      const cleanedRowPeriod = d.period ? d.period.replace(/"/g, '').trim().toLowerCase() : '';
      const cleanedRowSSP = d.ssp ? d.ssp.replace(/"/g, '').trim().toLowerCase() : '';
      const cleanedRowRCP = d.rcp ? d.rcp.replace(/"/g, '').trim().toLowerCase() : '';
      const cleanedRowModel = d.model ? d.model.replace(/"/g, '').trim() : '';
      
      if (
        cleanedRowPeriod === filterPeriod &&
        cleanedRowSSP === filterSSP &&
        cleanedRowRCP === filterRCP &&
        cleanedRowModel === filterModel
      ) {
        const iso = d.iso ? d.iso.replace(/"/g, '').trim() : '';
        let flexVal = d.flextotal ? parseFloat(d.flextotal) : NaN;
        let rawVal = d.rawtotal ? parseFloat(d.rawtotal) : NaN;
        
        if (!isNaN(flexVal) && !isNaN(rawVal) && iso && isFinite(flexVal) && isFinite(rawVal)) {
          if (["combined", "high risk", "low risk"].includes(filters.sector.toLowerCase())) {
            flexVal = flexVal;
            rawVal = rawVal;
          }
          if (flexMap[iso] === undefined) flexMap[iso] = flexVal;
          if (rawMap[iso] === undefined) rawMap[iso] = rawVal;
        }
      }
    });

    // Apply winsorization if enabled (only for flex and raw, not difference)
    const currentFinalFlexMap = winsorizationSettings.enabled && layerMode !== 'difference'
      ? winsorizeMap(flexMap, winsorizationSettings.lowerPercentile, winsorizationSettings.upperPercentile)
      : flexMap;
    const currentFinalRawMap = winsorizationSettings.enabled && layerMode !== 'difference'
      ? winsorizeMap(rawMap, winsorizationSettings.lowerPercentile, winsorizationSettings.upperPercentile)
      : rawMap;

    // Calculate dynamic max based on actual data range
    let currentValues: number[] = [];
    if (layerMode === 'flex') {
      currentValues = Object.values(winsorizationSettings.enabled ? currentFinalFlexMap : flexMap);
    } else if (layerMode === 'raw') {
      currentValues = Object.values(winsorizationSettings.enabled ? currentFinalRawMap : rawMap);
    } else {
      // For difference mode, always use non-winsorized values
      currentValues = Object.values(currentFinalFlexMap).concat(Object.values(currentFinalRawMap));
    }
    
    let displayMaxAbs: number;
    
    if (winsorizationSettings.topCoding) {
      // Top coding: use the minimum absolute value between max positive and max negative
      // This clips the scale to the smaller extreme, improving color distribution
      const actualMin = Math.min(...currentValues);
      const actualMax = Math.max(...currentValues);
      const maxPositive = Math.max(actualMax, 0);
      const maxNegative = Math.abs(Math.min(actualMin, 0));
      
      displayMaxAbs = Math.min(maxPositive, maxNegative);
      
      // If one side has no values, use the other side
      if (displayMaxAbs === 0) {
        displayMaxAbs = Math.max(maxPositive, maxNegative);
      }
      
      // For tiny values, don't force a minimum of 1
      displayMaxAbs = Math.max(displayMaxAbs, 0.001);
    } else {
      // Regular max absolute value approach
      const computedMaxAbs = Math.max(...currentValues.map(v => Math.abs(v))) || 1;
      
      // Round up to a nice number for display, but preserve small scales
      const roundToNiceNumber = (num: number): number => {
        // For very small values (< 0.1), don't round to avoid losing scale information
        if (num < 0.1) {
          return num; // Use actual value for tiny values
        }
        
        // For small values (< 1), round to 1 decimal place
        if (num < 1) {
          return Math.ceil(num * 10) / 10;
        }
        
        const magnitude = Math.pow(10, Math.floor(Math.log10(num)));
        const normalized = num / magnitude;
        let rounded;
        if (normalized <= 1) rounded = 1;
        else if (normalized <= 2) rounded = 2;
        else if (normalized <= 5) rounded = 5;
        else rounded = 10;
        return rounded * magnitude;
      };
      
      displayMaxAbs = roundToNiceNumber(computedMaxAbs);
    }
    
    // Special handling for labor sectors with tiny values for better color distribution
    const isLaborSector = filters.sector?.toLowerCase().includes('labor');
    if (isLaborSector && !winsorizationSettings.topCoding) {
      // For labor sectors, use percentile-based scaling for better color distribution
      const sortedAbsValues = currentValues.map(v => Math.abs(v)).sort((a, b) => a - b);
      if (sortedAbsValues.length > 0) {
        // Use 90th percentile instead of max for better color distribution
        const percentile90Index = Math.floor(sortedAbsValues.length * 0.9);
        const percentile90 = sortedAbsValues[percentile90Index];
        
        // Use the smaller of percentile90 and the current displayMaxAbs
        // This helps show variation in the majority of data while not being dominated by extreme outliers
        if (percentile90 > 0 && percentile90 < displayMaxAbs) {
          displayMaxAbs = percentile90;
        }
      }
    }
    
    setMaxAbs(displayMaxAbs);
    if (onMaxAbsChange) onMaxAbsChange(displayMaxAbs);

    let diffMap: { [iso: string]: number } = {};
    for (const iso in currentFinalFlexMap) {
      if (currentFinalFlexMap.hasOwnProperty(iso) && currentFinalRawMap[iso] !== undefined) {
        diffMap[iso] = currentFinalRawMap[iso] - currentFinalFlexMap[iso];
      }
    }
    
    // Never winsorize difference map (always use original)
    const currentFinalDiffMap = diffMap;

    // Update state variables for use in DataTable
    setFinalFlexMap(currentFinalFlexMap);
    setFinalRawMap(currentFinalRawMap);
    setFinalDiffMap(currentFinalDiffMap);
    
    const diffValues = Object.values(currentFinalDiffMap);
    const computedMaxAbsDiff = Math.max(...diffValues.map(v => Math.abs(v))) || 1;
    setDiffScale(computedMaxAbsDiff);

    // Use original (non-winsorized) values for the EXTREMES panel
    let originalSelectedValues: { [iso: string]: number } = {};
    if (layerMode === 'flex') originalSelectedValues = flexMap;
    else if (layerMode === 'raw') originalSelectedValues = rawMap;
    else if (layerMode === 'difference') originalSelectedValues = diffMap;
    const sortedEntries = Object.entries(originalSelectedValues).sort((a, b) => a[1] - b[1]);
    setLowest(sortedEntries.slice(0, 5) as [string, number][]);
    setHighest(sortedEntries.slice(-5).reverse() as [string, number][]);

    let fillColor: any;
    if (layerMode === 'flex' || layerMode === 'raw') {
      const prop = layerMode;
      // Base color palette from R code: blue (low) to red (high)
      const baseColors = ['#2c7bb6', '#9dcfe4', '#ace7e7', '#ffedaa', '#ffe277', '#fec980', '#d7191c'];
      
      // Color mapping based on sector:
      // makeStops maps -max to first color, +max to last color
      // baseColors = ['#2c7bb6' (blue), ..., '#d7191c' (red)]
      // - Mortality: negative = blue, positive = red => use baseColors (blue to red)
      // - Labor: negative = red, positive = blue => use reversed (red to blue)  
      // - Energy: negative = red, positive = blue => use reversed (red to blue)
      const isLaborOrEnergy = filters.sector?.toLowerCase().includes('labor') || filters.sector?.toLowerCase() === 'energy';
      const colorArray = isLaborOrEnergy ? [...baseColors].reverse() : baseColors;
      
      // Use the actual display max for proper color distribution
      const effectiveMax = displayMaxAbs;
      const stops = makeStops(colorArray, effectiveMax);
      fillColor = [
        'case',
        ['!=', ['get', prop], null],
        [
          'interpolate',
          ['linear'],
          ['get', prop],
          ...stops
        ],
        '#e0e0e0'  // Gray color for countries with no data
      ];
      
    }

     else if (layerMode === 'difference') {
      fillColor = [
        'case',
        ['==', ['<', ['get', 'raw'], 0], ['<', ['get', 'flex'], 0]],
        [
          'interpolate',
          ['linear'],
          ['abs', ['get', 'diff']],
          0, '#d0f0c0',
          computedMaxAbsDiff, '#006400'
        ],
        [
          'interpolate',
          ['linear'],
          ['abs', ['get', 'diff']],
          0, '#f08080',
          computedMaxAbsDiff, '#8b0000'
        ]
      ];
    }

    const displayFillColor = isLoading ? '#e0e0e0' : fillColor;

    const loadGeoData = () => {
      if (geoData) return Promise.resolve(geoData);
      const url = 'https://huggingface.co/datasets/c1587s/flex-damage-impacts/resolve/main/geometries/world_countries_simplified.geojson';
      return fetch(url).then(res => res.json());
    };

    removeExistingLayersAndSources();
    let cleanupHover = () => {};
    
    const setupMapLayers = () => {
      loadGeoData()
        .then(data => {
          data.features.forEach((feature: any) => {
            const isoCode = feature.properties?.ISO || feature.properties?.iso || '';
            // Set processed values for visualization
            feature.properties.flex = isLoading ? null : currentFinalFlexMap[isoCode] ?? null;
            feature.properties.raw = isLoading ? null : currentFinalRawMap[isoCode] ?? null;
            feature.properties.diff = isLoading ? null : currentFinalDiffMap[isoCode] ?? null;
            // Set original values for hover display
            feature.properties.originalFlex = isLoading ? null : flexMap[isoCode] ?? null;
            feature.properties.originalRaw = isLoading ? null : rawMap[isoCode] ?? null;
            feature.properties.originalDiff = isLoading ? null : diffMap[isoCode] ?? null;
          });

          if (!map.getSource('countries')) {
            map.addSource('countries', { type: 'geojson', data });
          } else {
            const source = map.getSource('countries');
            if (source && 'setData' in source) {
              (source as any).setData(data);
            }
          }
          
          if (!map.getLayer('choropleth')) {
            map.addLayer({
              id: 'choropleth',
              type: 'fill',
              source: 'countries',
              paint: {
                'fill-color': displayFillColor,
                'fill-opacity': 0.7,
                'fill-outline-color': '#ccc'
              }
            });
          } else {
            map.setPaintProperty('choropleth', 'fill-color', displayFillColor);
          }
          
          // Always try to create highlight layers if they don't exist
          if (!map.getLayer('country-highlight-border')) {
            console.log('Creating country-highlight-border layer');
            map.addLayer({
              id: 'country-highlight-border',
              type: 'line',
              source: 'countries',
              paint: {
                'line-color': '#00ff00', // Lime color
                'line-width': 4, // Thick border
                'line-opacity': 0 // Start with 0, will be updated on hover
              },
              filter: ['==', ['get', 'ISO'], ''] // Start with empty filter
            });
          }
          
          console.log('Highlight layers check completed');
          cleanupHover = addHoverListeners(map);
        })
        .catch(error => console.error('Error processing GeoJSON:', error));
    };
    
    if (!map.isStyleLoaded()) {
      map.once('style.load', setupMapLayers);
    } else {
      setupMapLayers();
    }
    return () => {
      cleanupHover();
    };
  }, [
    csvData,
    filters,
    geoData,
    layerMode,
    projection,
    winsorizationSettings,
    isLoading,
    onMaxAbsChange,
    removeExistingLayersAndSources
  ]);

  return (
    <div className="map-container" style={{ position: 'relative', height: '100%' }}>
      <LayerToggle layerMode={layerMode} onChange={setLayerMode} />
      <ProjectionSelector 
        selectedProjection={projection} 
        onChange={handleProjectionChange} 
      />
      {layerMode !== 'difference' && (
        <WinsorizationPanel 
          settings={winsorizationSettings}
          onChange={setWinsorizationSettings}
        />
      )}
      <div className="legend-wrapper">
      <Legend
        maxAbs={layerMode === 'difference' ? diffScale : maxAbs}
        diffScale={diffScale}
        hoverInfo={hoverInfo}
        sector={filters.sector}
        ttAnomaly={ttAnomaly}
        layerMode={layerMode}
      />

      </div>
      <div ref={mapContainerRef} className="map" style={{ height: '100%' }} />
              <DataTable 
          lowest={lowest} 
          highest={highest} 
          maxAbs={layerMode === 'difference' ? diffScale : maxAbs}
          sector={filters.sector}
          layerMode={layerMode}
          winsorizationSettings={winsorizationSettings}
          finalFlexMap={finalFlexMap}
          finalRawMap={finalRawMap}
          finalDiffMap={finalDiffMap}
          onCountryHover={handleCountryHover}
        />
    </div>
  );
};

export default MapComponent;
