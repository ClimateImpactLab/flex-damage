import React, { useState, useEffect } from 'react';
import SelectorPanel from './SelectorPanel';
import MapComponent from './MapComponent';
import Loading from './Loading';
import './Map.css';

const App: React.FC = () => {
  // Initial filters
  const [filters, setFilters] = useState({
    ssp: 'SSP3',
    rcp: 'rcp45',
    model: 'high',
    metric: 'flextotal',
    sector: 'Mortality',
    period: '2095_2100'
  });
  const [csvData, setCsvData] = useState<any[]>([]);
  const [loading, setLoading] = useState(false);
  // State for storing the geojson (loaded only once)
  const [geoData, setGeoData] = useState<any>(null);

  // Load GeoJSON only once
  useEffect(() => {
    const geojsonUrl =
      'https://huggingface.co/datasets/c1587s/flex-damage-impacts/resolve/main/geometries/world_countries_simplified.geojson';
    fetch(geojsonUrl)
      .then(res => res.json())
      .then(data => {
        setGeoData(data);
      })
      .catch(error => console.error("Error loading GeoJSON:", error));
  }, []);

  const getFolder = (sector: string) => {
    const lower = sector.toLowerCase();
    if (lower === 'mortality') return 'mortality';
    if (lower === 'agriculture') return 'agriculture';
    if (sector === 'Combined') return 'labor_combined';
    if (sector === 'High risk') return 'labor_high';
    if (sector === 'Low risk') return 'labor_low';
    return lower;
  };

  const handleSubmit = (updatedFilters: typeof filters) => {
    console.log('Submitted filters:', updatedFilters);
    setFilters(updatedFilters);
    setCsvData([]);
    setLoading(true);
    fetch(
      `https://huggingface.co/datasets/c1587s/flex-damage-impacts/resolve/main/${getFolder(
        updatedFilters.sector
      )}/${updatedFilters.ssp}.csv`
    )
      .then((res) => res.text())
      .then((text) => {
        const rows = text.split('\n').filter((row) => row.trim() !== '');
        if (rows.length === 0) {
          console.warn('CSV vacío o no se pudo parsear.');
          setLoading(false);
          return;
        }
        const headers = rows[0]
          .split(',')
          .map((h) => h.trim().toLowerCase().replace(/"/g, ''));
        console.log('Headers CSV:', headers);
        const data = rows
          .slice(1)
          .map((row) => {
            const values = row.split(',').map((val) => val.trim());
            if (values.every((val) => val === '')) return null;
            const obj: any = {};
            headers.forEach((h, i) => {
              obj[h] = values[i] || '';
            });
            if (!obj.period || obj.period === '') return null;
            return obj;
          })
          .filter((row) => row !== null);
        console.log('CSV ORIGINAL (parseado):', data);
        setCsvData(data);
        setLoading(false);
      })
      .catch((error) => {
        console.error('Error al cargar el CSV:', error);
        setLoading(false);
      });
  };

  return (
    <div className="map-container" style={{ position: 'relative', height: '100vh' }}>
      <SelectorPanel filters={filters} onSubmit={handleSubmit} />
      {loading && <Loading />}
      <MapComponent
        csvData={csvData}
        filters={filters}
        geoData={geoData}
      />
    </div>
  );
};

export default App;
