import { StrictMode } from 'react';
import { createRoot } from 'react-dom/client';
import './index.css';
import App from './App.tsx';

// Rotate the favicon in an infinite loop
function rotateFaviconInfinite(speed = 0.1) {
  const img = new Image();
  img.src = '/cil_logo.png'; // Make sure this image exists in the public/ folder

  img.onload = () => {
    const canvas = document.createElement('canvas');
    const ctx = canvas.getContext('2d')!;
    const size = 64;
    canvas.width = size;
    canvas.height = size;

    let angle = 0;

    function draw() {
      ctx.clearRect(0, 0, size, size);
      ctx.save();
      ctx.translate(size / 2, size / 2);
      ctx.rotate(angle);
      ctx.drawImage(img, -size / 2, -size / 2, size, size);
      ctx.restore();

      const link: HTMLLinkElement =
        document.querySelector("link[rel='icon']") || document.createElement('link');
      link.rel = 'icon';
      link.href = canvas.toDataURL('image/png');
      if (!document.head.contains(link)) {
        document.head.appendChild(link);
      }

      angle += speed; // radians per frame
      requestAnimationFrame(draw);
    }

    draw();
  };
}

// Start infinite favicon rotation on load
rotateFaviconInfinite(0.009);

createRoot(document.getElementById('root')!).render(
  <StrictMode>
    <App />
  </StrictMode>
);
