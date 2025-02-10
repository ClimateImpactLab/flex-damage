import { jsx as _jsx, jsxs as _jsxs } from "react/jsx-runtime";
import { useState, useEffect, useMemo, useCallback } from 'react';
import DeckGL from '@deck.gl/react';
import { GeoJsonLayer } from '@deck.gl/layers';
import Map from 'react-map-gl/maplibre';
import 'maplibre-gl/dist/maplibre-gl.css';
import maplibregl from 'maplibre-gl';
import Protobuf from 'pbf';
import { VectorTile } from '@mapbox/vector-tile';
import tileToProtobuf from 'vt-pbf';
// Helper: calcula el centroide de un feature (Polygon o MultiPolygon)
const getCentroid = (feature) => {
    const { type, coordinates } = feature.geometry;
    let coords;
    if (type === 'Polygon') {
        coords = coordinates[0];
    }
    else if (type === 'MultiPolygon') {
        coords = coordinates[0][0];
    }
    else {
        return null;
    }
    const [sumX, sumY] = coords.reduce(([sx, sy], [x, y]) => [sx + x, sy + y], [0, 0]);
    return [sumX / coords.length, sumY / coords.length];
};
const geoJsonUrl = 'https://raw.githubusercontent.com/datasets/geo-countries/master/data/countries.geojson';
function App() {
    // Tipamos el contenedor con CSSProperties
    const containerStyle = {
        position: 'relative',
        width: '100vw',
        height: '100vh',
    };
    // Estado del viewport
    const [viewport, setViewport] = useState({
        longitude: 0,
        latitude: 20,
        zoom: 1.5,
        bearing: 0,
        pitch: 0,
    });
    // Estado para el GeoJSON (usamos el tipo FeatureCollection de 'geojson')
    const [geoData, setGeoData] = useState(null);
    // Estado para los datos de la API
    const [apiData, setApiData] = useState([]);
    const [filters, setFilters] = useState({
        rcp: 'rcp45',
        ssp: 'SSP3',
        model: 'OECD Env-Growth',
        case_gamma: 'all_gamma_values',
        case_population: 'population_weighted',
        impact_source: 'data_meantas',
    });
    const [selectedMetric, setSelectedMetric] = useState('flextotal');
    const [hoverInfo, setHoverInfo] = useState(null);
    const [loading, setLoading] = useState(false);
    const [loadingText, setLoadingText] = useState('');
    const [submitted, setSubmitted] = useState(false);
    // Cargar GeoJSON
    useEffect(() => {
        fetch(geoJsonUrl)
            .then((res) => res.json())
            .then((data) => setGeoData(data))
            .catch((err) => console.error('Error loading GeoJSON:', err));
    }, []);
    // Mapeo ISO a nombre de país
    const isoToCountry = useMemo(() => {
        const mapping = {};
        if (geoData && geoData.features) {
            geoData.features.forEach((feature) => {
                mapping[feature.properties.ISO_A3] = feature.properties.ADMIN;
            });
        }
        return mapping;
    }, [geoData]);
    // Efecto para el spinner ("Loading...")
    useEffect(() => {
        if (loading) {
            const message = "Loading...";
            let index = 0;
            setLoadingText('');
            const interval = setInterval(() => {
                setLoadingText(message.slice(0, index + 1));
                index++;
                if (index === message.length)
                    clearInterval(interval);
            }, 100);
            return () => clearInterval(interval);
        }
        else {
            setLoadingText('');
        }
    }, [loading]);
    // Reverse protocol para MapLibre
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
                        feature: (index) => {
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
    // Función para obtener datos de la API
    const fetchApiData = () => {
        setLoading(true);
        const startTime = Date.now();
        const query = new URLSearchParams();
        Object.entries(filters).forEach(([key, value]) => {
            if (value)
                query.append(key, value);
        });
        fetch(`http://127.0.0.1:5000/api/data?${query.toString()}`)
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
    // Handler para el submit
    const handleSubmit = (e) => {
        e.preventDefault();
        setSubmitted(true);
        fetchApiData();
    };
    // Llamar a la API al cambiar los filtros o tras el submit
    useEffect(() => {
        if (submitted) {
            fetchApiData();
        }
    }, [filters, submitted]);
    // Construir el mapeo de promedios en dos pasos:
    // 1. Acumular sumas y contadores en 'temp'
    // 2. Calcular el promedio y generar 'result'
    const aggregatedMapping = useMemo(() => {
        const temp = {};
        if (apiData) {
            apiData.forEach((item) => {
                const iso = item.iso;
                const value = item[selectedMetric];
                if (typeof value === 'number') {
                    if (!temp[iso]) {
                        temp[iso] = { sum: value, count: 1 };
                    }
                    else {
                        temp[iso].sum += value;
                        temp[iso].count += 1;
                    }
                }
            });
        }
        const result = {};
        Object.keys(temp).forEach((iso) => {
            const avg = temp[iso].sum / temp[iso].count;
            result[iso] = parseFloat(avg.toFixed(2));
        });
        return result;
    }, [apiData, selectedMetric]);
    // Calcular el valor máximo absoluto para normalizar
    const maxAbs = useMemo(() => {
        const values = Object.values(aggregatedMapping);
        if (values.length === 0)
            return 1;
        const maxValue = Math.max(...values.map((v) => Math.abs(v)));
        return maxValue || 1;
    }, [aggregatedMapping]);
    // Función para calcular el color según el valor (escala: negativo → azul, positivo → rojo)
    const getColorForValue = (value) => {
        const norm = Math.max(-1, Math.min(1, value / maxAbs));
        let r, g, b;
        if (norm >= 0) {
            r = 255;
            g = Math.round(255 * (1 - norm));
            b = Math.round(255 * (1 - norm));
        }
        else {
            r = Math.round(255 * (1 + norm));
            g = Math.round(255 * (1 + norm));
            b = 255;
        }
        return [r, g, b];
    };
    // Capa GeoJSON para Deck.GL (se especifica el tipo genérico como 'any')
    const geoJsonLayer = useMemo(() => {
        return new GeoJsonLayer({
            id: `geojson-layer-${selectedMetric}-${Object.keys(aggregatedMapping).length}`,
            data: geoData, // Se castea a any para evitar problemas si geoData es null
            pickable: true,
            stroked: true,
            filled: true,
            lineWidthMinPixels: 1,
            onHover: (info) => setHoverInfo(info),
            getFillColor: (feature) => {
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
    // Top 10 Highest
    const sortedHighest = useMemo(() => {
        return Object.entries(aggregatedMapping)
            .map(([iso, value]) => ({ iso, value }))
            .sort((a, b) => b.value - a.value)
            .slice(0, 10);
    }, [aggregatedMapping]);
    // Top 10 Lowest
    const sortedLowest = useMemo(() => {
        return Object.entries(aggregatedMapping)
            .map(([iso, value]) => ({ iso, value }))
            .sort((a, b) => a.value - b.value)
            .slice(0, 10);
    }, [aggregatedMapping]);
    // Callback para cambios en el viewport
    const handleViewportChange = useCallback((newViewport) => {
        setViewport((prev) => {
            if (prev.longitude !== newViewport.longitude ||
                prev.latitude !== newViewport.latitude ||
                prev.zoom !== newViewport.zoom ||
                prev.bearing !== newViewport.bearing ||
                prev.pitch !== newViewport.pitch) {
                return newViewport;
            }
            return prev;
        });
    }, []);
    // Marker para la leyenda (calculando la posición)
    let marker = null;
    if (hoverInfo &&
        hoverInfo.object &&
        aggregatedMapping[hoverInfo.object.properties.ISO_A3] !== undefined) {
        const hoveredValue = aggregatedMapping[hoverInfo.object.properties.ISO_A3];
        const norm = (hoveredValue + maxAbs) / (2 * maxAbs);
        marker = (_jsx("div", { style: {
                position: 'absolute',
                left: `${norm * 100}%`,
                top: '-4px',
                transform: 'translateX(-50%)',
                width: '8px',
                height: '18px',
                border: '2px solid black',
                boxSizing: 'border-box',
                backgroundColor: 'rgba(0,0,0,0.1)',
            } }));
    }
    return (_jsxs("div", { style: containerStyle, children: [_jsx("div", { style: {
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
                }, children: _jsxs("form", { onSubmit: handleSubmit, style: {
                        display: 'flex',
                        gap: '8px',
                        flexWrap: 'wrap',
                        alignItems: 'center',
                    }, children: [_jsxs("div", { children: [_jsx("label", { children: "RCP:" }), _jsxs("select", { value: filters.rcp, onChange: (e) => setFilters({ ...filters, rcp: e.target.value }), style: { backgroundColor: '#2f2f2f', color: '#fff', border: '1px solid #fff' }, children: [_jsx("option", { value: "rcp45", children: "RCP 45" }), _jsx("option", { value: "rcp85", children: "RCP 85" })] })] }), _jsxs("div", { children: [_jsx("label", { children: "SSP:" }), _jsxs("select", { value: filters.ssp, onChange: (e) => setFilters({ ...filters, ssp: e.target.value }), style: { backgroundColor: '#2f2f2f', color: '#fff', border: '1px solid #fff' }, children: [_jsx("option", { value: "SSP1", children: "SSP 3" }), _jsx("option", { value: "SSP2", children: "SSP 4" }), _jsx("option", { value: "SSP3", children: "SSP 5" }), _jsx("option", { value: "SSP4", children: "SSP 1" }), _jsx("option", { value: "SSP5", children: "SSP 2" })] })] }), _jsxs("div", { children: [_jsx("label", { children: "Model:" }), _jsxs("select", { value: filters.model, onChange: (e) => setFilters({ ...filters, model: e.target.value }), style: { backgroundColor: '#2f2f2f', color: '#fff', border: '1px solid #fff' }, children: [_jsx("option", { value: "OECD Env-Growth", children: "OECD Env Growth" }), _jsx("option", { value: "IIASA GDP", children: "IIASA GDP" })] })] }), _jsxs("div", { children: [_jsx("label", { children: "Case Gamma:" }), _jsxs("select", { value: filters.case_gamma, onChange: (e) => setFilters({ ...filters, case_gamma: e.target.value }), style: { backgroundColor: '#2f2f2f', color: '#fff', border: '1px solid #fff' }, children: [_jsx("option", { value: "all_gamma_values", children: "All Gamma Values" }), _jsx("option", { value: "positive_gamma_only", children: "Positive Gamma Only" })] })] }), _jsxs("div", { children: [_jsx("label", { children: "Case Pop.:" }), _jsxs("select", { value: filters.case_population, onChange: (e) => setFilters({ ...filters, case_population: e.target.value }), style: { backgroundColor: '#2f2f2f', color: '#fff', border: '1px solid #fff' }, children: [_jsx("option", { value: "population_weighted", children: "Population Weighted" }), _jsx("option", { value: "unweighted", children: "Unweighted" })] })] }), _jsxs("div", { children: [_jsx("label", { children: "Impact Src.:" }), _jsxs("select", { value: filters.impact_source, onChange: (e) => setFilters({ ...filters, impact_source: e.target.value }), style: { backgroundColor: '#2f2f2f', color: '#fff', border: '1px solid #fff' }, children: [_jsx("option", { value: "data_meantas", children: "Data Meantas" }), _jsx("option", { value: "fixed_to_2", children: "Fixed To 2" }), _jsx("option", { value: "fixed_to_3", children: "Fixed To 3" }), _jsx("option", { value: "fixed_to_4", children: "Fixed To 4" }), _jsx("option", { value: "data_meantas_country", children: "Data Meantas Country" })] })] }), _jsxs("div", { children: [_jsx("label", { children: "Metric:" }), _jsxs("select", { value: selectedMetric, onChange: (e) => setSelectedMetric(e.target.value), style: { backgroundColor: '#2f2f2f', color: '#fff', border: '1px solid #fff' }, children: [_jsx("option", { value: "flextotal", children: "Flex Total" }), _jsx("option", { value: "rawtotal", children: "Raw Total" })] })] }), _jsxs("div", { style: { display: 'flex', alignItems: 'center' }, children: [_jsx("button", { type: "submit", style: {
                                        backgroundColor: '#333',
                                        color: '#00ff00',
                                        border: '1px solid #00ff00',
                                        cursor: 'pointer',
                                        padding: '4px 8px',
                                    }, children: "Submit" }), loading && (_jsx("span", { style: {
                                        marginLeft: '8px',
                                        fontSize: '12px',
                                        fontFamily: 'monospace',
                                    }, children: loadingText }))] })] }) }), _jsxs("div", { style: {
                    position: 'absolute',
                    top: 70,
                    left: 10,
                    zIndex: 30,
                    display: 'flex',
                    flexDirection: 'column',
                    gap: '10px',
                }, children: [_jsxs("div", { style: {
                            backgroundColor: 'rgba(30,30,30,0.7)',
                            color: '#fff',
                            fontFamily: 'monospace',
                            padding: '10px',
                            borderRadius: '5px',
                            width: '200px',
                            border: '1px solid rgba(255,255,255,0.3)',
                        }, children: [_jsx("div", { style: { textAlign: 'center', marginBottom: '5px', fontWeight: 'bold' }, children: "Top 10" }), _jsx("table", { style: { width: '100%', fontSize: '12px', borderCollapse: 'collapse' }, children: _jsx("tbody", { children: sortedHighest.map(({ iso, value }) => {
                                        const bgColor = getColorForValue(value);
                                        const countryName = isoToCountry[iso] || iso;
                                        return (_jsxs("tr", { style: { backgroundColor: `rgb(${bgColor.join(',')})` }, children: [_jsx("td", { children: countryName }), _jsx("td", { style: { textAlign: 'right' }, children: value.toFixed(2) })] }, iso));
                                    }) }) })] }), _jsx("div", { style: {
                            backgroundColor: 'rgba(30,30,30,0.7)',
                            color: '#fff',
                            fontFamily: 'monospace',
                            padding: '10px',
                            borderRadius: '5px',
                            width: '200px',
                            border: '1px solid rgba(255,255,255,0.3)',
                        }, children: _jsx("table", { style: { width: '100%', fontSize: '12px', borderCollapse: 'collapse' }, children: _jsx("tbody", { children: sortedLowest.map(({ iso, value }) => {
                                    const bgColor = getColorForValue(value);
                                    const countryName = isoToCountry[iso] || iso;
                                    return (_jsxs("tr", { style: { backgroundColor: `rgb(${bgColor.join(',')})` }, children: [_jsx("td", { children: countryName }), _jsx("td", { style: { textAlign: 'right' }, children: value.toFixed(2) })] }, iso));
                                }) }) }) })] }), hoverInfo && hoverInfo.object && (_jsxs("div", { style: {
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
                }, children: [_jsx("div", { children: _jsx("strong", { children: isoToCountry[hoverInfo.object.properties.ISO_A3] ||
                                hoverInfo.object.properties.ISO_A3 }) }), _jsxs("div", { children: ["Value: ", aggregatedMapping[hoverInfo.object.properties.ISO_A3]?.toFixed(2)] })] })), _jsxs("div", { style: {
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
                }, children: [_jsx("div", { style: {
                            position: 'relative',
                            width: '100%',
                            height: '10px',
                            background: 'linear-gradient(to right, blue, white, red)',
                            border: '1px solid rgb(0, 0, 246)',
                            boxSizing: 'border-box',
                        }, children: marker }), _jsxs("div", { style: { display: 'flex', justifyContent: 'space-between', fontSize: '10px', marginTop: '5px' }, children: [_jsx("span", { children: `-${maxAbs}` }), _jsx("span", { children: "0" }), _jsx("span", { children: `+${maxAbs}` })] })] }), _jsx(DeckGL, { initialViewState: viewport, controller: true, layers: [geoJsonLayer], style: { position: 'relative', width: '100%', height: '100%' }, children: _jsx(Map, { ...viewport, style: { width: '100%', height: '100%' }, mapStyle: "https://demotiles.maplibre.org/style.json", transformRequest: (url, resourceType) => {
                        if (url.startsWith('https://demotiles.maplibre.org/tiles/') &&
                            resourceType === 'Tile') {
                            return { url: 'reverse://' + url };
                        }
                        return undefined;
                    }, onMove: (evt) => handleViewportChange(evt.viewState) }) })] }));
}
export default App;
