import { useState, useCallback, useEffect, useRef, useMemo } from 'react';
import { predictSegmentation, PredictionResponse } from '../lib/api';

/**
 * Job status types for batch processing
 */
export type JobStatus = 'pending' | 'processing' | 'completed' | 'error';

/**
 * Individual job in the processing queue
 */
export interface BatchJob {
  id: string; // Unique identifier
  file: File; // Original file
  status: JobStatus;
  result: PredictionResponse | null; // Segmentation result
  error: string | null; // Error message if failed
  startTime: number | null; // Processing start timestamp
  endTime: number | null; // Processing end timestamp
}

/**
 * Statistics for batch processing
 */
export interface BatchStats {
  total: number;
  completed: number;
  processing: number;
  pending: number;
  errors: number;
  progress: number; // 0-100 percentage
}

/**
 * Configuration for batch processing
 */
interface BatchConfig {
  maxConcurrent: number; // Maximum parallel processing jobs
}

const DEFAULT_CONFIG: BatchConfig = {
  maxConcurrent: 3, // Process 3 images at a time
};

/**
 * Custom hook for managing batch image processing queue
 * Handles concurrent processing, retries, and state management
 */
export function useBatchProcessing(config: Partial<BatchConfig> = {}) {
  const finalConfig = { ...DEFAULT_CONFIG, ...config };
  const [jobs, setJobs] = useState<BatchJob[]>([]);
  const processingRef = useRef<Set<string>>(new Set()); // Track currently processing job IDs

  /**
   * Helper to update a job by ID
   */
  const updateJob = useCallback((jobId: string, updates: Partial<BatchJob>) => {
    setJobs(prev => prev.map(j => j.id === jobId ? { ...j, ...updates } : j));
  }, []);

  /**
   * Calculate batch statistics (memoized)
   */
  const stats = useMemo((): BatchStats => {
    const total = jobs.length;
    const completed = jobs.filter(j => j.status === 'completed').length;
    const processing = jobs.filter(j => j.status === 'processing').length;
    const pending = jobs.filter(j => j.status === 'pending').length;
    const errors = jobs.filter(j => j.status === 'error').length;
    const progress = total > 0 ? Math.round((completed / total) * 100) : 0;

    return {
      total,
      completed,
      processing,
      pending,
      errors,
      progress,
    };
  }, [jobs]);

  /**
   * Process a single job
   */
  const processJob = useCallback(async (job: BatchJob) => {
    // Mark as processing
    updateJob(job.id, { status: 'processing', startTime: Date.now() });

    try {
      const result = await predictSegmentation(job.file);
      updateJob(job.id, { status: 'completed', result, error: null, endTime: Date.now() });
    } catch (err: any) {
      const errorMessage = err.response?.data?.detail || err.message || 'Error processing image';
      updateJob(job.id, { status: 'error', error: errorMessage, endTime: Date.now() });
    } finally {
      processingRef.current.delete(job.id);
    }
  }, [updateJob]);

  /**
   * Process the queue (up to maxConcurrent jobs in parallel)
   */
  const processQueue = useCallback(() => {
    const pendingJobs = jobs.filter(j => j.status === 'pending');
    const currentlyProcessing = jobs.filter(j => j.status === 'processing').length;
    const availableSlots = finalConfig.maxConcurrent - currentlyProcessing;

    if (availableSlots <= 0 || pendingJobs.length === 0) {
      return;
    }

    // Start processing up to availableSlots jobs
    const jobsToProcess = pendingJobs.slice(0, availableSlots);
    
    jobsToProcess.forEach(job => {
      if (!processingRef.current.has(job.id)) {
        processingRef.current.add(job.id);
        processJob(job);
      }
    });
  }, [jobs, finalConfig.maxConcurrent, processJob]);

  /**
   * Process queue whenever jobs change
   */
  useEffect(() => {
    processQueue();
  }, [processQueue]);

  /**
   * Add new jobs to the queue
   */
  const addJobs = useCallback((files: File[]) => {
    const newJobs: BatchJob[] = files.map(file => ({
      id: `${file.name}-${Date.now()}-${Math.random()}`,
      file,
      status: 'pending' as JobStatus,
      result: null,
      error: null,
      startTime: null,
      endTime: null,
    }));

    setJobs(prev => [...prev, ...newJobs]);
  }, []);

  /**
   * Retry a failed job
   */
  const retryJob = useCallback((jobId: string) => {
    updateJob(jobId, { status: 'pending', error: null, startTime: null, endTime: null });
  }, [updateJob]);

  /**
   * Remove a job from the queue
   */
  const removeJob = useCallback((jobId: string) => {
    setJobs(prev => prev.filter(j => j.id !== jobId));
    processingRef.current.delete(jobId);
  }, []);

  /**
   * Clear all completed jobs
   */
  const clearCompleted = useCallback(() => {
    setJobs(prev => prev.filter(j => j.status !== 'completed'));
  }, []);

  /**
   * Clear all jobs
   */
  const clearAll = useCallback(() => {
    setJobs([]);
    processingRef.current.clear();
  }, []);

  const isProcessing = stats.processing > 0 || stats.pending > 0;

  return {
    jobs,
    stats,
    isProcessing,
    addJobs,
    retryJob,
    removeJob,
    clearCompleted,
    clearAll,
  };
}

