import { useState } from 'react';
import { BatchJob } from '../hooks/useBatchProcessing';
import SegmentationResult from './SegmentationResult';
import { downloadOverlay } from '../lib/imageUtils';

/**
 * Props interface for BatchResultItem component
 */
interface BatchResultItemProps {
  job: BatchJob;
  onRetry: (jobId: string) => void;
  onRemove: (jobId: string) => void;
}

/**
 * Status configuration mapping
 */
const STATUS_CONFIG = {
  completed: {
    icon: (
      <svg className="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
        <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M5 13l4 4L19 7" />
      </svg>
    ),
    color: 'text-green-600',
    bgColor: 'bg-green-50',
    label: 'Completed',
  },
  processing: {
    icon: <div className="animate-spin rounded-full h-5 w-5 border-b-2 border-blue-600"></div>,
    color: 'text-blue-600',
    bgColor: 'bg-blue-50',
    label: 'Processing',
  },
  error: {
    icon: (
      <svg className="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
        <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M6 18L18 6M6 6l12 12" />
      </svg>
    ),
    color: 'text-red-600',
    bgColor: 'bg-red-50',
    label: 'Error',
  },
  pending: {
    icon: (
      <svg className="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
        <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M12 8v4l3 3m6-3a9 9 0 11-18 0 9 9 0 0118 0z" />
      </svg>
    ),
    color: 'text-gray-600',
    bgColor: 'bg-gray-50',
    label: 'Pending',
  },
} as const;

/**
 * Individual result item in the batch processing list
 * Shows preview, status, and expandable detailed view
 */
export default function BatchResultItem({ job, onRetry, onRemove }: BatchResultItemProps) {
  const [isExpanded, setIsExpanded] = useState(false);
  const [opacity, setOpacity] = useState(0.5);

  const statusDisplay = STATUS_CONFIG[job.status];

  /**
   * Get processing time in seconds
   */
  const processingTime = job.startTime && job.endTime
    ? `${((job.endTime - job.startTime) / 1000).toFixed(1)}s`
    : job.startTime
    ? `${((Date.now() - job.startTime) / 1000).toFixed(1)}s (processing)`
    : null;

  return (
    <div className={`border rounded-lg transition-all ${isExpanded ? 'shadow-md' : ''}`}>
      {/* Collapsed view - always visible */}
      <div className={`p-4 ${statusDisplay.bgColor} ${isExpanded ? 'border-b' : ''}`}>
        <div className="flex items-center gap-4">
          {/* Status icon */}
          <div className={`flex-shrink-0 ${statusDisplay.color}`}>
            {statusDisplay.icon}
          </div>

          {/* Preview thumbnail */}
          <div className="flex-shrink-0">
            {job.result?.mask ? (
              <img
                src={`data:image/png;base64,${job.result.mask}`}
                alt="Preview"
                className="w-16 h-16 object-cover rounded border border-gray-300"
              />
            ) : job.status === 'processing' ? (
              <div className="w-16 h-16 bg-gray-200 rounded border border-gray-300 flex items-center justify-center">
                <div className="animate-spin rounded-full h-6 w-6 border-b-2 border-blue-500"></div>
              </div>
            ) : (
              <div className="w-16 h-16 bg-gray-200 rounded border border-gray-300 flex items-center justify-center">
                <svg className="w-8 h-8 text-gray-400" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                  <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M4 16l4.586-4.586a2 2 0 012.828 0L16 16m-2-2l1.586-1.586a2 2 0 012.828 0L20 14m-6-6h.01M6 20h12a2 2 0 002-2V6a2 2 0 00-2-2H6a2 2 0 00-2 2v12a2 2 0 002 2z" />
                </svg>
              </div>
            )}
          </div>

          {/* File info */}
          <div className="flex-1 min-w-0">
            <div className="flex items-center gap-2 mb-1">
              <p className="font-medium text-gray-900 truncate" title={job.file.name}>
                {job.file.name}
              </p>
              <span className={`text-xs px-2 py-0.5 rounded ${statusDisplay.bgColor} ${statusDisplay.color} font-medium`}>
                {statusDisplay.label}
              </span>
            </div>
            <div className="flex items-center gap-4 text-xs text-gray-500">
              <span>{(job.file.size / 1024 / 1024).toFixed(2)} MB</span>
              {processingTime && <span>Time: {processingTime}</span>}
              {job.error && (
                <span className="text-red-600 truncate max-w-xs" title={job.error}>
                  Error: {job.error}
                </span>
              )}
            </div>
          </div>

          {/* Action buttons */}
          <div className="flex items-center gap-2 flex-shrink-0">
            {job.status === 'completed' && job.result?.mask && job.result?.original && (() => {
              const original = job.result.original;
              const mask = job.result.mask;
              return (
                <button
                  onClick={() => downloadOverlay(original, mask, job.file.name, opacity)}
                  className="p-2 text-green-600 hover:bg-green-100 rounded transition-colors"
                  title="Download overlay"
                >
                <svg className="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                  <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M4 16v1a3 3 0 003 3h10a3 3 0 003-3v-1m-4-4l-4 4m0 0l-4-4m4 4V4" />
                </svg>
              </button>
              );
            })()}
            {job.status === 'error' && (
              <button
                onClick={() => onRetry(job.id)}
                className="p-2 text-blue-600 hover:bg-blue-100 rounded transition-colors"
                title="Retry"
              >
                <svg className="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                  <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M4 4v5h.582m15.356 2A8.001 8.001 0 004.582 9m0 0H9m11 11v-5h-.581m0 0a8.003 8.003 0 01-15.357-2m15.357 2H15" />
                </svg>
              </button>
            )}
            <button
              onClick={() => setIsExpanded(!isExpanded)}
              className="p-2 text-gray-600 hover:bg-gray-100 rounded transition-colors"
              title={isExpanded ? 'Collapse' : 'Expand'}
            >
              <svg
                className={`w-5 h-5 transition-transform ${isExpanded ? 'rotate-180' : ''}`}
                fill="none"
                stroke="currentColor"
                viewBox="0 0 24 24"
              >
                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M19 9l-7 7-7-7" />
              </svg>
            </button>
            <button
              onClick={() => onRemove(job.id)}
              className="p-2 text-red-600 hover:bg-red-100 rounded transition-colors"
              title="Remove"
            >
              <svg className="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M6 18L18 6M6 6l12 12" />
              </svg>
            </button>
          </div>
        </div>
      </div>

      {/* Expanded view - detailed segmentation result */}
      {isExpanded && job.status === 'completed' && job.result && (
        <div className="p-4 bg-white">
          <SegmentationResult
            mask={job.result.mask}
            original={job.result.original}
            loading={false}
            error={null}
            originalFile={job.file}
            opacity={opacity}
            onOpacityChange={setOpacity}
          />
        </div>
      )}

      {/* Expanded view - error state */}
      {isExpanded && job.status === 'error' && (
        <div className="p-4 bg-red-50 border-t border-red-200">
          <div className="flex items-start gap-3">
            <svg className="w-5 h-5 text-red-600 flex-shrink-0 mt-0.5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M12 8v4m0 4h.01M21 12a9 9 0 11-18 0 9 9 0 0118 0z" />
            </svg>
            <div className="flex-1">
              <p className="font-medium text-red-900 mb-1">Processing Error</p>
              <p className="text-sm text-red-700">{job.error || 'Unknown error occurred'}</p>
              <button
                onClick={() => onRetry(job.id)}
                className="mt-3 px-4 py-2 bg-red-600 text-white rounded hover:bg-red-700 transition-colors text-sm font-medium"
              >
                Retry Processing
              </button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}

