// DataTable.tsx
import React, { useState, useEffect } from 'react';
import { preloadCountryNames, getCachedCountryName } from './utils/countryNames';
import './DataTable.css';

interface DataTableProps {
  lowest: [string, number][];
  highest: [string, number][];
  maxAbs: number; // En modo difference, este es diffScale
  sector: string;
  layerMode: 'flex' | 'raw' | 'difference';
  winsorizationSettings: { enabled: boolean; lowerPercentile: number; upperPercentile: number };
  finalFlexMap: { [iso: string]: number };
  finalRawMap: { [iso: string]: number };
  finalDiffMap: { [iso: string]: number };
  onCountryHover?: (iso: string | null) => void;
}

function hexToRgb(hex: string): { r: number; g: number; b: number } {
  const result = /^#?([a-f\d]{2})([a-f\d]{2})([a-f\d]{2})$/i.exec(hex);
  return result ? {
    r: parseInt(result[1], 16),
    g: parseInt(result[2], 16),
    b: parseInt(result[3], 16)
  } : { r: 0, g: 0, b: 0 };
}

function interpolateColor(color1: { r: number; g: number; b: number }, color2: { r: number; g: number; b: number }, factor: number): string {
  const r = Math.round(color1.r + factor * (color2.r - color1.r));
  const g = Math.round(color1.g + factor * (color2.g - color1.g));
  const b = Math.round(color1.b + factor * (color2.b - color1.b));
  return `rgb(${r},${g},${b})`;
}

