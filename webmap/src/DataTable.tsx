// DataTable.tsx
import React from 'react';
import './DataTable.css';

interface DataTableProps {
  lowest: [string, number][];
  highest: [string, number][];
  maxAbs: number; // En modo difference, este es diffScale
  sector: string;
  layerMode: 'flex' | 'raw' | 'difference';
}

function getColor(value: number, maxAbs: number, sector: string, layerMode: 'flex' | 'raw' | 'difference'): string {
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
    // Para modos flex y raw usamos la lógica anterior.
    let val = value;
    if (sector.toLowerCase() === 'mortality') {
      val = -value;
    }
    const colorA = { r: 255, g: 7, b: 58 };
    const colorB = { r: 255, g: 140, b: 0 };
    const colorC = { r: 255, g: 255, b: 255 };
    const colorD = { r: 0, g: 255, b: 234 };
    const colorE = { r: 0, g: 174, b: 255 };
    let t, r, g, b;
    if (val <= -maxAbs / 2) {
      t = (val + maxAbs) / (maxAbs / 2);
      r = Math.round(colorA.r + t * (colorB.r - colorA.r));
      g = Math.round(colorA.g + t * (colorB.g - colorA.g));
      b = Math.round(colorA.b + t * (colorB.b - colorA.b));
    } else if (val < 0) {
      t = (val + maxAbs / 2) / (maxAbs / 2);
      r = Math.round(colorB.r + t * (colorC.r - colorB.r));
      g = Math.round(colorB.g + t * (colorC.g - colorB.g));
      b = Math.round(colorB.b + t * (colorC.b - colorB.b));
    } else if (val < maxAbs / 2) {
      t = val / (maxAbs / 2);
      r = Math.round(colorC.r + t * (colorD.r - colorC.r));
      g = Math.round(colorC.g + t * (colorD.g - colorC.g));
      b = Math.round(colorC.b + t * (colorD.b - colorC.b));
    } else {
      t = (val - maxAbs / 2) / (maxAbs / 2);
      r = Math.round(colorD.r + t * (colorE.r - colorD.r));
      g = Math.round(colorD.g + t * (colorE.g - colorD.g));
      b = Math.round(colorD.b + t * (colorE.b - colorD.b));
    }
    return `rgb(${r},${g},${b})`;
  }
}

const DataTable: React.FC<DataTableProps> = ({ lowest, highest, maxAbs, sector, layerMode }) => {
  return (
    <div className="data-table">
      <h4 className="table-title">EXTREMES</h4>
      <div className="table-section">
        <div className="section-title">Lowest</div>
        <div className="table-list">
          {lowest.map(([iso, value]) => (
            <div key={iso} className="table-row" style={{ backgroundColor: getColor(value, maxAbs, sector, layerMode) }}>
              <span className="iso">{iso}</span>
              <span className="val">{value.toFixed(2)}</span>
            </div>
          ))}
        </div>
      </div>
      <div className="table-section">
        <div className="section-title">Highest</div>
        <div className="table-list">
          {highest.map(([iso, value]) => (
            <div key={iso} className="table-row" style={{ backgroundColor: getColor(value, maxAbs, sector, layerMode) }}>
              <span className="iso">{iso}</span>
              <span className="val">{value.toFixed(2)}</span>
            </div>
          ))}
        </div>
      </div>
    </div>
  );
};

export default DataTable;
