/**
 * Utility functions for image processing and manipulation
 * Handles mask colorization, base64 conversion, and file downloads
 */

/**
 * Converts a base64 string to a Blob
 * @param base64 - Base64 encoded string
 * @param mimeType - MIME type of the image (default: 'image/png')
 * @returns Blob object ready for download
 */
export function base64ToBlob(base64: string, mimeType: string = 'image/png'): Blob {
  const byteCharacters = atob(base64);
  const byteNumbers = new Array(byteCharacters.length);
  for (let i = 0; i < byteCharacters.length; i++) {
    byteNumbers[i] = byteCharacters.charCodeAt(i);
  }
  const byteArray = new Uint8Array(byteNumbers);
  return new Blob([byteArray], { type: mimeType });
}

/**
 * Triggers a file download from a Blob
 * @param blob - Blob object to download
 * @param filename - Name of the file to download
 */
export function downloadBlob(blob: Blob, filename: string): void {
  const url = URL.createObjectURL(blob);
  const link = document.createElement('a');
  link.href = url;
  link.download = filename;
  document.body.appendChild(link);
  link.click();
  document.body.removeChild(link);
  URL.revokeObjectURL(url);
}

/**
 * Colorizes a mask image by converting bright pixels to red/pink and making dark pixels transparent
 * @param maskBase64 - Base64 encoded mask image
 * @returns Promise that resolves to a data URL of the colored mask
 */
export function colorizeMask(maskBase64: string): Promise<string> {
  return new Promise((resolve, reject) => {
    const canvas = document.createElement('canvas');
    const ctx = canvas.getContext('2d');
    if (!ctx) {
      reject(new Error('Could not get canvas context'));
      return;
    }

    const img = new Image();
    
    img.onload = () => {
      canvas.width = img.width;
      canvas.height = img.height;
      ctx.drawImage(img, 0, 0);
      
      const imageData = ctx.getImageData(0, 0, canvas.width, canvas.height);
      const data = imageData.data;
      
      // Colorize mask: bright pixels -> red/pink, dark -> transparent
      for (let i = 0; i < data.length; i += 4) {
        const brightness = (data[i] + data[i + 1] + data[i + 2]) / 3;
        if (brightness > 50 && data[i + 3] > 0) {
          data[i] = 255;     // R
          data[i + 1] = 0;    // G
          data[i + 2] = 122;  // B
        } else {
          data[i + 3] = 0; // Transparent
        }
      }
      
      ctx.putImageData(imageData, 0, 0);
      resolve(canvas.toDataURL('image/png'));
    };
    
    img.onerror = () => {
      reject(new Error('Failed to load mask image'));
    };
    
    img.src = `data:image/png;base64,${maskBase64}`;
  });
}

/**
 * Downloads an overlay image (original + colored mask combined)
 * @param originalBase64 - Base64 encoded original image
 * @param maskBase64 - Base64 encoded mask image
 * @param filename - Name of the file to download (extension will be replaced with _overlay.png)
 * @param opacity - Opacity of the overlay (0-1, default: 0.5)
 * @returns Promise that resolves when download is triggered
 */
export function downloadOverlay(
  originalBase64: string,
  maskBase64: string,
  filename: string,
  opacity: number = 0.5
): Promise<void> {
  return new Promise((resolve) => {
    // First colorize the mask
    colorizeMask(maskBase64)
      .then((coloredMaskDataUrl) => {
        const canvas = document.createElement('canvas');
        const ctx = canvas.getContext('2d');
        if (!ctx) return resolve();

        const originalImg = new Image();
        const coloredMaskImg = new Image();

        // Load colored mask
        coloredMaskImg.onload = () => {
          // Load original image
          originalImg.onload = () => {
            canvas.width = originalImg.width;
            canvas.height = originalImg.height;
            ctx.drawImage(originalImg, 0, 0);
            ctx.globalAlpha = opacity;
            ctx.drawImage(coloredMaskImg, 0, 0);
            ctx.globalAlpha = 1.0;

            canvas.toBlob((blob) => {
              if (!blob) return resolve();
              const overlayFilename = `${filename.replace(/\.[^/.]+$/, '')}_overlay.png`;
              downloadBlob(blob, overlayFilename);
              resolve();
            }, 'image/png');
          };
          originalImg.onerror = () => resolve();
          originalImg.src = `data:image/png;base64,${originalBase64}`;
        };
        coloredMaskImg.onerror = () => resolve();
        coloredMaskImg.src = coloredMaskDataUrl;
      })
      .catch(() => resolve());
  });
}

