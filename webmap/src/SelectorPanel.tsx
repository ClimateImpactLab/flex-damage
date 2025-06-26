// SelectorPanel.tsx
import React, { useState, useEffect, ChangeEvent } from 'react';
import CircleLoader from "react-spinners/CircleLoader";
import './SelectorPanel.css';

interface Filters {
  ssp: string;
  rcp: string;
  model: string;
  sector: string;
  period: string;
}

interface SelectorPanelProps {
  // The onSubmit callback can optionally return a promise if asynchronous actions are performed.
  onSubmit: (filters: Filters) => Promise<void> | void;
}

const SelectorPanel: React.FC<SelectorPanelProps> = ({ onSubmit }) => {
  // Initialize with empty values - user must select everything
  const [localFilters, setLocalFilters] = useState<Filters>({
    sector: '',
    ssp: '',
    rcp: '',
    model: '',
    period: '2095_2100'  // Default to 2099
  });
  const [loading, setLoading] = useState(false);
  const [availableSSPs, setAvailableSSPs] = useState<string[]>([]);
  const [availableRCPs, setAvailableRCPs] = useState<string[]>([]);
  const [availableModels, setAvailableModels] = useState<string[]>([]);
  const [loadingSSPs, setLoadingSSPs] = useState(false);
  const [loadingRCPs, setLoadingRCPs] = useState(false);
  const [loadingModels, setLoadingModels] = useState(false);

  // Helper function to get the folder name for a sector
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

  // Helper function to map model names for display
  const mapModelForDisplay = (modelValue: string, sector: string): string => {
    if (sector.toLowerCase() === 'energy') {
      if (modelValue.toLowerCase() === 'oecd env-growth') return 'high';
      if (modelValue.toLowerCase() === 'iiasa gdp') return 'low';
    }
    return modelValue.toLowerCase();
  };

  // Function to check available SSP files for a given sector
  const checkAvailableSSPs = async (sector: string) => {
    const folderName = getFolder(sector);
    const possibleSSPs = ['SSP1', 'SSP2', 'SSP3', 'SSP4', 'SSP5'];
    const availableSSPs: string[] = [];

    setLoadingSSPs(true);
    // Clear dependent fields when loading new SSPs
    setAvailableRCPs([]);
    setAvailableModels([]);

    // Check each possible SSP file
    for (const ssp of possibleSSPs) {
      try {
        const url = `https://huggingface.co/datasets/c1587s/flex-damage-impacts/resolve/main/${folderName}/${ssp}.csv`;
        const response = await fetch(url, { method: 'HEAD' });
        if (response.ok) {
          availableSSPs.push(ssp);
        }
      } catch (error) {
        // File doesn't exist, skip
        console.log(`${ssp} not available for ${sector}`);
      }
    }

    setLoadingSSPs(false);
    
    if (availableSSPs.length > 0) {
      setAvailableSSPs(availableSSPs);
    } else {
      // Fallback to default SSPs if none found
      setAvailableSSPs(['SSP1', 'SSP2', 'SSP3', 'SSP4']);
    }
  };

  // Function to check available RCP values by examining CSV content
  const checkAvailableRCPs = async (sector: string, ssp: string) => {
    if (!sector || !ssp) {
      setAvailableRCPs([]);
      return;
    }

    const folderName = getFolder(sector);
    const possibleRCPs = ['rcp26', 'rcp45', 'rcp60', 'rcp85'];
    const availableRCPs: string[] = [];

    setLoadingRCPs(true);
    // Clear models when loading new RCPs
    setAvailableModels([]);

    try {
      const url = `https://huggingface.co/datasets/c1587s/flex-damage-impacts/resolve/main/${folderName}/${ssp}.csv`;
      const response = await fetch(url);
      
      if (response.ok) {
        const text = await response.text();
        const lines = text.split('\n');
        
        if (lines.length > 1) {
          // Get header to find RCP column
          const headers = lines[0].split(',').map(h => h.trim().toLowerCase().replace(/"/g, ''));
          const rcpColumnIndex = headers.findIndex(h => h === 'rcp');
          
          if (rcpColumnIndex !== -1) {
            // Extract unique RCP values from the data
            const rcpValues = new Set<string>();
            
            for (let i = 1; i < lines.length; i++) {
              const values = lines[i].split(',');
              if (values[rcpColumnIndex]) {
                const rcpValue = values[rcpColumnIndex].trim().replace(/"/g, '').toLowerCase();
                if (rcpValue && possibleRCPs.includes(rcpValue)) {
                  rcpValues.add(rcpValue);
                }
              }
            }
            
            availableRCPs.push(...Array.from(rcpValues).sort());
          }
        }
      }
    } catch (error) {
      console.log(`Error checking RCPs for ${sector}/${ssp}:`, error);
    }

    setLoadingRCPs(false);
    
    if (availableRCPs.length > 0) {
      setAvailableRCPs(availableRCPs);
    } else {
      // Fallback to default RCPs if none found
      setAvailableRCPs(['rcp45', 'rcp85']);
    }
  };

  // Function to check available Model values by examining CSV content
  const checkAvailableModels = async (sector: string, ssp: string, rcp: string) => {
    if (!sector || !ssp || !rcp) {
      setAvailableModels([]);
      return;
    }

    const folderName = getFolder(sector);
    const availableModels: string[] = [];

    setLoadingModels(true);

    try {
      const url = `https://huggingface.co/datasets/c1587s/flex-damage-impacts/resolve/main/${folderName}/${ssp}.csv`;
      const response = await fetch(url);
      
      if (response.ok) {
        const text = await response.text();
        const lines = text.split('\n');
        
        if (lines.length > 1) {
          // Get headers to find model column
          const headers = lines[0].split(',').map(h => h.trim().toLowerCase().replace(/"/g, ''));
          const modelColumnIndex = headers.findIndex(h => h === 'model');
          const rcpColumnIndex = headers.findIndex(h => h === 'rcp');
          
          if (modelColumnIndex !== -1 && rcpColumnIndex !== -1) {
            // Extract unique Model values for the selected RCP
            const modelValues = new Set<string>();
            
            for (let i = 1; i < lines.length; i++) {
              const values = lines[i].split(',');
              if (values[rcpColumnIndex] && values[modelColumnIndex]) {
                const rowRcp = values[rcpColumnIndex].trim().replace(/"/g, '').toLowerCase();
                const modelValue = values[modelColumnIndex].trim().replace(/"/g, '');
                
                if (rowRcp === rcp.toLowerCase() && modelValue) {
                  // Map the model name for display
                  const displayModel = mapModelForDisplay(modelValue, sector);
                  if (displayModel) {
                    modelValues.add(displayModel);
                  }
                }
              }
            }
            
            availableModels.push(...Array.from(modelValues).sort());
          }
        }
      }
    } catch (error) {
      console.log(`Error checking Models for ${sector}/${ssp}/${rcp}:`, error);
    }

    setLoadingModels(false);
    
    if (availableModels.length > 0) {
      setAvailableModels(availableModels);
    } else {
      // Fallback to default models if none found
      setAvailableModels(['high', 'low']);
    }
  };

  // Load available SSPs when sector changes
  useEffect(() => {
    if (localFilters.sector) {
      checkAvailableSSPs(localFilters.sector);
    } else {
      setAvailableSSPs([]);
      setAvailableRCPs([]);
      setAvailableModels([]);
    }
  }, [localFilters.sector]);

  // Load available RCPs when SSP changes (only if we have sector and SSP)
  useEffect(() => {
    if (localFilters.sector && localFilters.ssp) {
      checkAvailableRCPs(localFilters.sector, localFilters.ssp);
    } else {
      setAvailableRCPs([]);
      setAvailableModels([]);
    }
  }, [localFilters.sector, localFilters.ssp]);

  // Load available Models when RCP changes (only if we have sector, SSP, and RCP)
  useEffect(() => {
    if (localFilters.sector && localFilters.ssp && localFilters.rcp) {
      checkAvailableModels(localFilters.sector, localFilters.ssp, localFilters.rcp);
    } else {
      setAvailableModels([]);
    }
  }, [localFilters.sector, localFilters.ssp, localFilters.rcp]);

  const handleChange = (e: ChangeEvent<HTMLSelectElement>) => {
    const { name, value } = e.target;
    
    if (name === 'sector') {
      // Reset all dependent fields when sector changes
      setLocalFilters(prev => ({ 
        ...prev, 
        sector: value, 
        ssp: '', 
        rcp: '', 
        model: '',
        // Keep period as it's independent
        period: prev.period
      }));
    } else if (name === 'ssp') {
      // Reset dependent fields when SSP changes
      setLocalFilters(prev => ({ 
        ...prev, 
        ssp: value, 
        rcp: '',
        model: ''
      }));
    } else if (name === 'rcp') {
      // Reset model when RCP changes
      setLocalFilters(prev => ({ 
        ...prev, 
        rcp: value, 
        model: ''
      }));
    } else {
      setLocalFilters(prev => ({ ...prev, [name]: value }));
    }
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

  // Helper function to get placeholder text
  const getSSPPlaceholder = () => {
    if (loadingSSPs) return "Loading...";
    if (!localFilters.sector) return "Select Sector";
    if (availableSSPs.length === 0) return "No SSPs available";
    return "Select SSP";
  };

  const getRCPPlaceholder = () => {
    if (loadingRCPs) return "Loading...";
    if (!localFilters.sector) return "Select Sector";
    if (!localFilters.ssp) return "Select SSP";
    if (availableRCPs.length === 0) return "No RCPs available";
    return "Select RCP";
  };

  const getModelPlaceholder = () => {
    if (loadingModels) return "Loading...";
    if (!localFilters.sector) return "Select Sector";
    if (!localFilters.ssp) return "Select SSP";
    if (!localFilters.rcp) return "Select RCP";
    if (availableModels.length === 0) return "No Models available";
    return "Select Model";
  };

  const isSubmitDisabled = () => {
    return loading || 
           loadingSSPs || 
           loadingRCPs || 
           loadingModels ||
           !localFilters.sector || 
           !localFilters.ssp || 
           !localFilters.rcp || 
           !localFilters.model || 
           !localFilters.period;
  };

  return (
    <div className="selector-panel">
      <div className="selector-group">
        <label>Sector:</label>
        <select name="sector" value={localFilters.sector} onChange={handleChange}>
          <option value="">Select Sector</option>
          {["Mortality", "Labor (Combined)", "Labor (High Risk)", "Labor (Low Risk)", "Agriculture", "Energy"].map(opt => (
            <option key={opt} value={opt}>{opt}</option>
          ))}
        </select>
      </div>
      
      <div className="selector-group">
        <label>SSP:</label>
        <select 
          name="ssp" 
          value={localFilters.ssp} 
          onChange={handleChange}
          disabled={loadingSSPs || !localFilters.sector}
        >
          <option value="">{getSSPPlaceholder()}</option>
          {availableSSPs.map(opt => (
            <option key={opt} value={opt}>{opt}</option>
          ))}
        </select>
        {loadingSSPs && <div className="selector-loading-text">Loading SSPs...</div>}
      </div>
      
      <div className="selector-group">
        <label>RCP:</label>
        <select 
          name="rcp" 
          value={localFilters.rcp} 
          onChange={handleChange}
          disabled={loadingRCPs || !localFilters.sector || !localFilters.ssp}
        >
          <option value="">{getRCPPlaceholder()}</option>
          {availableRCPs.map(opt => (
            <option key={opt} value={opt}>{opt}</option>
          ))}
        </select>
        {loadingRCPs && <div className="selector-loading-text">Loading RCPs...</div>}
      </div>
      
      <div className="selector-group">
        <label>Model:</label>
        <select 
          name="model" 
          value={localFilters.model} 
          onChange={handleChange}
          disabled={loadingModels || !localFilters.sector || !localFilters.ssp || !localFilters.rcp}
        >
          <option value="">{getModelPlaceholder()}</option>
          {availableModels.map(opt => (
            <option key={opt} value={opt}>{opt}</option>
          ))}
        </select>
        {loadingModels && <div className="selector-loading-text">Loading Models...</div>}
      </div>
      
      <div className="selector-group">
        <label>Period:</label>
        <select name="period" value={localFilters.period} onChange={handleChange}>
          <option value="">Select Period</option>
          {[
            { value: "2020_2039", label: "2039" },
            { value: "2040_2059", label: "2059" },
            { value: "2060_2079", label: "2079" },
            { value: "2080_2094", label: "2094" },
            { value: "2095_2100", label: "2099" }
          ].map(opt => (
            <option key={opt.value} value={opt.value}>{opt.label}</option>
          ))}
        </select>
      </div>
      
      <div className="selector-submit-container">
        <button 
          className="selector-submit-btn" 
          onClick={handleSubmit} 
          disabled={isSubmitDisabled()}
        >
          Submit
        </button>
        {loading && (
          <div className="selector-loading">
            <CircleLoader size={16} color="#20e998" />
          </div>
        )}
      </div>
    </div>
  );
};

export default SelectorPanel;