function getColor(value: number, maxAbs: number, sector: string, layerMode: 'flex' | 'raw' | 'difference', winsorizationEnabled: boolean = false, actualMin?: number, actualMax?: number): string {
  if (layerMode === 'difference') {
    let ratio: number;
    if (value < 0) {
      ratio = Math.min(Math.abs(value) / maxAbs, 1);
      const dark = { r: 0, g: 100, b: 0 };       // #006400
      const light = { r: 208, g: 240, b: 192 };    // #d0f0c0
      const r = Math.round(dark.r + ratio * (light.r - dark.r));
      const g = Math.round(dark.g + ratio * (light.g - dark.g));
      const b = Math.round(dark.b + ratio * (light.b - dark.b));
      return `rgb(${r},${g},${b})`;
    } else {
      ratio = Math.min(value / maxAbs, 1);
      const light = { r: 240, g: 128, b: 128 };    // #f08080
      const dark = { r: 139, g: 0, b: 0 };           // #8b0000
      const r = Math.round(light.r + ratio * (dark.r - light.r));
      const g = Math.round(light.g + ratio * (dark.g - light.g));
      const b = Math.round(light.b + ratio * (dark.b - light.b));
      return `rgb(${r},${g},${b})`;
    }
  } else {
    // Use the exact same color logic as the map
    const baseColors = ['#053061', '#2166ac', '#92c5de', '#f7f7f7', '#fddbc7', '#ef8a62', '#67001f'];
    const isLaborOrEnergy = sector.toLowerCase().includes('labor') || sector.toLowerCase() === 'energy';
    const colorArray = isLaborOrEnergy ? [...baseColors].reverse() : baseColors;
    
    if (winsorizationEnabled && actualMin !== undefined && actualMax !== undefined) {
      // For winsorized data, use asymmetric scaling like the map
      const stops: [number, string][] = colorArray.map((c, i) => {
        const factor = i / (colorArray.length - 1);
        const v = actualMin + factor * (actualMax - actualMin);
        return [v, c];
      });
      
      const clampedValue = Math.max(actualMin, Math.min(actualMax, value));
      

      
      // Handle exact extreme values
      if (clampedValue <= actualMin) return colorArray[0]; // Most extreme negative
      if (clampedValue >= actualMax) return colorArray[colorArray.length - 1]; // Most extreme positive
      
      // Find the two stops to interpolate between
      for (let i = 0; i < stops.length - 1; i++) {
        const [val1, color1] = stops[i];
        const [val2, color2] = stops[i + 1];
        
        if (clampedValue >= val1 && clampedValue <= val2) {
          if (val1 === val2) return color1;
          
          const factor = (clampedValue - val1) / (val2 - val1);
          const rgb1 = hexToRgb(color1);
          const rgb2 = hexToRgb(color2);
          
          return interpolateColor(rgb1, rgb2, factor);
        }
      }
      
      return stops[stops.length - 1][1];
    } else if (winsorizationEnabled) {
      // Fallback to symmetric scaling if actualMin/actualMax not provided
      const stops: [number, string][] = colorArray.map((c, i) => {
        const v = -maxAbs + (2 * maxAbs * i) / (colorArray.length - 1);
        return [v, c];
      });
      
      const clampedValue = Math.max(-maxAbs, Math.min(maxAbs, value));
      
      // Handle exact extreme values
      if (clampedValue <= -maxAbs) return colorArray[0];
      if (clampedValue >= maxAbs) return colorArray[colorArray.length - 1];
      
      // Find the two stops to interpolate between
      for (let i = 0; i < stops.length - 1; i++) {
        const [val1, color1] = stops[i];
        const [val2, color2] = stops[i + 1];
        
        if (clampedValue >= val1 && clampedValue <= val2) {
          if (val1 === val2) return color1;
          
          const factor = (clampedValue - val1) / (val2 - val1);
          const rgb1 = hexToRgb(color1);
          const rgb2 = hexToRgb(color2);
          
          return interpolateColor(rgb1, rgb2, factor);
        }
      }
      
      return stops[stops.length - 1][1];
    } else {
      // Apply the same square root transformation as the map when not winsorized
      const transformedValue = value < 0 ? -Math.sqrt(Math.abs(value)) : Math.sqrt(value);
      const effectiveMax = Math.sqrt(maxAbs);
      
      // Create stops using the square root transformation like the map
      const stops: [number, string][] = [
        [-effectiveMax, colorArray[0]],
        [-effectiveMax * 0.5, colorArray[1]],
        [-effectiveMax * 0.2, colorArray[2]],
        [0, colorArray[3]],
        [effectiveMax * 0.2, colorArray[4]],
        [effectiveMax * 0.5, colorArray[5]],
        [effectiveMax, colorArray[6]]
      ];
      
      // Clamp the transformed value
      const clampedValue = Math.max(-effectiveMax, Math.min(effectiveMax, transformedValue));
      
      // Find the two stops to interpolate between
      for (let i = 0; i < stops.length - 1; i++) {
        const [val1, color1] = stops[i];
        const [val2, color2] = stops[i + 1];
        
        if (clampedValue >= val1 && clampedValue <= val2) {
          if (val1 === val2) return color1;
          
          const factor = (clampedValue - val1) / (val2 - val1);
          const rgb1 = hexToRgb(color1);
          const rgb2 = hexToRgb(color2);
          
          return interpolateColor(rgb1, rgb2, factor);
        }
      }
      
      return stops[stops.length - 1][1];
    }
  }
}

