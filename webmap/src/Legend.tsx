// Legend.tsx
// Si usas el nuevo JSX transform, puedes eliminar la siguiente línea o comentarla:
// import React from 'react';
import './Legend.css';

interface HoverInfo {
  iso: string;
  value: number | null;
}

interface LegendProps {
  maxAbs: number;
  hoverInfo: HoverInfo | null;
  sector: string;
  ttAnomaly: number | null;
}

const Legend: React.FC<LegendProps> = ({ maxAbs, hoverInfo, sector, ttAnomaly }) => {
  const getColor = (value: number, maxAbs: number): string => {
    const colorA = { r: 255, g: 7, b: 58 };
    const colorB = { r: 255, g: 140, b: 0 };
    const colorC = { r: 255, g: 255, b: 255 };
    const colorD = { r: 0, g: 255, b: 234 };
    const colorE = { r: 0, g: 174, b: 255 };

    let t: number, r: number, g: number, b: number;
    if (value <= -maxAbs / 2) {
      t = (value + maxAbs) / (maxAbs / 2);
      r = Math.round(colorA.r + t * (colorB.r - colorA.r));
      g = Math.round(colorA.g + t * (colorB.g - colorA.g));
      b = Math.round(colorA.b + t * (colorB.b - colorA.b));
    } else if (value < 0) {
      t = (value + maxAbs / 2) / (maxAbs / 2);
      r = Math.round(colorB.r + t * (colorC.r - colorB.r));
      g = Math.round(colorB.g + t * (colorC.g - colorB.g));
      b = Math.round(colorB.b + t * (colorC.b - colorB.b));
    } else if (value < maxAbs / 2) {
      t = value / (maxAbs / 2);
      r = Math.round(colorC.r + t * (colorD.r - colorC.r));
      g = Math.round(colorC.g + t * (colorD.g - colorC.g));
      b = Math.round(colorC.b + t * (colorD.b - colorC.b));
    } else {
      t = (value - maxAbs / 2) / (maxAbs / 2);
      r = Math.round(colorD.r + t * (colorE.r - colorD.r));
      g = Math.round(colorD.g + t * (colorE.g - colorD.g));
      b = Math.round(colorD.b + t * (colorE.b - colorD.b));
    }
    return `rgb(${r},${g},${b})`;
  };

  let unitText = "";
  const lowerSector = sector.toLowerCase();
  if (lowerSector === 'mortality') {
    unitText = "deaths per 100k population";
  } else if (["combined", "high risk", "low risk"].includes(lowerSector)) {
    unitText = "hours/person/year";
  }

  let markerLeft = 0;
  let markerColor = "#000";
  let hoverValue: string | null = null;
  if (hoverInfo && hoverInfo.value !== null) {
    const v = hoverInfo.value;
    markerLeft = ((v + maxAbs) / (2 * maxAbs)) * 200;
    markerColor = getColor(v, maxAbs);
    hoverValue = v.toFixed(2);
  }

  const gradient =
    lowerSector === 'mortality'
      ? 'linear-gradient(to right, #00AEFF, #00FFEA, #FFFFFF, #FF8C00, #FF073A)'
      : 'linear-gradient(to right, #FF073A, #FF8C00, #FFFFFF, #00FFEA, #00AEFF)';

  return (
    <div className="legend">
      <div className="legend-title">
        {hoverInfo && hoverInfo.value !== null ? ` - ${hoverInfo.iso}: ${hoverValue}` : ''}
      </div>
      <div className="legend-gradient-container">
        <div className="legend-gradient" style={{ background: gradient }} />
        {hoverInfo && hoverInfo.value !== null && (
          <div
            className="legend-marker"
            style={{ left: markerLeft - 10 }}
          >
            <span style={{ color: markerColor }}></span>
          </div>
        )}
      </div>
      <div className="legend-labels">
        <span>{(-maxAbs).toFixed(2)}</span>
        <span>{(-maxAbs / 2).toFixed(2)}</span>
        <span>0</span>
        <span>{(maxAbs / 2).toFixed(2)}</span>
        <span>{maxAbs.toFixed(2)}</span>
      </div>
      {unitText && <div className="legend-unit">{unitText}</div>}
      {ttAnomaly !== null && (
        <div className="legend-delta-c">ΔC: {ttAnomaly.toFixed(2)} °C</div>
      )}
    </div>
  );
};

export default Legend;
