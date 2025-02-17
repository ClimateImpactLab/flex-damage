import React, { useState, useEffect, useMemo, useCallback } from 'react';
import DeckGL from '@deck.gl/react';
import { GeoJsonLayer } from '@deck.gl/layers';
import Map from 'react-map-gl/maplibre';
import 'maplibre-gl/dist/maplibre-gl.css';

import maplibregl from 'maplibre-gl';
import Protobuf from 'pbf';
import { VectorTile } from '@mapbox/vector-tile';
import tileToProtobuf from 'vt-pbf';

import type { FeatureCollection } from 'geojson';

// API data interface
interface ApiDataItem {
  iso: string;
  [key: string]: any;
}

// Hover info interface
interface HoverInfo {
  object: any;
  x: number;
  y: number;
}

// Helper: calculate the centroid of a feature (Polygon or MultiPolygon)
const getCentroid = (feature: any): [number, number] | null => {
  const { type, coordinates } = feature.geometry;
  let coords;
  if (type === 'Polygon') {
    coords = coordinates[0];
  } else if (type === 'MultiPolygon') {
    coords = coordinates[0][0];
  } else {
    return null;
  }
  const [sumX, sumY] = coords.reduce(
    ([sx, sy]: [number, number], [x, y]: [number, number]) => [sx + x, sy + y],
    [0, 0]
  );
  return [sumX / coords.length, sumY / coords.length];
};

const geoJsonUrl =
  'https://raw.githubusercontent.com/datasets/geo-countries/master/data/countries.geojson';

