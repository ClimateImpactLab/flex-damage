// LayerToggle.tsx
import React from 'react';
import './LayerToggle.css';

interface LayerToggleProps {
  layerMode: 'flex' | 'raw' | 'difference';
  onChange: (mode: 'flex' | 'raw' | 'difference') => void;
}

const LayerToggle: React.FC<LayerToggleProps> = ({ layerMode, onChange }) => {
  return (
    <div className="layer-toggle-container">
      <label className="layer-toggle-button">
        <input
          type="radio"
          name="layerMode"
          value="flex"
          checked={layerMode === 'flex'}
          onChange={() => onChange('flex')}
        />
        Flex Damage
      </label>
      <label className="layer-toggle-button">
        <input
          type="radio"
          name="layerMode"
          value="raw"
          checked={layerMode === 'raw'}
          onChange={() => onChange('raw')}
        />
        Raw Total
      </label>
      <label className="layer-toggle-button">
        <input
          type="radio"
          name="layerMode"
          value="difference"
          checked={layerMode === 'difference'}
          onChange={() => onChange('difference')}
        />
        Difference
      </label>
    </div>
  );
};

export default LayerToggle;
