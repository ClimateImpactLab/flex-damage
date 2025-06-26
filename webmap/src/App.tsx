import React, { useState, useEffect } from 'react';
import SelectorPanel from './SelectorPanel';
import MapComponent from './MapComponent';
import './index.css';

const App: React.FC = () => {
  const [filters, setFilters] = useState({
    ssp: 'SSP3',
    rcp: 'rcp45',
    model: 'high',
    sector: 'Mortality',
    period: '2095_2100'
  });
  const [csvData, setCsvData] = useState<any[]>([]);
  const [animate, setAnimate] = useState<boolean>(false);
  const [geoData, setGeoData] = useState<any>(null);

  // Load GeoJSON only once
  useEffect(() => {
    const geojsonUrl =
      'https://huggingface.co/datasets/c1587s/flex-damage-impacts/resolve/main/geometries/world_countries_simplified.geojson';
    fetch(geojsonUrl)
      .then(res => res.json())
      .then(data => setGeoData(data))
      .catch(error => console.error("Error loading GeoJSON:", error));
  }, []);

  const handleSubmit = (updatedFilters: typeof filters) => {
    setFilters(updatedFilters);
    setCsvData([]);       // Clear any existing CSV data
    setAnimate(true);     // Trigger animation
    
    // Start the random-color animation for 1.5 seconds, then fetch CSV normally
    setTimeout(() => {
      const getFolder = (sector: string) => {
        const lower = sector.toLowerCase();
        if (lower === 'mortality') return 'mortality';
        if (lower === 'agriculture') return 'agriculture';
        if (lower === 'energy') return 'energy';
        if (sector === 'Labor (Combined)') return 'labor_combined';
        if (sector === 'Labor (High Risk)') return 'labor_high';
        if (sector === 'Labor (Low Risk)') return 'labor_low';
        return lower;
      };
      const url = `https://huggingface.co/datasets/c1587s/flex-damage-impacts/resolve/main/${getFolder(
        updatedFilters.sector
      )}/${updatedFilters.ssp}.csv`;
      fetch(url)
        .then(res => res.text())
        .then(text => {
          const rows = text.split('\n').filter(row => row.trim() !== '');
          if (rows.length === 0) {
            console.warn('Empty CSV or unable to parse.');
            setAnimate(false);
            return;
          }
          const headers = rows[0]
            .split(',')
            .map(h => h.trim().toLowerCase().replace(/"/g, ''));
          const data = rows.slice(1)
            .map(row => {
              const values = row.split(',').map(val => val.trim());
              if (values.every(val => val === '')) return null;
              const obj: any = {};
              headers.forEach((h, i) => {
                obj[h] = values[i] || '';
              });
              if (!obj.period || obj.period === '') return null;
              return obj;
            })
            .filter(row => row !== null);
          setCsvData(data);
          setAnimate(false);  // Stop animation, show actual data
        })
        .catch(error => {
          console.error('Error fetching CSV:', error);
          setAnimate(false);
        });
    }, 1500);
  };

  return (
    <div className="map-container" style={{ position: 'relative', height: '100vh' }}>
      <SelectorPanel onSubmit={handleSubmit} />
      <MapComponent csvData={csvData} filters={filters} geoData={geoData} animate={animate} />
    </div>
  );
};

export default App;
