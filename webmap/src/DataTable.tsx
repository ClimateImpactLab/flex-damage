// DataTable.tsx
import React from 'react';
import './DataTable.css';

interface DataTableProps {
  lowest: [string, number][];
  highest: [string, number][];
  maxAbs: number;
  sector: string;
}

function getColor(value: number, maxAbs: number, sector: string): string {
  if (sector.toLowerCase() === 'mortality') {
    value = -value;  // Invertir para que la escala coincida con Legend
  }
  const colorA = { r: 255, g: 7, b: 58 };
  const colorB = { r: 255, g: 140, b: 0 };
  const colorC = { r: 255, g: 255, b: 255 };
  const colorD = { r: 0, g: 255, b: 234 };
  const colorE = { r: 0, g: 174, b: 255 };

  let t, r, g, b;
  if (value <= -maxAbs/2) {
    t = (value + maxAbs) / (maxAbs/2);
    r = Math.round(colorA.r + t * (colorB.r - colorA.r));
    g = Math.round(colorA.g + t * (colorB.g - colorA.g));
    b = Math.round(colorA.b + t * (colorB.b - colorA.b));
  } else if (value < 0) {
    t = (value + maxAbs/2) / (maxAbs/2);
    r = Math.round(colorB.r + t * (colorC.r - colorB.r));
    g = Math.round(colorB.g + t * (colorC.g - colorB.g));
    b = Math.round(colorB.b + t * (colorC.b - colorB.b));
  } else if (value < maxAbs/2) {
    t = value / (maxAbs/2);
    r = Math.round(colorC.r + t * (colorD.r - colorC.r));
    g = Math.round(colorC.g + t * (colorD.g - colorC.g));
    b = Math.round(colorC.b + t * (colorD.b - colorC.b));
  } else {
    t = (value - maxAbs/2) / (maxAbs/2);
    r = Math.round(colorD.r + t * (colorE.r - colorD.r));
    g = Math.round(colorD.g + t * (colorE.g - colorD.g));
    b = Math.round(colorD.b + t * (colorE.b - colorD.b));
  }
  return `rgb(${r},${g},${b})`;
}

const DataTable: React.FC<DataTableProps> = ({ lowest, highest, maxAbs, sector }) => {
  return (
    <div className="data-table">
      <h4 className="table-title">EXTREMES</h4>
      <div className="table-section">
        <div className="section-title">Lowest</div>
        <div className="table-list">
          {lowest.map(([iso, value]) => (
            <div key={iso} className="table-row" style={{ backgroundColor: getColor(value, maxAbs, sector) }}>
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
            <div key={iso} className="table-row" style={{ backgroundColor: getColor(value, maxAbs, sector) }}>
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
