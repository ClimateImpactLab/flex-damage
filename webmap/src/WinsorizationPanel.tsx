// WinsorizationPanel.tsx
import React from 'react';
import './WinsorizationPanel.css';

export interface WinsorizationSettings {
  enabled: boolean;
  lowerPercentile: number;
  upperPercentile: number;
  topCoding: boolean;
}

interface WinsorizationPanelProps {
  settings: WinsorizationSettings;
  onChange: (settings: WinsorizationSettings) => void;
}

const WinsorizationPanel: React.FC<WinsorizationPanelProps> = ({ settings, onChange }) => {
  const handleEnabledChange = (e: React.ChangeEvent<HTMLInputElement>) => {
    onChange({
      ...settings,
      enabled: e.target.checked,
      topCoding: e.target.checked ? false : settings.topCoding  // Disable top coding if winsorization is enabled
    });
  };

  const handleTopCodingChange = (e: React.ChangeEvent<HTMLInputElement>) => {
    onChange({
      ...settings,
      topCoding: e.target.checked,
      enabled: e.target.checked ? false : settings.enabled  // Disable winsorization if top coding is enabled
    });
  };

  const handlePercentileChange = (field: 'lowerPercentile' | 'upperPercentile') => 
    (e: React.ChangeEvent<HTMLInputElement>) => {
      const value = parseFloat(e.target.value);
      if (!isNaN(value) && value >= 0 && value <= 100) {
        onChange({
          ...settings,
          [field]: value
        });
      }
    };

  const presetOptions = [
    { label: 'Q1-Q99', lower: 1, upper: 99 },
    { label: 'Q2-Q98', lower: 2, upper: 98 },
    { label: 'Q5-Q95', lower: 5, upper: 95 },
    { label: 'Q10-Q90', lower: 10, upper: 90 }
  ];

  const handlePresetClick = (lower: number, upper: number) => {
    onChange({
      ...settings,
      lowerPercentile: lower,
      upperPercentile: upper
    });
  };

  return (
    <div className="winsorization-panel-container">
      <div className="winsorization-panel-title">
        <label className="winsorization-checkbox">
          <input
            type="checkbox"
            checked={settings.topCoding}
            onChange={handleTopCodingChange}
          />
          <span>Top Coding (Min/Max Scale)</span>
        </label>
      </div>
      
      <div className="winsorization-panel-title">
        <label className="winsorization-checkbox">
          <input
            type="checkbox"
            checked={settings.enabled}
            onChange={handleEnabledChange}
          />
          <span>Winsorization</span>
        </label>
      </div>
      
      {settings.enabled && (
        <div className="winsorization-panel-controls">
          <div className="winsorization-presets">
            {presetOptions.map(preset => (
              <button
                key={preset.label}
                className={`winsorization-preset-btn ${
                  settings.lowerPercentile === preset.lower && 
                  settings.upperPercentile === preset.upper ? 'active' : ''
                }`}
                onClick={() => handlePresetClick(preset.lower, preset.upper)}
              >
                {preset.label}
              </button>
            ))}
          </div>
          
          <div className="winsorization-inputs">
            <div className="winsorization-input-group">
              <label>Lower %:</label>
              <input
                type="number"
                min="0"
                max="50"
                step="0.1"
                value={settings.lowerPercentile}
                onChange={handlePercentileChange('lowerPercentile')}
              />
            </div>
            <div className="winsorization-input-group">
              <label>Upper %:</label>
              <input
                type="number"
                min="50"
                max="100"
                step="0.1"
                value={settings.upperPercentile}
                onChange={handlePercentileChange('upperPercentile')}
              />
            </div>
          </div>
        </div>
      )}
      
      <div className="winsorization-note">
        Note: These techniques are only applied to make the map more comparable when using color scales.<br/>
        Original values are presented in the legend when hovering over countries.
      </div>
    </div>
  );
};

export default WinsorizationPanel; 