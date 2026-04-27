import axios from 'axios';
import { JobStatus } from './types';

const API_BASE = process.env.NEXT_PUBLIC_API_URL || 'http://localhost:8000';
const WS_BASE = API_BASE.replace(/^http/, 'ws');

export const api = axios.create({ baseURL: API_BASE });

export async function startResearch(
  topic: string,
  maxPapers = 40,
  minYear = 2018,
  useCache = true,
): Promise<JobStatus> {
  const { data } = await api.post<JobStatus>('/api/research', {
    topic,
    max_papers: maxPapers,
    min_year: minYear,
    use_rebel: false,
    use_cache: useCache,
  });
  return data;
}

export async function pollStatus(jobId: string): Promise<JobStatus> {
  const { data } = await api.get<JobStatus>(`/api/status/${jobId}`);
  return data;
}

export function getWsProgressUrl(jobId: string): string {
  return `${WS_BASE}/ws/progress/${jobId}`;
}

export function getGraphUrl(jobId: string): string {
  return `${API_BASE}/api/graph/${jobId}`;
}
