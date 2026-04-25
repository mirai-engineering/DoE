import { useState } from 'react';

/**
 * Props interface for the BatchImageUpload component
 * Supports multiple file selection for batch processing
 */
interface BatchImageUploadProps {
  onFilesSelect: (files: File[]) => void; // Callback with array of selected files
  selectedFiles: File[]; // Currently selected files
}

/**
 * Component that provides drag-and-drop and click-to-upload functionality
 * for multiple image files. Supports TIFF, PNG, and JPG formats.
 */
export default function BatchImageUpload({ onFilesSelect, selectedFiles }: BatchImageUploadProps) {
  const [dragActive, setDragActive] = useState(false);

  /**
   * Validates if a file is a supported image format
   */
  const isValidImageFile = (file: File): boolean => {
    const validExtensions = ['.tif', '.tiff', '.png', '.jpg', '.jpeg'];
    const fileName = file.name.toLowerCase();
    return validExtensions.some(ext => fileName.endsWith(ext));
  };

  /**
   * Handles drag events to provide visual feedback
   */
  const handleDrag = (e: React.DragEvent) => {
    e.preventDefault();
    e.stopPropagation();
    
    if (e.type === "dragenter" || e.type === "dragover") {
      setDragActive(true);
    } else if (e.type === "dragleave") {
      setDragActive(false);
    }
  };

  /**
   * Handles the drop event when user releases files over the drop zone
   * Filters valid image files and passes them to parent component
   */
  const handleDrop = (e: React.DragEvent) => {
    e.preventDefault();
    e.stopPropagation();
    setDragActive(false);
    
    if (e.dataTransfer.files && e.dataTransfer.files.length > 0) {
      const files = Array.from(e.dataTransfer.files);
      const validFiles = files.filter(isValidImageFile);
      
      if (validFiles.length > 0) {
        onFilesSelect(validFiles);
      }
    }
  };

  /**
   * Handles file selection via the file input (click to browse)
   */
  const handleChange = (e: React.ChangeEvent<HTMLInputElement>) => {
    if (e.target.files && e.target.files.length > 0) {
      const files = Array.from(e.target.files);
      const validFiles = files.filter(isValidImageFile);
      
      if (validFiles.length > 0) {
        onFilesSelect(validFiles);
      }
    }
  };

  /**
   * Removes a file from the selection
   */
  const handleRemoveFile = (index: number) => {
    const newFiles = selectedFiles.filter((_, i) => i !== index);
    onFilesSelect(newFiles);
  };

  /**
   * Clears all selected files
   */
  const handleClearAll = () => {
    onFilesSelect([]);
  };

  return (
    <div className="space-y-4">
      {/* Drop zone */}
      <div
        className={`border-2 border-dashed rounded-lg p-8 text-center transition-colors ${
          dragActive ? 'border-blue-500 bg-blue-50' : 'border-gray-300'
        }`}
        onDragEnter={handleDrag}
        onDragLeave={handleDrag}
        onDragOver={handleDrag}
        onDrop={handleDrop}
      >
        <input
          type="file"
          id="batch-file-upload"
          className="hidden"
          accept=".tif,.tiff,.png,.jpg,.jpeg"
          multiple
          onChange={handleChange}
        />
        <label
          htmlFor="batch-file-upload"
          className="cursor-pointer flex flex-col items-center"
        >
          <svg className="w-12 h-12 text-gray-400 mb-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
            <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M7 16a4 4 0 01-.88-7.903A5 5 0 1115.9 6L16 6a5 5 0 011 9.9M15 13l-3-3m0 0l-3 3m3-3v12" />
          </svg>
          <p className="text-gray-600 mb-2">
            Drag images here or click to select multiple files
          </p>
          <p className="text-sm text-gray-500">
            Supported formats: TIFF, PNG, JPG (multiple files allowed)
          </p>
        </label>
      </div>

      {/* Selected files list */}
      {selectedFiles.length > 0 && (
        <div className="border rounded-lg p-4 bg-white">
          <div className="flex justify-between items-center mb-3">
            <h3 className="text-sm font-semibold text-gray-700">
              Selected Files ({selectedFiles.length})
            </h3>
            <button
              onClick={handleClearAll}
              className="text-sm text-red-600 hover:text-red-700 font-medium"
            >
              Clear All
            </button>
          </div>
          <div className="space-y-2 max-h-48 overflow-y-auto">
            {selectedFiles.map((file, index) => (
              <div
                key={`${file.name}-${index}`}
                className="flex items-center justify-between p-2 bg-gray-50 rounded hover:bg-gray-100"
              >
                <div className="flex items-center gap-2 flex-1 min-w-0">
                  <svg className="w-5 h-5 text-gray-400 flex-shrink-0" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                    <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M4 16l4.586-4.586a2 2 0 012.828 0L16 16m-2-2l1.586-1.586a2 2 0 012.828 0L20 14m-6-6h.01M6 20h12a2 2 0 002-2V6a2 2 0 00-2-2H6a2 2 0 00-2 2v12a2 2 0 002 2z" />
                  </svg>
                  <span className="text-sm text-gray-700 truncate" title={file.name}>
                    {file.name}
                  </span>
                  <span className="text-xs text-gray-500 flex-shrink-0">
                    ({(file.size / 1024 / 1024).toFixed(2)} MB)
                  </span>
                </div>
                <button
                  onClick={() => handleRemoveFile(index)}
                  className="ml-2 text-red-500 hover:text-red-700 flex-shrink-0"
                  aria-label={`Remove ${file.name}`}
                >
                  <svg className="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                    <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M6 18L18 6M6 6l12 12" />
                  </svg>
                </button>
              </div>
            ))}
          </div>
        </div>
      )}
    </div>
  );
}

