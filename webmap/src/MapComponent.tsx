// MapComponent.tsx
import React, { useEffect, useRef, useState, useCallback } from 'react';
import mapboxgl, { Map, MapMouseEvent } from 'mapbox-gl';
import Legend from './Legend';
import DataTable from './DataTable';
import LayerToggle from './LayerToggle';
import ProjectionSelector, { ProjectionType } from './ProjectionSelector';
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
  const isMortality = filters.sector?.toLowerCase() === 'mortality';
  const mapContainerRef = useRef<HTMLDivElement | null>(null);
  const mapRef = useRef<Map | null>(null);

  const [layerMode, setLayerMode] = useState<LayerMode>('flex');
  const [projection, setProjection] = useState<ProjectionType>('naturalEarth');
  const [maxAbs, setMaxAbs] = useState<number>(1);
  const [diffScale, setDiffScale] = useState<number>(1);
  const [lowest, setLowest] = useState<[string, number][]>([]);
  const [highest, setHighest] = useState<[string, number][]>([]);
  const [ttAnomaly, setTtAnomaly] = useState<number | null>(null);
  const [hoverInfo, setHoverInfo] = useState<HoverInfo | null>(null);

  const removeExistingLayersAndSources = useCallback(() => {
    if (!mapRef.current) return;
    const map = mapRef.current;
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
      mapRef.current.on('style.load', () => {
        const layersToHide = ['admin-1-boundary', 'admin-0-boundary-disputed', 'admin-0-boundary-bg'];
        layersToHide.forEach(layerId => {
          if (mapRef.current?.getLayer(layerId)) {
            mapRef.current.setLayoutProperty(layerId, 'visibility', 'none');
          }
        });
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

  const addHoverListeners = (map: Map) => {
    const handleMouseMove = (e: MapMouseEvent) => {
      if (!e.features || !e.features.length) return;
      const feature = e.features[0];
      let value: number | null = null;
      if (layerMode === 'difference') {
        value = feature.properties?.diff ?? null;
      } else {
        value = feature.properties ? feature.properties[layerMode] ?? null : null;
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

    console.log("CSV fields:", Object.keys(csvData[0] || {}));
    console.log("First row:", csvData[0]);

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
    const filterModel = filters.model.toLowerCase();

    let flexMap: { [iso: string]: number } = {};
    let rawMap: { [iso: string]: number } = {};

    csvData.forEach((d: CSVRow) => {
      const cleanedRowPeriod = d.period ? d.period.replace(/"/g, '').trim().toLowerCase() : '';
      const cleanedRowSSP = d.ssp ? d.ssp.replace(/"/g, '').trim().toLowerCase() : '';
      const cleanedRowRCP = d.rcp ? d.rcp.replace(/"/g, '').trim().toLowerCase() : '';
      const cleanedRowModel = d.model ? d.model.replace(/"/g, '').trim().toLowerCase() : '';
      if (
        cleanedRowPeriod === filterPeriod &&
        cleanedRowSSP === filterSSP &&
        cleanedRowRCP === filterRCP &&
        cleanedRowModel === filterModel
      ) {
        const iso = d.iso ? d.iso.replace(/"/g, '').trim() : '';
        let flexVal = d.flextotal ? parseFloat(d.flextotal) : NaN;
        let rawVal = d.rawtotal ? parseFloat(d.rawtotal) : NaN;
        if (!isNaN(flexVal) && !isNaN(rawVal) && iso) {
          if (["combined", "high risk", "low risk"].includes(filters.sector.toLowerCase())) {
            flexVal = flexVal / 60;
            rawVal = rawVal / 60;
          }
          if (flexMap[iso] === undefined) flexMap[iso] = flexVal;
          if (rawMap[iso] === undefined) rawMap[iso] = rawVal;
        }
      }
    });

    const combinedValues = Object.values(flexMap).concat(Object.values(rawMap));
    const computedMaxAbs = Math.max(...combinedValues.map(v => Math.abs(v))) || 1;
    setMaxAbs(computedMaxAbs);
    if (onMaxAbsChange) onMaxAbsChange(computedMaxAbs);

    const fixedMaxAbsMortality = 300;
    const displayMaxAbs = isMortality ? fixedMaxAbsMortality : computedMaxAbs;

    let diffMap: { [iso: string]: number } = {};
    for (const iso in flexMap) {
      if (flexMap.hasOwnProperty(iso) && rawMap[iso] !== undefined) {
        diffMap[iso] = rawMap[iso] - flexMap[iso];
      }
    }
    const diffValues = Object.values(diffMap);
    const computedMaxAbsDiff = Math.max(...diffValues.map(v => Math.abs(v))) || 1;
    setDiffScale(computedMaxAbsDiff);

    let selectedValues: { [iso: string]: number } = {};
    if (layerMode === 'flex') selectedValues = flexMap;
    else if (layerMode === 'raw') selectedValues = rawMap;
    else if (layerMode === 'difference') selectedValues = diffMap;
    const sortedEntries = Object.entries(selectedValues).sort((a, b) => a[1] - b[1]);
    setLowest(sortedEntries.slice(0, 5) as [string, number][]);
    setHighest(sortedEntries.slice(-5).reverse() as [string, number][]);

    let fillColor: any;
    if (layerMode === 'flex' || layerMode === 'raw') {
      const prop = layerMode;
      // choose your five anchors
      const anchorCols = isMortality
        ? ['#00AEFF', '#00FFEA', '#FFFFFF', '#FF8C00', '#FF073A']
        : ['#FF073A', '#FF8C00', '#FFFFFF', '#00FFEA', '#00AEFF'];
      // generate smooth stops from –displayMaxAbs to +displayMaxAbs
      const effectiveMax = displayMaxAbs * 0.5;  // 50% of real max
      const stops       = makeStops(anchorCols, effectiveMax);
      fillColor = [
        'interpolate',
        ['linear'],
        ['coalesce', ['get', prop], 0],
        ...stops
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
    if (!map.isStyleLoaded()) {
      map.once('style.load', () => {
        loadGeoData()
          .then(data => {
            data.features.forEach((feature: any) => {
              const isoCode = feature.properties?.ISO || feature.properties?.iso || '';
              feature.properties.flex = isLoading ? null : flexMap[isoCode] ?? null;
              feature.properties.raw = isLoading ? null : rawMap[isoCode] ?? null;
              feature.properties.diff = isLoading ? null : diffMap[isoCode] ?? null;
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
            cleanupHover = addHoverListeners(map);
          })
          .catch(error => console.error('Error processing GeoJSON:', error));
      });
    } else {
      loadGeoData()
        .then(data => {
          data.features.forEach((feature: any) => {
            const isoCode = feature.properties?.ISO || feature.properties?.iso || '';
            feature.properties.flex = isLoading ? null : flexMap[isoCode] ?? null;
            feature.properties.raw = isLoading ? null : rawMap[isoCode] ?? null;
            feature.properties.diff = isLoading ? null : diffMap[isoCode] ?? null;
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
          cleanupHover = addHoverListeners(map);
        })
        .catch(error => console.error('Error processing GeoJSON:', error));
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
      <div className="legend-wrapper">
      <Legend
        maxAbs={layerMode === 'difference' ? diffScale : (isMortality ? 300 : maxAbs)}
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
        maxAbs={layerMode === 'difference' ? diffScale : (isMortality ? 300 : maxAbs)}
        sector={filters.sector}
        layerMode={layerMode}
      />
    </div>
  );
};

export default MapComponent;
