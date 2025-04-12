// Loading.tsx
import React from 'react';
import './Loading.css';

const Loading: React.FC = () => {
  return (
    <div className="loading-overlay">
      <div className="loading-text">Loading...</div>
    </div>
  );
};

export default Loading;
