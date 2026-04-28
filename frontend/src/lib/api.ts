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
  token?: string,
): Promise<JobStatus> {
  const { data } = await api.post<JobStatus>('/api/research', {
    topic,
    max_papers: maxPapers,
    min_year: minYear,
    use_rebel: false,
    use_cache: useCache,
  }, {
    headers: token ? { Authorization: `Bearer ${token}` } : {}
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

export async function generateLitReview(jobId: string): Promise<{ literature_review: string }> {
  const { data } = await api.post(`/api/generate_lit_review?job_id=${jobId}`);
  return data;
}

export async function checkNovelty(jobId: string, proposal: string): Promise<any> {
  const { data } = await api.post(`/api/check_novelty`, { job_id: jobId, proposal });
  return data;
}

export async function registerUser(email: string, password: string): Promise<any> {
  const { data } = await api.post('/api/auth/register', { email, password });
  return data;
}

export async function loginUser(email: string, password: string): Promise<any> {
  const { data } = await api.post('/api/auth/login', { email, password });
  return data;
}

export async function listUserJobs(token: string): Promise<any[]> {
  const { data } = await api.get('/api/user/jobs', {
    headers: { Authorization: `Bearer ${token}` }
  });
  return data;
}

export async function deleteJob(jobId: string, token: string): Promise<void> {
  await api.delete(`/api/jobs/${jobId}`, {
    headers: { Authorization: `Bearer ${token}` }
  });
}


