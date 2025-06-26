// SelectorPanel.tsx
import React, { useState, ChangeEvent } from 'react';
import CircleLoader from "react-spinners/CircleLoader";

interface Filters {
  ssp: string;
  rcp: string;
  model: string;
  sector: string;
  period: string;
}

interface SelectorPanelProps {
  filters: Filters;
  // The onSubmit callback can optionally return a promise if asynchronous actions are performed.
  onSubmit: (filters: Filters) => Promise<void> | void;
}

const SelectorPanel: React.FC<SelectorPanelProps> = ({ filters, onSubmit }) => {
  const [localFilters, setLocalFilters] = useState<Filters>(filters);
  const [loading, setLoading] = useState(false);

  const handleChange = (e: ChangeEvent<HTMLSelectElement>) => {
    const { name, value } = e.target;
    setLocalFilters(prev => ({ ...prev, [name]: value }));
  };

  const handleSubmit = async () => {
    setLoading(true);
    const startTime = Date.now();
    // Ensure onSubmit is treated as a promise even if it is not asynchronous.
    await Promise.resolve(onSubmit(localFilters));
    const elapsed = Date.now() - startTime;
    const minWait = 1500; // Minimum wait of 1.5 seconds.
    if (elapsed < minWait) {
      await new Promise(resolve => setTimeout(resolve, minWait - elapsed));
    }
    setLoading(false);
  };

  return (
    <div className="selector-panel">
      <div className="selector-group">
        <label>SSP:</label>
        <select name="ssp" value={localFilters.ssp} onChange={handleChange}>
          {["SSP1", "SSP2", "SSP3", "SSP4"].map(opt => (
            <option key={opt} value={opt}>{opt}</option>
          ))}
        </select>
      </div>
      <div className="selector-group">
        <label>RCP:</label>
        <select name="rcp" value={localFilters.rcp} onChange={handleChange}>
          {["rcp45", "rcp85"].map(opt => (
            <option key={opt} value={opt}>{opt}</option>
          ))}
        </select>
      </div>
      <div className="selector-group">
        <label>Model:</label>
        <select name="model" value={localFilters.model} onChange={handleChange}>
          {["high", "low"].map(opt => (
            <option key={opt} value={opt}>{opt}</option>
          ))}
        </select>
      </div>
      <div className="selector-group">
        <label>Sector:</label>
        <select name="sector" value={localFilters.sector} onChange={handleChange}>
          {["Mortality", "Labor (Combined)", "Labor (High Risk)", "Labor (Low Risk)", "Agriculture", "Energy"].map(opt => (
            <option key={opt} value={opt}>{opt}</option>
          ))}
        </select>
      </div>
      <div className="selector-group">
        <label>Period:</label>
        <select name="period" value={localFilters.period} onChange={handleChange}>
          {[
            { value: "2020_2039", label: "2039" },
            { value: "2040_2059", label: "2059" },
            { value: "2060_2079", label: "2079" },
            { value: "2080_2094", label: "2094" },
            { value: "2095_2100", label: "2100" }
          ].map(opt => (
            <option key={opt.value} value={opt.value}>{opt.label}</option>
          ))}
        </select>
      </div>
      <div style={{ display: 'flex', alignItems: 'center' }}>
        <button onClick={handleSubmit} disabled={loading}>Submit</button>
        {loading && (
          <div style={{ marginLeft: '8px' }}>
            <CircleLoader size={20} color="#20e998" />
          </div>
        )}
      </div>
    </div>
  );
};

export default SelectorPanel;
