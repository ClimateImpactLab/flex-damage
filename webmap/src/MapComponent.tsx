// MapComponent.tsx
// Este componente ahora soporta tres modos: "flex" (Flex Damage),
// "raw" (Raw Total) y "difference" (Raw Total - Flex Damage).
// Se muestra un panel toggle (ahora como componente LayerToggle) en la parte superior izquierda.
// La leyenda se posiciona debajo del toggle.
import React, { useEffect, useRef, useState, useCallback } from 'react';
import mapboxgl, { Map, MapMouseEvent } from 'mapbox-gl';
import Legend from './Legend';
import DataTable from './DataTable';
import LayerToggle from './LayerToggle';
import './Map.css';

mapboxgl.accessToken = import.meta.env.VITE_MAPBOX_ACCESS_TOKEN;

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

const MapComponent: React.FC<{
  filters: any;
  csvData: CSVRow[];
  geoData?: any;
  onMaxAbsChange?: (maxAbs: number) => void;
}> = ({ filters, csvData, geoData, onMaxAbsChange }) => {
  const mapContainerRef = useRef<HTMLDivElement | null>(null);
  const mapRef = useRef<Map | null>(null);

  const [layerMode, setLayerMode] = useState<LayerMode>('flex');
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
        zoom: 1.5,
        projection: 'globe'
      });
      mapRef.current.addControl(new mapboxgl.NavigationControl());
      mapRef.current.on('style.load', () => {
        const layersToHide = ['admin-1-boundary', 'admin-0-boundary-disputed', 'admin-0-boundary-bg'];
        layersToHide.forEach(layerId => {
          if (mapRef.current && mapRef.current.getLayer(layerId)) {
            mapRef.current.setLayoutProperty(layerId, 'visibility', 'none');
          }
        });
      });
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
    map.on('mousemove', 'choropleth', handleMouseMove);
    map.on('mouseleave', 'choropleth', handleMouseLeave);
    // Cambiar el cursor a pointer al entrar y restaurarlo al salir.
    map.on('mouseenter', 'choropleth', () => {
      map.getCanvas().style.cursor = 'pointer';
    });
    map.on('mouseleave', 'choropleth', () => {
      map.getCanvas().style.cursor = '';
    });
    return () => {
      map.off('mousemove', 'choropleth', handleMouseMove);
      map.off('mouseleave', 'choropleth', handleMouseLeave);
      map.off('mouseenter', 'choropleth');
      map.off('mouseleave', 'choropleth');
    };
  };

  useEffect(() => {
    const map = mapRef.current;
    if (!map) return;
    if (csvData.length === 0) {
      console.warn('No CSV data to process');
      return;
    }

    const anomalyVal = csvData[0].tt ? parseFloat(csvData[0].tt) : null;
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
          if (['combined', 'high risk', 'low risk'].includes(filters.sector.toLowerCase())) {
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
      if (filters.sector.toLowerCase() === 'mortality') {
        fillColor = [
          'interpolate',
          ['linear'],
          ['coalesce', ['get', prop], 0],
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
          ['coalesce', ['get', prop], 0],
          -computedMaxAbs, '#FF073A',
          -computedMaxAbs / 2, '#FF8C00',
          0, '#FFFFFF',
          computedMaxAbs / 2, '#00FFEA',
          computedMaxAbs, '#00AEFF'
        ];
      }
    } else if (layerMode === 'difference') {
      // Si ambos valores (raw y flex) tienen el mismo signo, se usa una escala de verdes;
      // de lo contrario, se usa una escala de rojo ladrillo.
      fillColor = [
        'case',
        // Comprueba si "raw" y "flex" tienen el mismo signo: se comparan si ambos son menores a 0.
        ['==', ['<', ['get', 'raw'], 0], ['<', ['get', 'flex'], 0]],
        // Si sí (mismo signo): escala de verdes
        [
          'interpolate',
          ['linear'],
          ['abs', ['get', 'diff']],
          0, '#d0f0c0',   // light green
          computedMaxAbsDiff, '#006400'  // dark green
        ],
        // Si no (signos opuestos): escala de rojo ladrillo
        [
          'interpolate',
          ['linear'],
          ['abs', ['get', 'diff']],
          0, '#f08080',   // light brick red
          computedMaxAbsDiff, '#8b0000'  // dark brick red
        ]
      ];
    }

    const loadGeoData = () => {
      if (geoData) return Promise.resolve(geoData);
      else {
        const url = 'https://huggingface.co/datasets/c1587s/flex-damage-impacts/resolve/main/geometries/world_countries_simplified.geojson';
        return fetch(url).then(res => res.json());
      }
    };

    removeExistingLayersAndSources();
    let cleanupHover = () => {};
    if (!map.isStyleLoaded()) {
      map.once('style.load', () => {
        loadGeoData()
          .then(data => {
            data.features.forEach((feature: any) => {
              const isoCode = feature.properties?.ISO || feature.properties?.iso || '';
              feature.properties.flex = flexMap[isoCode] ?? null;
              feature.properties.raw = rawMap[isoCode] ?? null;
              feature.properties.diff = diffMap[isoCode] ?? null;
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
                  'fill-color': fillColor,
                  'fill-opacity': 0.7,
                  'fill-outline-color': '#ccc'
                }
              });
            } else {
              map.setPaintProperty('choropleth', 'fill-color', fillColor);
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
            feature.properties.flex = flexMap[isoCode] ?? null;
            feature.properties.raw = rawMap[isoCode] ?? null;
            feature.properties.diff = diffMap[isoCode] ?? null;
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
                'fill-color': fillColor,
                'fill-opacity': 0.7,
                'fill-outline-color': '#ccc'
              }
            });
          } else {
            map.setPaintProperty('choropleth', 'fill-color', fillColor);
          }
          cleanupHover = addHoverListeners(map);
        })
        .catch(error => console.error('Error processing GeoJSON:', error));
    }
    return () => {
      cleanupHover();
    };
  }, [csvData, filters, geoData, layerMode, onMaxAbsChange, removeExistingLayersAndSources]);

  return (
    <div className="map-container" style={{ position: 'relative', height: '100%' }}>
      {/* Renderizamos el componente toggle separado */}
      <LayerToggle layerMode={layerMode} onChange={setLayerMode} />
      {/* El contenedor de la leyenda se posiciona con CSS (modificado para ubicarse en la parte superior izquierda debajo del toggle) */}
      <div className="legend-wrapper">
        <Legend
          maxAbs={maxAbs}
          diffScale={diffScale}
          hoverInfo={hoverInfo}
          sector={filters.sector}
          ttAnomaly={ttAnomaly}
          layerMode={layerMode}
        />
      </div>
      {/* El contenedor del mapa */}
      <div ref={mapContainerRef} className="map" style={{ height: '100%' }} />
      <DataTable
      lowest={lowest}
      highest={highest}
      maxAbs={layerMode === 'difference' ? diffScale : maxAbs}
      sector={filters.sector}
      layerMode={layerMode}
    />


    </div>
  );
};

export default MapComponent;
