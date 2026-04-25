import { useState, useEffect } from 'react';
import { colorizeMask, base64ToBlob, downloadBlob, downloadOverlay } from '../lib/imageUtils';

/**
 * Props interface for the SegmentationResult component
 * Defines all the data and callbacks needed to display segmentation results
 */
interface SegmentationResultProps {
  mask: string | null; // base64 encoded segmentation mask image from backend
  original: string | null; // base64 encoded original image (processed for display)
  loading: boolean; // indicates if image is currently being processed
  error: string | null; // error message if processing failed
  originalFile: File | null; // the original file uploaded by user
  opacity: number; // overlay opacity value between 0 and 1
  onOpacityChange: (opacity: number) => void; // callback to update opacity when slider changes
}

/**
 * Component that displays the segmentation result with overlay functionality
 * Shows the original image with a colored mask overlay that can be adjusted
 */
export default function SegmentationResult({ 
  mask, 
  original,
  loading, 
  error, 
  originalFile,
  opacity,
  onOpacityChange 
}: SegmentationResultProps) {
  // State to store the colored version of the mask (red/pink overlay)
  // Created by processing the mask image pixel by pixel using Canvas API
  const [coloredMaskUrl, setColoredMaskUrl] = useState<string | null>(null);

  /**
   * Effect hook that processes the mask image to create a colored overlay
   * Runs whenever the mask prop changes
   */
  useEffect(() => {
    if (!mask) {
      setColoredMaskUrl(null);
      return;
    }

    colorizeMask(mask)
      .then(setColoredMaskUrl)
      .catch(() => setColoredMaskUrl(null));
  }, [mask]);

  /**
   * Handles downloading the segmentation mask as a PNG file
   */
  const handleDownload = () => {
    if (!mask) return;
    const blob = base64ToBlob(mask, 'image/png');
    const filename = originalFile 
      ? `${originalFile.name.replace(/\.[^/.]+$/, '')}_mask.png`
      : 'segmentation_mask.png';
    downloadBlob(blob, filename);
  };

  /**
   * Handles downloading the overlay image (original + mask combined)
   */
  const handleDownloadOverlay = () => {
    if (!original || !mask) return;
    const filename = originalFile 
      ? originalFile.name
      : 'segmentation_overlay.png';
    downloadOverlay(original, mask, filename, opacity);
  };

  if (loading) {
    return (
      <div className="border rounded-lg p-8 flex items-center justify-center min-h-[256px]">
        <div className="text-center">
          <div className="animate-spin rounded-full h-12 w-12 border-b-2 border-blue-500 mx-auto mb-4"></div>
          <p className="text-gray-600">Processing image...</p>
        </div>
      </div>
    );
  }

  if (error) {
    return (
      <div className="border border-red-300 rounded-lg p-8 bg-red-50">
        <p className="text-red-600">Error: {error}</p>
      </div>
    );
  }

  if (!mask) {
    return (
      <div className="border-2 border-dashed border-gray-300 rounded-lg p-8 flex items-center justify-center min-h-[256px]">
        <p className="text-gray-400">
          {originalFile ? 'Segmentation mask will appear here' : 'Upload an image to get started'}
        </p>
      </div>
    );
  }

  // Determine if overlay mode is available (need mask, original, and colored mask)
  const showOverlay = mask && original && coloredMaskUrl;
  const imageClassName = "max-w-full max-h-[600px] object-contain";

  return (
    <div className="space-y-4">
      <div className="border rounded-lg overflow-hidden bg-gray-900 relative" style={{ minHeight: '400px' }}>
        <div className="relative w-full h-full flex items-center justify-center" style={{ minHeight: '400px' }}>
          {showOverlay ? (
            // Overlay mode: original image with colored mask on top
            <div className="relative inline-block">
              {opacity >= 1.0 ? (
                <img
                  src={`data:image/png;base64,${mask}`}
                  alt="Segmentation mask"
                  className={`block ${imageClassName}`}
                />
              ) : opacity <= 0 ? (
                <img
                  src={`data:image/png;base64,${original}`}
                  alt="Original CT/MRI image"
                  className={`block ${imageClassName}`}
                />
              ) : (
                <>
                  <img
                    src={`data:image/png;base64,${original}`}
                    alt="Original CT/MRI image"
                    className={`block ${imageClassName}`}
                  />
                  {coloredMaskUrl && (
                    <img
                      src={coloredMaskUrl}
                      alt="Segmentation overlay"
                      className={`absolute top-0 left-0 ${imageClassName} pointer-events-none`}
                      style={{ opacity }}
                    />
                  )}
                </>
              )}
            </div>
          ) : (
            // No overlay: show mask only
            <div className="text-center">
              {coloredMaskUrl ? (
                <img
                  src={coloredMaskUrl}
                  alt="Segmentation mask"
                  className={`${imageClassName} mx-auto`}
                />
              ) : (
                <img
                  src={`data:image/png;base64,${mask}`}
                  alt="Segmentation mask"
                  className={`${imageClassName} mx-auto`}
                />
              )}
            </div>
          )}
        </div>
      </div>

      <div className="space-y-4">
        {/* Opacity slider - only shown when overlay mode is available */}
        {showOverlay && (
          <div className="bg-white border rounded-lg p-4">
            <label className="block mb-2">
              <div className="flex justify-between items-center mb-2">
                <span className="text-sm font-medium text-gray-700">
                  Segmentation Overlay Opacity: {Math.round(opacity * 100)}%
                </span>
                <span className="text-xs text-gray-500">
                  {opacity <= 0 ? 'Original only' : opacity >= 1 ? 'Mask only' : 'Overlay'}
                </span>
              </div>
              <input
                type="range"
                min="0"
                max="1"
                step="0.05"
                value={opacity}
                onChange={(e) => onOpacityChange(parseFloat(e.target.value))}
                className="w-full mt-2 h-2 bg-gray-200 rounded-lg appearance-none cursor-pointer"
              />
              <div className="flex justify-between text-xs text-gray-400 mt-1">
                <span>0% - Original CT/MRI</span>
                <span>100% - Mask only</span>
              </div>
            </label>
          </div>
        )}

        {/* Download buttons */}
        <div className="flex justify-center gap-3 flex-wrap">
          <button
            onClick={handleDownload}
            className="bg-green-500 hover:bg-green-600 text-white font-semibold py-2 px-6 rounded-lg transition-colors flex items-center gap-2"
          >
            <svg className="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M4 16v1a3 3 0 003 3h10a3 3 0 003-3v-1m-4-4l-4 4m0 0l-4-4m4 4V4" />
            </svg>
            Download Mask
          </button>
          {showOverlay && (
            <button
              onClick={handleDownloadOverlay}
              className="bg-blue-500 hover:bg-blue-600 text-white font-semibold py-2 px-6 rounded-lg transition-colors flex items-center gap-2"
            >
              <svg className="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M4 16v1a3 3 0 003 3h10a3 3 0 003-3v-1m-4-4l-4 4m0 0l-4-4m4 4V4" />
              </svg>
              Download Overlay
            </button>
          )}
        </div>
      </div>
    </div>
  );
}

