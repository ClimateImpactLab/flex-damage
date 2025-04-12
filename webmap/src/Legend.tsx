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

  const isFlex = layerMode === 'flex';
  const gradientStyle = isFlex
    ? 'linear-gradient(to right, #00AEFF, #00FFEA, #FFFFFF, #FF8C00, #FF073A)'
    : 'linear-gradient(to right, #FF073A, #FF8C00, #FFFFFF, #00FFEA, #00AEFF)';
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
