import React from 'react';
import './ProjectionSelector.css';

export type ProjectionType = 'globe' | 'equalEarth' | 'equirectangular' | 'mercator' | 'naturalEarth';

interface ProjectionSelectorProps {
  selectedProjection: ProjectionType;
  onChange: (projection: ProjectionType) => void;
}

const ProjectionSelector: React.FC<ProjectionSelectorProps> = ({ selectedProjection, onChange }) => {
  const projections: { value: ProjectionType; label: string }[] = [
    { value: 'naturalEarth', label: 'Natural Earth' },
    { value: 'globe', label: 'Globe' },
    { value: 'equalEarth', label: 'Equal Earth' },
    { value: 'equirectangular', label: 'Equirectangular' },
    { value: 'mercator', label: 'Mercator' }
  ];

  return (
    <div className="projection-selector-container">
      <span className="projection-selector-title">Projection:</span>
      <div className="projection-selector-options">
        {projections.map(projection => (
          <label key={projection.value} className="projection-selector-option">
            <input
              type="radio"
              name="projection"
              value={projection.value}
              checked={selectedProjection === projection.value}
              onChange={() => onChange(projection.value)}
            />
            <span className="projection-selector-label">{projection.label}</span>
          </label>
        ))}
      </div>
    </div>
  );
};

export default ProjectionSelector; 