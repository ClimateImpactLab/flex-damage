// SelectorPanel.tsx
import React, { useState, ChangeEvent } from 'react';

interface Filters {
  ssp: string;
  rcp: string;
  model: string;
  metric: string;
  sector: string;
  period: string;
}

interface SelectorPanelProps {
  filters: Filters;
  onSubmit: (filters: Filters) => void;
}

const SelectorPanel: React.FC<SelectorPanelProps> = ({ filters, onSubmit }) => {
  const [localFilters, setLocalFilters] = useState<Filters>(filters);

  const handleChange = (e: ChangeEvent<HTMLSelectElement>) => {
    const { name, value } = e.target;
    setLocalFilters(prev => ({ ...prev, [name]: value }));
  };

  return (
    <div className="selector-panel">
      {["ssp", "rcp", "model", "metric", "sector", "period"].map(field => (
        <div key={field} className="selector-group">
          <label>{field.toUpperCase()}:</label>
          {field === "sector" ? (
            <select name={field} value={localFilters[field]} onChange={handleChange}>
              {["Mortality", "Combined", "High risk", "Low risk", "Agriculture"].map(opt => (
                <option key={opt} value={opt}>{opt}</option>
              ))}
            </select>
          ) : field === "metric" ? (
            <select name={field} value={localFilters[field]} onChange={handleChange}>
              {["flextotal", "rawtotal"].map(opt => (
                <option key={opt} value={opt}>{opt}</option>
              ))}
            </select>
          ) : field === "ssp" ? (
            <select name={field} value={localFilters[field]} onChange={handleChange}>
              {["SSP1", "SSP2", "SSP3", "SSP4"].map(opt => (
                <option key={opt} value={opt}>{opt}</option>
              ))}
            </select>
          ) : field === "rcp" ? (
            <select name={field} value={localFilters[field]} onChange={handleChange}>
              {["rcp45", "rcp85"].map(opt => (
                <option key={opt} value={opt}>{opt}</option>
              ))}
            </select>
          ) : field === "model" ? (
            <select name={field} value={localFilters[field]} onChange={handleChange}>
              {["high", "low"].map(opt => (
                <option key={opt} value={opt}>{opt}</option>
              ))}
            </select>
          ) : field === "period" ? (
            <select name={field} value={localFilters[field]} onChange={handleChange}>
              {["2020_2039", "2040_2059", "2060_2079", "2080_2094", "2095_2100"].map(opt => (
                <option key={opt} value={opt}>{opt}</option>
              ))}
            </select>
          ) : null}
        </div>
      ))}
      <button onClick={() => onSubmit(localFilters)}>Submit</button>
    </div>
  );
};

export default SelectorPanel;
