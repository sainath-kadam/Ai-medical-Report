export type PlaceholderLogoKind = 'cross' | 'pulse' | 'shield' | 'bold-cross';

/** Draws a small, generic medical-style mark (a ring+cross, a pulse line, a shield, or a
 *  bold cross -- never based on any real organization's actual logo) onto an offscreen
 *  canvas and returns it as a real PNG file. Used so a freshly-picked starter template has
 *  a logo in its live preview immediately instead of looking bare; swap it for a real logo
 *  any time via the normal upload control. */
export function generatePlaceholderLogo(kind: PlaceholderLogoKind, color: string): Promise<File> {
  const size = 240;
  const canvas = document.createElement('canvas');
  canvas.width = size;
  canvas.height = size;
  const ctx = canvas.getContext('2d');
  if (!ctx) return Promise.reject(new Error('Canvas is not supported in this browser'));

  const center = size / 2;
  ctx.clearRect(0, 0, size, size);
  ctx.strokeStyle = color;
  ctx.fillStyle = color;
  ctx.lineCap = 'round';
  ctx.lineJoin = 'round';

  function ring(radius: number, width: number) {
    ctx!.lineWidth = width;
    ctx!.beginPath();
    ctx!.arc(center, center, radius, 0, Math.PI * 2);
    ctx!.stroke();
  }

  function cross(arm: number, width: number) {
    ctx!.lineWidth = width;
    ctx!.beginPath();
    ctx!.moveTo(center - arm, center);
    ctx!.lineTo(center + arm, center);
    ctx!.moveTo(center, center - arm);
    ctx!.lineTo(center, center + arm);
    ctx!.stroke();
  }

  switch (kind) {
    case 'cross':
      ring(size * 0.38, 14);
      cross(size * 0.22, 18);
      break;
    case 'pulse': {
      ring(size * 0.38, 12);
      const y = center;
      const r = size * 0.38;
      ctx.lineWidth = 10;
      ctx.beginPath();
      ctx.moveTo(center - r * 0.7, y);
      ctx.lineTo(center - r * 0.3, y);
      ctx.lineTo(center - r * 0.1, y - r * 0.55);
      ctx.lineTo(center + r * 0.1, y + r * 0.55);
      ctx.lineTo(center + r * 0.3, y);
      ctx.lineTo(center + r * 0.7, y);
      ctx.stroke();
      break;
    }
    case 'shield': {
      const w = size * 0.6;
      const h = size * 0.72;
      const x = center - w / 2;
      const y = center - h / 2;
      ctx.lineWidth = 12;
      ctx.beginPath();
      ctx.moveTo(center, y);
      ctx.lineTo(x + w, y + h * 0.28);
      ctx.quadraticCurveTo(x + w, y + h * 0.82, center, y + h);
      ctx.quadraticCurveTo(x, y + h * 0.82, x, y + h * 0.28);
      ctx.closePath();
      ctx.stroke();
      cross(size * 0.14, 12);
      break;
    }
    case 'bold-cross':
      cross(size * 0.3, 32);
      break;
  }

  return new Promise((resolve, reject) => {
    canvas.toBlob((blob) => {
      if (!blob) {
        reject(new Error('Failed to generate placeholder logo'));
        return;
      }
      resolve(new File([blob], `${kind}-logo.png`, { type: 'image/png' }));
    }, 'image/png');
  });
}
