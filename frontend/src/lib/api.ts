import axios from 'axios';

// Use environment variable or default to localhost for development
const API_URL = import.meta.env.VITE_API_URL || 'http://localhost:8000';

export const api = axios.create({
  baseURL: API_URL,
});

export interface PredictionResponse {
  mask: string; // base64 encoded PNG
  original: string; // base64 encoded PNG (processed for display)
}

export async function predictSegmentation(file: File): Promise<PredictionResponse> {
  const formData = new FormData();
  formData.append('file', file);
  
  try {
    const response = await api.post<PredictionResponse>('/api/predict', formData, {
      timeout: 60000, // 60 seconds timeout
    });
    return response.data;
  } catch (error: any) {
    if (error.code === 'ECONNREFUSED' || error.message.includes('Network Error')) {
      throw new Error('Unable to connect to server. Please try again later.');
    }
    if (error.response) {
      throw new Error(error.response.data?.detail || error.response.data?.message || 'Server error occurred');
    }
    throw error;
  }
}