const DataTable: React.FC<DataTableProps> = ({ 
  lowest, 
  highest, 
  maxAbs, 
  sector, 
  layerMode,
  winsorizationSettings,
  finalFlexMap,
  finalRawMap,
  finalDiffMap,
  onCountryHover
}) => {
  const [isExpanded, setIsExpanded] = useState(true);
  const [countryNamesLoaded, setCountryNamesLoaded] = useState(false);

  // Helper function to determine decimal places for display
  const getDecimalPlaces = (sector: string): number => {
    const sectorLower = sector.toLowerCase();
    if (sectorLower.includes('labor')) {
      return 6; // Up to 6 decimals for labor sector
    }
    return 2; // Default 2 decimals for other sectors
  };

  // Preload country names when the data changes
  useEffect(() => {
    const allIsoCodes = [...lowest, ...highest].map(([iso]) => iso);
    if (allIsoCodes.length > 0) {
      setCountryNamesLoaded(false);
      console.log('Preloading country names for sector:', sector, 'ISOs:', allIsoCodes);
      preloadCountryNames(allIsoCodes).then(() => {
        console.log('Country names loaded for sector:', sector);
        setCountryNamesLoaded(true);
      });
    }
  }, [lowest, highest, sector]);

  const getColorForCountry = (iso: string, originalValue: number): string => {
    // To match map colors, we need to use the same processed value that the map uses
    let valueForColor: number;
    if (layerMode === 'flex') {
      valueForColor = finalFlexMap[iso] ?? originalValue;
    } else if (layerMode === 'raw') {
      valueForColor = finalRawMap[iso] ?? originalValue;
    } else {
      valueForColor = finalDiffMap[iso] ?? originalValue;
    }
    

    
    // Get the actual range for asymmetric scaling when winsorization is enabled
    let actualMin: number | undefined;
    let actualMax: number | undefined;
    
    if (winsorizationSettings.enabled) {
      // Use only the current layer mode values, just like the map does
      let currentLayerValues: number[] = [];
      if (layerMode === 'flex') {
        currentLayerValues = Object.values(finalFlexMap).filter(v => v !== undefined);
      } else if (layerMode === 'raw') {
        currentLayerValues = Object.values(finalRawMap).filter(v => v !== undefined);
      } else if (layerMode === 'difference') {
        currentLayerValues = Object.values(finalDiffMap).filter(v => v !== undefined);
      }
      
      if (currentLayerValues.length > 0) {
        actualMin = Math.min(...currentLayerValues);
        actualMax = Math.max(...currentLayerValues);
      }
    }
    
    // Use the processed value for color calculation to match map colors
    const color = getColor(valueForColor, maxAbs, sector, layerMode, winsorizationSettings.enabled, actualMin, actualMax);
    

    
    return color;
  };

  return (
    <div className="data-table">
      <div className="table-header">
        <h4 className="table-title">EXTREMES</h4>
        <button 
          className="table-toggle"
          onClick={() => setIsExpanded(!isExpanded)}
        >
          <span className={`arrow ${isExpanded ? 'expanded' : 'collapsed'}`}>▼</span>
        </button>
      </div>
      {isExpanded && (
        <>
          <div className="table-note">Original values (not winsorized)</div>
          <div className="table-section">
        <div className="section-title">Lowest</div>
                  <div className="table-list">
            {lowest.map(([iso, value]) => (
              <div 
                key={iso} 
                className="table-row" 
                style={{ backgroundColor: getColorForCountry(iso, value) }}
                onMouseEnter={() => {
                  console.log('Table hover ENTER (lowest):', iso);
                  onCountryHover?.(iso);
                }}
                onMouseLeave={() => {
                  console.log('Table hover LEAVE (lowest)');
                  onCountryHover?.(null);
                }}
              >
                <span className="iso">{countryNamesLoaded ? getCachedCountryName(iso) : iso}</span>
                <span className="val">{value.toFixed(getDecimalPlaces(sector))}</span>
              </div>
            ))}
          </div>
        </div>
        <div className="table-section">
          <div className="section-title">Highest</div>
          <div className="table-list">
            {highest.map(([iso, value]) => (
              <div 
                key={iso} 
                className="table-row" 
                style={{ backgroundColor: getColorForCountry(iso, value) }}
                onMouseEnter={() => {
                  console.log('Table hover ENTER (highest):', iso);
                  onCountryHover?.(iso);
                }}
                onMouseLeave={() => {
                  console.log('Table hover LEAVE (highest)');
                  onCountryHover?.(null);
                }}
              >
                <span className="iso">{countryNamesLoaded ? getCachedCountryName(iso) : iso}</span>
                <span className="val">{value.toFixed(getDecimalPlaces(sector))}</span>
              </div>
            ))}
          </div>
        </div>
        </>
      )}
    </div>
  );
};

export default DataTable;