function App() {
  // Container style
  const containerStyle: React.CSSProperties = {
    position: 'relative',
    width: '100vw',
    height: '100vh',
  };

  // Viewport state
  const [viewport, setViewport] = useState({
    longitude: 0,
    latitude: 20,
    zoom: 1.5,
    bearing: 0,
    pitch: 0,
  });

  // State for GeoJSON data
  const [geoData, setGeoData] = useState<FeatureCollection | null>(null);
  // State for API data
  const [apiData, setApiData] = useState<ApiDataItem[]>([]);
  // State for filter values
  const [filters, setFilters] = useState({
    rcp: 'rcp45',
    ssp: 'SSP3',
    model: 'OECD Env-Growth',
    case_gamma: 'all_gamma_values',
    case_population: 'population_weighted',
    impact_source: 'data_meantas',
  });
  const [selectedMetric, setSelectedMetric] = useState('flextotal');
  const [hoverInfo, setHoverInfo] = useState<HoverInfo | null>(null);
  const [loading, setLoading] = useState(false);
  const [loadingText, setLoadingText] = useState('');
  const [submitted, setSubmitted] = useState(false);

  // Load GeoJSON on mount
  useEffect(() => {
    fetch(geoJsonUrl)
      .then((res) => res.json())
      .then((data: FeatureCollection) => setGeoData(data))
      .catch((err) => console.error('Error loading GeoJSON:', err));
  }, []);

  // Map ISO to country name
  const isoToCountry = useMemo<Record<string, string>>(() => {
    const mapping: Record<string, string> = {};
    if (geoData && geoData.features) {
      geoData.features.forEach((feature: any) => {
        mapping[feature.properties.ISO_A3] = feature.properties.ADMIN;
      });
    }
    return mapping;
  }, [geoData]);

  // Loading spinner effect
  useEffect(() => {
    if (loading) {
      const message = "Loading...";
      let index = 0;
      setLoadingText('');
      const interval = setInterval(() => {
        setLoadingText(message.slice(0, index + 1));
        index++;
        if (index === message.length) clearInterval(interval);
      }, 100);
      return () => clearInterval(interval);
    } else {
      setLoadingText('');
    }
  }, [loading]);

  // Reverse protocol for MapLibre
  useEffect(() => {
    const protocol = 'reverse';
    maplibregl.addProtocol(protocol, (request) => {
      const url = request.url.replace(protocol + '://', '');
      return fetch(url)
        .then((response) => response.arrayBuffer())
        .then((data) => new VectorTile(new Protobuf(data)))
        .then((tile) => ({
          layers: Object.entries(tile.layers).reduce((acc, [layerId, layer]) => ({
            ...acc,
            [layerId]: {
              ...layer,
              feature: (index: number) => {
                const feature = layer.feature(index);
                if (feature.properties && typeof feature.properties['NAME'] === 'string') {
                  feature.properties['NAME'] = feature.properties['NAME'].split('').reverse().join('');
                }
                if (feature.properties && typeof feature.properties['ABBREV'] === 'string') {
                  feature.properties['ABBREV'] = feature.properties['ABBREV'].split('').reverse().join('');
                }
                return feature;
              }
            }
          }), {})
        }))
        .then((tile) => tileToProtobuf(tile).buffer)
        .then((data) => ({ data }));
    });
  }, []);

  // Function to fetch API data from Heroku endpoint
  const fetchApiData = () => {
    // Clear old data so the map shows no data during loading
    setApiData([]);
    setLoading(true);
    const startTime = Date.now();
    const query = new URLSearchParams();
    Object.entries(filters).forEach(([key, value]) => {
      if (value) query.append(key, value);
    });
    // Use Heroku API endpoint
    fetch(`https://flex-damage-api-425e80ae6f2d.herokuapp.com/api/data?${query.toString()}`)
      .then((res) => res.json())
      .then((data) => {
        const elapsed = Date.now() - startTime;
        const delay = Math.max(0, 1000 - elapsed);
        setTimeout(() => {
          setApiData(data.data);
          setLoading(false);
        }, delay);
      })
      .catch((err) => {
        console.error('Error fetching API data:', err);
        setLoading(false);
      });
  };

  // Handle form submit
  const handleSubmit = (e: React.FormEvent<HTMLFormElement>) => {
    e.preventDefault();
    setSubmitted(true);
    fetchApiData();
  };

  // Fetch API data when filters change and after submit
  useEffect(() => {
    if (submitted) {
      fetchApiData();
    }
  }, [filters, submitted]);

  // Aggregate API data by ISO code
  const aggregatedMapping = useMemo<Record<string, number>>(() => {
    const temp: Record<string, { sum: number; count: number }> = {};
    if (apiData) {
      apiData.forEach((item) => {
        const iso = item.iso;
        const value = item[selectedMetric];
        if (typeof value === 'number') {
          if (!temp[iso]) {
            temp[iso] = { sum: value, count: 1 };
          } else {
            temp[iso].sum += value;
            temp[iso].count += 1;
          }
        }
      });
    }
    const result: Record<string, number> = {};
    Object.keys(temp).forEach((iso) => {
      const avg = temp[iso].sum / temp[iso].count;
      result[iso] = parseFloat(avg.toFixed(2));
    });
    return result;
  }, [apiData, selectedMetric]);

  // Calculate max absolute value for normalization
  const maxAbs = useMemo<number>(() => {
    const values = Object.values(aggregatedMapping);
    if (values.length === 0) return 1;
    const maxValue = Math.max(...values.map((v) => Math.abs(v)));
    return maxValue || 1;
  }, [aggregatedMapping]);

  // Get color based on value (blue for negative, red for positive)
  const getColorForValue = (value: number): number[] => {
    const norm = Math.max(-1, Math.min(1, value / maxAbs));
    let r, g, b;
    if (norm >= 0) {
      r = 255;
      g = Math.round(255 * (1 - norm));
      b = Math.round(255 * (1 - norm));
    } else {
      r = Math.round(255 * (1 + norm));
      g = Math.round(255 * (1 + norm));
      b = 255;
    }
    return [r, g, b];
  };

  // Create GeoJsonLayer for Deck.GL
  const geoJsonLayer = useMemo(() => {
    return new GeoJsonLayer<any>({
      id: `geojson-layer-${selectedMetric}-${Object.keys(aggregatedMapping).length}`,
      data: geoData as any,
      pickable: true,
      stroked: true,
      filled: true,
      lineWidthMinPixels: 1,
      onHover: (info: any) => setHoverInfo(info),
      getFillColor: (feature: any) => {
        const iso = feature.properties.ISO_A3;
        const value = aggregatedMapping[iso];
        if (typeof value !== 'number') {
          return new Uint8ClampedArray([200, 200, 200, 255]);
        }
        return new Uint8ClampedArray([...getColorForValue(value), 255]);
      },
      getLineColor: new Uint8ClampedArray([50, 50, 50, 255]),
    });
  }, [geoData, aggregatedMapping, maxAbs, selectedMetric]);

  // Top 10 highest values
  const sortedHighest = useMemo(() => {
    return Object.entries(aggregatedMapping)
      .map(([iso, value]) => ({ iso, value }))
      .sort((a, b) => b.value - a.value)
      .slice(0, 10);
  }, [aggregatedMapping]);

  // Top 10 lowest values
  const sortedLowest = useMemo(() => {
    return Object.entries(aggregatedMapping)
      .map(([iso, value]) => ({ iso, value }))
      .sort((a, b) => a.value - b.value)
      .slice(0, 10);
  }, [aggregatedMapping]);

  // Update viewport state on change
  const handleViewportChange = useCallback((newViewport: any) => {
    setViewport((prev) => {
      if (
        prev.longitude !== newViewport.longitude ||
        prev.latitude !== newViewport.latitude ||
        prev.zoom !== newViewport.zoom ||
        prev.bearing !== newViewport.bearing ||
        prev.pitch !== newViewport.pitch
      ) {
        return newViewport;
      }
      return prev;
    });
  }, []);

  // Create marker for legend based on hover info
  let marker: React.ReactElement | null = null;
  if (
    hoverInfo &&
    hoverInfo.object &&
    aggregatedMapping[hoverInfo.object.properties.ISO_A3] !== undefined
  ) {
    const hoveredValue = aggregatedMapping[hoverInfo.object.properties.ISO_A3];
    const norm = (hoveredValue + maxAbs) / (2 * maxAbs);
    marker = (
      <div
        style={{
          position: 'absolute',
          left: `${norm * 100}%`,
          top: '-4px',
          transform: 'translateX(-50%)',
          width: '8px',
          height: '18px',
          border: '2px solid black',
          boxSizing: 'border-box',
          backgroundColor: 'rgba(0,0,0,0.1)',
        }}
      ></div>
    );
  }

  return (
    <div style={containerStyle}>
      {/* Control panel */}
      <div
        style={{
          position: 'absolute',
          top: 10,
          left: 10,
          zIndex: 30,
          backgroundColor: 'rgba(47,47,47,0.9)',
          color: '#fff',
          fontFamily: 'monospace',
          padding: '8px',
          borderRadius: '5px',
          display: 'flex',
          gap: '8px',
          flexWrap: 'wrap',
          alignItems: 'center',
        }}
      >
        <form
          onSubmit={handleSubmit}
          style={{
            display: 'flex',
            gap: '8px',
            flexWrap: 'wrap',
            alignItems: 'center',
          }}
        >
          {/* Filter fields */}
          <div>
            <label>RCP:</label>
            <select
              value={filters.rcp}
              onChange={(e) => setFilters({ ...filters, rcp: e.target.value })}
              style={{ backgroundColor: '#2f2f2f', color: '#fff', border: '1px solid #fff' }}
            >
              <option value="rcp45">RCP 45</option>
              <option value="rcp85">RCP 85</option>
            </select>
          </div>
          <div>
            <label>SSP:</label>
            <select
              value={filters.ssp}
              onChange={(e) => setFilters({ ...filters, ssp: e.target.value })}
              style={{ backgroundColor: '#2f2f2f', color: '#fff', border: '1px solid #fff' }}
            >
              <option value="SSP1">SSP 1</option>
              <option value="SSP2">SSP 2</option>
              <option value="SSP3">SSP 3</option>
              <option value="SSP4">SSP 4</option>
              <option value="SSP5">SSP 5</option>
            </select>
          </div>
          <div>
            <label>Model:</label>
            <select
              value={filters.model}
              onChange={(e) => setFilters({ ...filters, model: e.target.value })}
              style={{ backgroundColor: '#2f2f2f', color: '#fff', border: '1px solid #fff' }}
            >
              <option value="OECD Env-Growth">OECD Env Growth</option>
              <option value="IIASA GDP">IIASA GDP</option>
            </select>
          </div>
          <div>
            <label>Case Gamma:</label>
            <select
              value={filters.case_gamma}
              onChange={(e) =>
                setFilters({ ...filters, case_gamma: e.target.value })
              }
              style={{ backgroundColor: '#2f2f2f', color: '#fff', border: '1px solid #fff' }}
            >
              <option value="all_gamma_values">All Gamma Values</option>
              <option value="positive_gamma_only">Positive Gamma Only</option>
            </select>
          </div>
          <div>
            <label>Case Pop.:</label>
            <select
              value={filters.case_population}
              onChange={(e) =>
                setFilters({ ...filters, case_population: e.target.value })
              }
              style={{ backgroundColor: '#2f2f2f', color: '#fff', border: '1px solid #fff' }}
            >
              <option value="population_weighted">Population Weighted</option>
              <option value="unweighted">Unweighted</option>
            </select>
          </div>
          <div>
            <label>Impact Src.:</label>
            <select
              value={filters.impact_source}
              onChange={(e) =>
                setFilters({ ...filters, impact_source: e.target.value })
              }
              style={{ backgroundColor: '#2f2f2f', color: '#fff', border: '1px solid #fff' }}
            >
              <option value="data_meantas">Data Meantas</option>
              <option value="fixed_to_2">Fixed To 2</option>
              <option value="fixed_to_3">Fixed To 3</option>
              <option value="fixed_to_4">Fixed To 4</option>
              <option value="data_meantas_country">Data Meantas Country</option>
            </select>
          </div>
          <div>
            <label>Metric:</label>
            <select
              value={selectedMetric}
              onChange={(e) => setSelectedMetric(e.target.value)}
              style={{ backgroundColor: '#2f2f2f', color: '#fff', border: '1px solid #fff' }}
            >
              <option value="flextotal">Flex Total</option>
              <option value="rawtotal">Raw Total</option>
            </select>
          </div>
          <div style={{ display: 'flex', alignItems: 'center' }}>
            <button
              type="submit"
              style={{
                backgroundColor: '#333',
                color: '#00ff00',
                border: '1px solid #00ff00',
                cursor: 'pointer',
                padding: '4px 8px',
              }}
            >
              Submit
            </button>
            {loading && (
              <span
                style={{
                  marginLeft: '8px',
                  fontSize: '12px',
                  fontFamily: 'monospace',
                }}
              >
                {loadingText}
              </span>
            )}
          </div>
        </form>
      </div>

      {/* Top 10 Tables */}
      <div
        style={{
          position: 'absolute',
          top: 100,
          left: 10,
          zIndex: 30,
          display: 'flex',
          flexDirection: 'column',
          gap: '10px',
        }}
      >
        {/* Top 10 Highest */}
        <div
          style={{
            backgroundColor: 'rgba(30,30,30,0.7)',
            color: '#fff',
            fontFamily: 'monospace',
            padding: '10px',
            borderRadius: '5px',
            width: '200px',
            border: '1px solid rgba(255,255,255,0.3)',
          }}
        >
          <div style={{ textAlign: 'center', marginBottom: '5px', fontWeight: 'bold' }}>
            Top 10
          </div>
          <table style={{ width: '100%', fontSize: '12px', borderCollapse: 'collapse' }}>
            <tbody>
              {sortedHighest.map(({ iso, value }) => {
                const bgColor = getColorForValue(value);
                const countryName = isoToCountry[iso] || iso;
                return (
                  <tr key={iso} style={{ backgroundColor: `rgb(${bgColor.join(',')})` }}>
                    <td>{countryName}</td>
                    <td style={{ textAlign: 'right' }}>{value.toFixed(2)}</td>
                  </tr>
                );
              })}
            </tbody>
          </table>
        </div>

        {/* Top 10 Lowest */}
        <div
          style={{
            backgroundColor: 'rgba(30,30,30,0.7)',
            color: '#fff',
            fontFamily: 'monospace',
            padding: '10px',
            borderRadius: '5px',
            width: '200px',
            border: '1px solid rgba(255,255,255,0.3)',
          }}
        >
          <table style={{ width: '100%', fontSize: '12px', borderCollapse: 'collapse' }}>
            <tbody>
              {sortedLowest.map(({ iso, value }) => {
                const bgColor = getColorForValue(value);
                const countryName = isoToCountry[iso] || iso;
                return (
                  <tr key={iso} style={{ backgroundColor: `rgb(${bgColor.join(',')})` }}>
                    <td>{countryName}</td>
                    <td style={{ textAlign: 'right' }}>{value.toFixed(2)}</td>
                  </tr>
                );
              })}
            </tbody>
          </table>
        </div>
      </div>

      {/* Warning message for no data */}
      {!loading && submitted && apiData.length === 0 && (
        <div
          style={{
            position: 'absolute',
            top: '50%',
            left: '50%',
            transform: 'translate(-50%, -50%)',
            zIndex: 40,
            backgroundColor: 'rgba(0,0,0,0.7)',
            color: '#fff',
            padding: '20px',
            borderRadius: '5px',
            fontFamily: 'monospace',
          }}
        >
          No data available for these filters.
        </div>
      )}

      {/* Tooltip on hover */}
      {hoverInfo && hoverInfo.object && (
        <div
          style={{
            position: 'absolute',
            zIndex: 30,
            pointerEvents: 'none',
            left: hoverInfo.x,
            top: hoverInfo.y,
            background: 'rgba(0,0,0,0.7)',
            color: '#fff',
            padding: '4px',
            borderRadius: '3px',
            fontSize: '10px',
          }}
        >
          <div>
            <strong>
              {isoToCountry[hoverInfo.object.properties.ISO_A3] ||
                hoverInfo.object.properties.ISO_A3}
            </strong>
          </div>
          <div>
            Value: {aggregatedMapping[hoverInfo.object.properties.ISO_A3]?.toFixed(2)}
          </div>
        </div>
      )}

      {/* Legend */}
      <div
        style={{
          position: 'absolute',
          bottom: 10,
          left: 10,
          zIndex: 20,
          backgroundColor: 'rgba(30,30,30,1)',
          color: '#ddebdd',
          fontFamily: 'monospace',
          borderRadius: '5px',
          width: '200px',
          padding: '10px',
          boxSizing: 'border-box',
        }}
      >
        <div
          style={{
            position: 'relative',
            width: '100%',
            height: '10px',
            background: 'linear-gradient(to right, blue, white, red)',
            border: '1px solid rgb(0, 0, 246)',
            boxSizing: 'border-box',
          }}
        >
          {marker}
        </div>
        <div style={{ display: 'flex', justifyContent: 'space-between', fontSize: '10px', marginTop: '5px' }}>
          <span>{`-${maxAbs}`}</span>
          <span>0</span>
          <span>{`+${maxAbs}`}</span>
        </div>
      </div>

      {/* Map with DeckGL */}
      <DeckGL
        initialViewState={viewport}
        controller={true}
        layers={[geoJsonLayer]}
        style={{ position: 'relative', width: '100%', height: '100%' }}
      >
        <Map
          {...viewport}
          style={{ width: '100%', height: '100%' }}
          mapStyle="https://demotiles.maplibre.org/style.json"
          transformRequest={(url, resourceType) => {
            if (
              url.startsWith('https://demotiles.maplibre.org/tiles/') &&
              resourceType === 'Tile'
            ) {
              return { url: 'reverse://' + url };
            }
            return undefined;
          }}
          onMove={(evt) => handleViewportChange(evt.viewState)}
        />
      </DeckGL>
    </div>
  );
}

export default App;
