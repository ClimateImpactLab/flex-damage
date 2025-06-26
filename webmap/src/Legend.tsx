// Legend.tsx
import React from 'react';
import './Legend.css';

interface HoverInfo {
  iso: string;
  value: number | null;
}

interface LegendProps {
  maxAbs: number;
  diffScale: number;
  hoverInfo: HoverInfo | null;
  sector: string;
  ttAnomaly: number | null;
  layerMode: 'flex' | 'raw' | 'difference';
}

const Legend: React.FC<LegendProps> = ({
  maxAbs,
  diffScale,
  hoverInfo,
  sector,
  ttAnomaly,
  layerMode,
}) => {
  if (layerMode === 'difference') {
    const gradientStyle =
      'linear-gradient(to right, #006400 0%, #d0f0c0 50%, #f08080 50%, #8b0000 100%)';

    return (
      <div className="legend">
        <div className="legend-title">
          {hoverInfo && hoverInfo.value !== null
            ? `${hoverInfo.iso}: ${hoverInfo.value.toFixed(2)}`
            : ''}
        </div>
        <div className="legend-gradient-container">
          <div className="legend-gradient" style={{ background: gradientStyle }}></div>
          {hoverInfo && hoverInfo.value !== null && (
            <div
              className="legend-marker"
              style={{
                left: `${((hoverInfo.value + diffScale) / (2 * diffScale)) * 200 - 1.5}px`,
              }}
            ></div>
          )}
        </div>
        <div className="legend-labels">
          <span>{`-${diffScale.toFixed(2)}`}</span>
          <span>0</span>
          <span>{diffScale.toFixed(2)}</span>
        </div>
        <div className="legend-unit">Difference (Raw Total – Flex Damage)</div>
        <div className="legend-info" style={{ fontSize: '10px', color: '#ccc', marginTop: '4px' }}>
          <p>
            <span className="legend-sample" style={{ backgroundColor: '#90EE90' }}></span>
            Both values share the same sign.
          </p>
          <p>
            <span className="legend-sample" style={{ backgroundColor: '#CD5C5C' }}></span>
            Values differ in sign.
          </p>
          <p>Intensity indicates the absolute difference.</p>
        </div>
        {ttAnomaly !== null && (
          <div className="legend-delta-c">ΔC: {ttAnomaly.toFixed(2)} °C</div>
        )}
      </div>
    );
  }

  // Use the same color palette as the map, adjusted for sector
  const baseColors = ['#2c7bb6', '#9dcfe4', '#ace7e7', '#ffedaa', '#ffe277', '#fec980', '#d7191c'];
  // Color mapping based on sector:
  // baseColors = ['#2c7bb6' (blue), ..., '#d7191c' (red)]
  // - Mortality: negative = blue, positive = red => use baseColors
  // - Labor: negative = red, positive = blue => use reversed  
  // - Energy: negative = red, positive = blue => use reversed
  const isLaborOrEnergy = sector?.toLowerCase().includes('labor') || sector?.toLowerCase() === 'energy';
  const colors = isLaborOrEnergy ? [...baseColors].reverse() : baseColors;
  const gradientStyle = `linear-gradient(to right, ${colors.join(', ')})`;
  const isFlex = layerMode === 'flex';
  const unitLabel = isFlex ? 'Flex Damage' : 'Raw Total';
  const scale = maxAbs;

  return (
    <div className="legend">
      <div className="legend-title">
        {hoverInfo && hoverInfo.value !== null
          ? `${hoverInfo.iso}: ${hoverInfo.value.toFixed(2)}`
          : ''}
      </div>
      <div className="legend-gradient-container">
        <div className="legend-gradient" style={{ background: gradientStyle }} />
        {hoverInfo && hoverInfo.value !== null && (
          <div
            className="legend-marker"
            style={{
              left: `${((hoverInfo.value + scale) / (2 * scale)) * 200 - 1.5}px`,
            }}
          ></div>
        )}
      </div>
      <div className="legend-labels">
        <span>{`-${scale.toFixed(2)}`}</span>
        <span>0</span>
        <span>{scale.toFixed(2)}</span>
      </div>
      <div className="legend-unit">{unitLabel}</div>
      {ttAnomaly !== null && (
        <div className="legend-delta-c">ΔC: {ttAnomaly.toFixed(2)} °C</div>
      )}
    </div>
  );
};

export default Legend;
