import { useState } from 'react';

/**
 * Props interface for the ImageUpload component
 * Defines the callback and current file state
 */
interface ImageUploadProps {
  onImageSelect: (file: File) => void; // Callback function called when user selects a file
  selectedFile: File | null; // Currently selected file (null if no file selected)
}

/**
 * Component that provides drag-and-drop and click-to-upload functionality
 * Supports TIFF, PNG, and JPG image formats
 */
export default function ImageUpload({ onImageSelect, selectedFile }: ImageUploadProps) {
  // State to track if user is currently dragging a file over the drop zone
  // Used to change visual styling (highlight border/background)
  const [dragActive, setDragActive] = useState(false);

  /**
   * Handles drag events (enter, over, leave) to provide visual feedback
   * Prevents default browser behavior and updates dragActive state
   */
  const handleDrag = (e: React.DragEvent) => {
    e.preventDefault();
    e.stopPropagation();
    
    // Toggle visual highlight based on drag position
    if (e.type === "dragenter" || e.type === "dragover") {
      setDragActive(true);
    } else if (e.type === "dragleave") {
      setDragActive(false);
    }
  };

  /**
   * Handles the drop event when user releases a file over the drop zone
   * Extracts the dropped file and passes it to the parent component
   */
  const handleDrop = (e: React.DragEvent) => {
    e.preventDefault();
    e.stopPropagation();
    setDragActive(false);
    
    // Extract first file from dropped files and notify parent
    if (e.dataTransfer.files && e.dataTransfer.files[0]) {
      onImageSelect(e.dataTransfer.files[0]);
    }
  };

  /**
   * Handles file selection via the file input (click to browse)
   * Triggered when user clicks the upload area and selects a file
   */
  const handleChange = (e: React.ChangeEvent<HTMLInputElement>) => {
    if (e.target.files && e.target.files[0]) {
      onImageSelect(e.target.files[0]);
    }
  };

  return (
    <div
      className={`border-2 border-dashed rounded-lg p-8 text-center ${
        dragActive ? 'border-blue-500 bg-blue-50' : 'border-gray-300'
      }`}
      onDragEnter={handleDrag}
      onDragLeave={handleDrag}
      onDragOver={handleDrag}
      onDrop={handleDrop}
    >
      {/* Hidden file input - accessible via label click */}
      <input
        type="file"
        id="file-upload"
        className="hidden"
        accept=".tif,.tiff,.png,.jpg,.jpeg"
        onChange={handleChange}
      />
      <label
        htmlFor="file-upload"
        className="cursor-pointer flex flex-col items-center"
      >
        <svg className="w-12 h-12 text-gray-400 mb-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
          <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M7 16a4 4 0 01-.88-7.903A5 5 0 1115.9 6L16 6a5 5 0 011 9.9M15 13l-3-3m0 0l-3 3m3-3v12" />
        </svg>
        <p className="text-gray-600 mb-2">
          Drag an image here or click to select
        </p>
        <p className="text-sm text-gray-500">
          Supported formats: TIFF, PNG, JPG
        </p>
        {selectedFile && (
          <p className="mt-4 text-sm text-green-600">
            Selected file: {selectedFile.name}
          </p>
        )}
      </label>
    </div>
  );
}

