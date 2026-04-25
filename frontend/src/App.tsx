import { useState } from 'react'
import ImageUpload from './components/ImageUpload'
import SegmentationResult from './components/SegmentationResult'
import BatchImageUpload from './components/BatchImageUpload'
import BatchResults from './components/BatchResults'
import { predictSegmentation } from './lib/api'
import { useBatchProcessing } from './hooks/useBatchProcessing'

/**
 * Main application component
 * Manages the entire segmentation workflow: upload -> process -> display results
 * Supports both single image and batch processing modes
 */
function App() {
  // Mode selection: 'single' or 'batch'
  const [mode, setMode] = useState<'single' | 'batch'>('single')
  
  // ===== Single Mode State =====
  // The image file selected by the user
  const [selectedFile, setSelectedFile] = useState<File | null>(null)
  
  // Base64 encoded segmentation mask returned from backend
  const [mask, setMask] = useState<string | null>(null)
  
  // Base64 encoded original image (processed for display) from backend
  const [original, setOriginal] = useState<string | null>(null)
  
  // Loading state: true while waiting for backend response
  const [loading, setLoading] = useState(false)
  
  // Error message if processing fails
  const [error, setError] = useState<string | null>(null)
  
  // Overlay opacity value (0 = original only, 1 = mask only, 0.5 = 50% overlay)
  const [opacity, setOpacity] = useState(0.5)

  // ===== Batch Mode State =====
  const {
    jobs,
    stats,
    addJobs,
    retryJob,
    removeJob,
    clearCompleted,
    clearAll,
  } = useBatchProcessing({ maxConcurrent: 3 })
  
  const [selectedFiles, setSelectedFiles] = useState<File[]>([])

  /**
   * Callback function called when user selects a new image file (single mode)
   * Automatically processes the image (following Deployment-Roadmap.md pattern)
   */
  const handleImageSelect = async (file: File) => {
    setSelectedFile(file)
    setMask(null)
    setOriginal(null)
    setError(null)
    setLoading(true)

    try {
      // Async operation - may take several seconds for large images
      const result = await predictSegmentation(file)
      
      if (!result.mask) {
        throw new Error('No mask received from server')
      }
      
      setMask(result.mask)
      setOriginal(result.original || null)
    } catch (err: any) {
      // Extract error message from FastAPI response format (err.response?.data?.detail)
      const errorMessage = err.response?.data?.detail || err.message || 'Error processing image. Please try again.'
      setError(errorMessage)
    } finally {
      setLoading(false)
    }
  }

  /**
   * Callback function called when user selects multiple files (batch mode)
   */
  const handleBatchFilesSelect = (files: File[]) => {
    setSelectedFiles(files)
    if (files.length > 0) {
      // Clear previous jobs and add new ones
      clearAll()
      addJobs(files)
    }
  }

  /**
   * Handle mode switch
   */
  const handleModeChange = (newMode: 'single' | 'batch') => {
    setMode(newMode)
    // Reset states when switching modes
    if (newMode === 'single') {
      setSelectedFiles([])
      clearAll()
    } else {
      setSelectedFile(null)
      setMask(null)
      setOriginal(null)
      setError(null)
      setLoading(false)
    }
  }

  return (
    <main className="min-h-screen bg-gray-50 py-8">
      <div className="container mx-auto px-4 max-w-6xl">
        {/* Page header */}
        <h1 className="text-4xl font-bold text-center mb-4 text-gray-800">
          Kidney Segmentation
        </h1>
        
        {/* Why-What-How Section */}
        <div className="bg-white rounded-lg border border-gray-200 p-4 mb-6 shadow-sm">
          <div className="grid grid-cols-1 md:grid-cols-3 gap-4 text-sm">
            <div>
              <h3 className="font-semibold text-gray-800 mb-1">Why</h3>
              <p className="text-gray-600 leading-relaxed">
                Automates manual segmentation that takes months, accelerating medical research and analysis.
              </p>
            </div>
            <div>
              <h3 className="font-semibold text-gray-800 mb-1">What</h3>
              <p className="text-gray-600 leading-relaxed">
                Automated kidney segmentation system that processes medical images and generates precise segmentation masks using artificial intelligence.
              </p>
            </div>
            <div>
              <h3 className="font-semibold text-gray-800 mb-1">How</h3>
              <p className="text-gray-600 leading-relaxed">
                Deep learning model (U-Net architecture) optimized with ONNX Runtime that processes normalized images and returns binary segmentation overlays in seconds.
              </p>
            </div>
          </div>
        </div>
        
        <p className="text-center text-gray-600 mb-8">
          Upload images to get kidney segmentation
        </p>

        {/* Mode selector */}
        <div className="flex justify-center mb-6">
          <div className="inline-flex rounded-lg border border-gray-300 bg-white p-1">
            <button
              onClick={() => handleModeChange('single')}
              className={`px-6 py-2 rounded-md text-sm font-medium transition-colors ${
                mode === 'single'
                  ? 'bg-blue-500 text-white'
                  : 'text-gray-700 hover:bg-gray-100'
              }`}
            >
              Single Image
            </button>
            <button
              onClick={() => handleModeChange('batch')}
              className={`px-6 py-2 rounded-md text-sm font-medium transition-colors ${
                mode === 'batch'
                  ? 'bg-blue-500 text-white'
                  : 'text-gray-700 hover:bg-gray-100'
              }`}
            >
              Batch Processing
            </button>
          </div>
        </div>

        <div className="space-y-6">
          {mode === 'single' ? (
            <>
              {/* Single Mode: Upload Section */}
          <div>
            <h2 className="text-xl font-semibold mb-2">Upload Image</h2>
            <ImageUpload
              onImageSelect={handleImageSelect}
              selectedFile={selectedFile}
            />
          </div>

              {/* Results Section - automatically shown when processing/complete */}
          {selectedFile && (
            <div>
              <h2 className="text-xl font-semibold mb-2">Segmentation Result</h2>
              <SegmentationResult 
                mask={mask}
                original={original}
                loading={loading}
                error={error}
                originalFile={selectedFile}
                opacity={opacity}
                onOpacityChange={setOpacity}
              />
            </div>
              )}
            </>
          ) : (
            <>
              {/* Batch Mode: Upload Section */}
              <div>
                <h2 className="text-xl font-semibold mb-2">Upload Images</h2>
                <BatchImageUpload
                  onFilesSelect={handleBatchFilesSelect}
                  selectedFiles={selectedFiles}
                />
              </div>

              {/* Batch Results Section */}
              {jobs.length > 0 && (
                <div>
                  <h2 className="text-xl font-semibold mb-2">Batch Processing Results</h2>
                  <BatchResults
                    jobs={jobs}
                    stats={stats}
                    onRetry={retryJob}
                    onRemove={removeJob}
                    onClearCompleted={clearCompleted}
                  />
                </div>
              )}
            </>
          )}
        </div>
      </div>
    </main>
  )
}

export default App

