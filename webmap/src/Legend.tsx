// Legend.tsx
import React, { useEffect, useState } from 'react';
import { getCountryName, getCachedCountryName } from './utils/countryNames';
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
  const [countryName, setCountryName] = useState<string>('');

  // Helper function to get units for each sector
  const getSectorUnits = (sector: string): string => {
    const sectorLower = sector.toLowerCase();
    if (sectorLower === 'mortality') {
      return 'deaths per 100,000';
    } else if (sectorLower.includes('labor')) {
      return 'change in minutes worked';
    } else if (sectorLower === 'energy') {
      return 'kWh/pc';
    }
    return '';
  };

  // Helper function to determine decimal places for display
  const getDecimalPlaces = (_value: number, sector: string): number => {
    const sectorLower = sector.toLowerCase();
    if (sectorLower.includes('labor')) {
      return 6; // Up to 6 decimals for labor sector
    }
    return 2; // Default 2 decimals for other sectors
  };

  // Fetch country name when hoverInfo changes
  useEffect(() => {
    if (hoverInfo?.iso) {
      // First try to get cached name for immediate display
      const cached = getCachedCountryName(hoverInfo.iso);
      setCountryName(cached);
      
      // If it's just the ISO code, try to fetch the real name
      if (cached === hoverInfo.iso) {
        getCountryName(hoverInfo.iso).then(name => {
          setCountryName(name);
        });
      }
    } else {
      setCountryName('');
    }
  }, [hoverInfo?.iso]);
  if (layerMode === 'difference') {
    const gradientStyle =
      'linear-gradient(to right, #006400 0%, #d0f0c0 50%, #f08080 50%, #8b0000 100%)';

    return (
      <div className="legend">
        <div className="legend-title">
          {hoverInfo && hoverInfo.value !== null
            ? `${countryName || hoverInfo.iso}: ${hoverInfo.value.toFixed(getDecimalPlaces(hoverInfo.value, sector))}`
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
          <span>{`-${diffScale.toFixed(getDecimalPlaces(diffScale, sector))}`}</span>
          <span>0</span>
          <span>{diffScale.toFixed(getDecimalPlaces(diffScale, sector))}</span>
        </div>
        <div className="legend-unit">Difference (Raw Total – Flex Damage) • {getSectorUnits(sector)}</div>
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
          ? `${countryName || hoverInfo.iso}: ${hoverInfo.value.toFixed(getDecimalPlaces(hoverInfo.value, sector))}`
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
        <span>{`-${scale.toFixed(getDecimalPlaces(scale, sector))}`}</span>
        <span>0</span>
        <span>{scale.toFixed(getDecimalPlaces(scale, sector))}</span>
      </div>
      <div className="legend-unit">{unitLabel} • {getSectorUnits(sector)}</div>
      {ttAnomaly !== null && (
        <div className="legend-delta-c">ΔC: {ttAnomaly.toFixed(2)} °C</div>
      )}
    </div>
  );
};

export default Legend;
