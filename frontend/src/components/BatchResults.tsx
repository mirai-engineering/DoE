import { useMemo } from 'react';
import { BatchJob, BatchStats } from '../hooks/useBatchProcessing';
import BatchResultItem from './BatchResultItem';
import { downloadOverlay, base64ToBlob, downloadBlob } from '../lib/imageUtils';

/**
 * Props interface for BatchResults component
 */
interface BatchResultsProps {
  jobs: BatchJob[];
  stats: BatchStats;
  onRetry: (jobId: string) => void;
  onRemove: (jobId: string) => void;
  onClearCompleted: () => void;
}

/**
 * Component that displays batch processing results in a list format
 * Shows progress bar, statistics, and individual result items
 */
export default function BatchResults({
  jobs,
  stats,
  onRetry,
  onRemove,
  onClearCompleted,
}: BatchResultsProps) {

  /**
   * Calculate estimated time remaining
   */
  const estimatedTimeRemaining = useMemo(() => {
    if (stats.processing === 0 || stats.pending === 0) return null;

    // Get average processing time from completed jobs
    const completedJobs = jobs.filter(j => j.status === 'completed' && j.startTime && j.endTime);
    if (completedJobs.length === 0) return null;

    const avgTime = completedJobs.reduce((sum, job) => {
      if (job.startTime && job.endTime) {
        return sum + (job.endTime - job.startTime);
      }
      return sum;
    }, 0) / completedJobs.length;

    const remainingTime = (stats.pending + stats.processing) * avgTime;
    const seconds = Math.ceil(remainingTime / 1000);
    
    if (seconds < 60) return `${seconds}s`;
    const minutes = Math.floor(seconds / 60);
    const remainingSeconds = seconds % 60;
    return `${minutes}m ${remainingSeconds}s`;
  }, [jobs, stats]);

  /**
   * Get completed jobs for download (with both original and mask)
   */
  const completedJobs = useMemo(() => {
    return jobs.filter(j => 
      j.status === 'completed' && 
      j.result?.mask && 
      j.result?.original
    );
  }, [jobs]);

  /**
   * Handle download all completed overlays
   * Downloads the combined overlay image (original + mask) for all completed jobs
   */
  const handleDownloadAll = async () => {
    for (let i = 0; i < completedJobs.length; i++) {
      const job = completedJobs[i];
      // Stagger downloads to avoid browser blocking
      await new Promise(resolve => setTimeout(resolve, i * 200));
      await downloadOverlay(
        job.result!.original,
        job.result!.mask,
        job.file.name,
        0.5 // Default opacity for batch download
      );
    }
  };

  /**
   * Handle download all completed masks (original masks without colorization)
   */
  const handleDownloadAllMasks = async () => {
    for (let i = 0; i < completedJobs.length; i++) {
      const job = completedJobs[i];
      // Stagger downloads to avoid browser blocking
      await new Promise(resolve => setTimeout(resolve, i * 200));
      const blob = base64ToBlob(job.result!.mask);
      const filename = `${job.file.name.replace(/\.[^/.]+$/, '')}_mask.png`;
      downloadBlob(blob, filename);
    }
  };

  if (jobs.length === 0) {
    return null;
  }

  return (
    <div className="space-y-4">
      {/* Statistics and progress bar */}
      <div className="bg-white border rounded-lg p-4">
        <div className="flex items-center justify-between mb-3">
          <div>
            <h3 className="text-lg font-semibold text-gray-900">
              Batch Processing Status
            </h3>
            <p className="text-sm text-gray-600 mt-1">
              {stats.completed} of {stats.total} completed
              {stats.errors > 0 && <span className="text-red-600"> • {stats.errors} errors</span>}
              {stats.processing > 0 && <span className="text-blue-600"> • {stats.processing} processing</span>}
              {stats.pending > 0 && <span className="text-gray-600"> • {stats.pending} pending</span>}
            </p>
          </div>
          <div className="flex gap-2 flex-wrap">
            {completedJobs.length > 0 && (
              <>
                <button
                  onClick={handleDownloadAll}
                  className="px-4 py-2 bg-green-600 text-white rounded-lg hover:bg-green-700 transition-colors text-sm font-medium flex items-center gap-2"
                >
                  <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                    <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M4 16v1a3 3 0 003 3h10a3 3 0 003-3v-1m-4-4l-4 4m0 0l-4-4m4 4V4" />
                  </svg>
                  Download All Overlays ({completedJobs.length})
                </button>
                <button
                  onClick={handleDownloadAllMasks}
                  className="px-4 py-2 bg-blue-600 text-white rounded-lg hover:bg-blue-700 transition-colors text-sm font-medium flex items-center gap-2"
                >
                  <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                    <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M4 16v1a3 3 0 003 3h10a3 3 0 003-3v-1m-4-4l-4 4m0 0l-4-4m4 4V4" />
                  </svg>
                  Download All Masks ({completedJobs.length})
                </button>
              </>
            )}
            {stats.completed > 0 && (
              <button
                onClick={onClearCompleted}
                className="px-4 py-2 bg-gray-200 text-gray-700 rounded-lg hover:bg-gray-300 transition-colors text-sm font-medium"
              >
                Clear Completed
              </button>
            )}
          </div>
        </div>

        {/* Progress bar */}
        <div className="w-full bg-gray-200 rounded-full h-3 mb-2">
          <div
            className="bg-blue-600 h-3 rounded-full transition-all duration-300"
            style={{ width: `${stats.progress}%` }}
          />
        </div>
        <div className="flex justify-between items-center text-xs text-gray-500">
          <span>{stats.progress}% complete</span>
          {estimatedTimeRemaining && (
            <span>Estimated time remaining: {estimatedTimeRemaining}</span>
          )}
        </div>
      </div>

      {/* Results list */}
      <div className="space-y-3">
        {jobs.map((job) => (
          <BatchResultItem
            key={job.id}
            job={job}
            onRetry={onRetry}
            onRemove={onRemove}
          />
        ))}
      </div>
    </div>
  );
}

