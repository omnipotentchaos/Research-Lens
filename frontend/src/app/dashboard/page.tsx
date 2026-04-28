'use client';

import { useEffect, useState } from 'react';
import { useAuth } from '@/context/AuthContext';
import { listUserJobs, deleteJob } from '@/lib/api';
import { useRouter } from 'next/navigation';
import Link from 'next/link';

export default function DashboardPage() {
  const { user, token, isLoading } = useAuth();
  const [jobs, setJobs] = useState<any[]>([]);
  const [loading, setLoading] = useState(true);
  const router = useRouter();

  useEffect(() => {
    if (!isLoading && !token) {
      router.push('/auth');
      return;
    }

    if (token) {
      loadJobs();
    }
  }, [token, isLoading]);

  const loadJobs = async () => {
    try {
      const data = await listUserJobs(token!);
      setJobs(data);
    } catch (err) {
      console.error('Failed to load jobs', err);
    } finally {
      setLoading(false);
    }
  };

  const handleDelete = async (jobId: string) => {
    if (!confirm('Are you sure you want to delete this research?')) return;
    try {
      await deleteJob(jobId, token!);
      setJobs(jobs.filter(j => j.job_id !== jobId));
    } catch (err) {
      alert('Failed to delete job');
    }
  };

  if (isLoading || loading) {
    return <div style={{ padding: '40px', textAlign: 'center', color: '#94a3b8' }}>Loading your research...</div>;
  }

  return (
    <div style={{ maxWidth: '1000px', margin: '0 auto', padding: '48px 24px' }}>
      <header style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '40px' }}>
        <div>
          <h1 style={{ fontSize: '28px', fontWeight: '700', marginBottom: '8px' }}>Your Research Library</h1>
          <p style={{ color: '#94a3b8' }}>Welcome back, {user?.email}</p>
        </div>
        <Link href="/">
          <button style={{
            padding: '10px 20px', borderRadius: '8px', background: '#7c3aed',
            color: '#fff', border: 'none', fontWeight: '600', cursor: 'pointer'
          }}>
            New Research
          </button>
        </Link>
      </header>

      {jobs.length === 0 ? (
        <div className="glass" style={{ padding: '64px', textAlign: 'center', borderRadius: '16px' }}>
          <p style={{ color: '#94a3b8', fontSize: '18px', marginBottom: '24px' }}>You haven't started any research yet.</p>
          <Link href="/">
            <button style={{
              padding: '12px 24px', borderRadius: '8px', background: 'rgba(124,58,237,0.1)',
              color: '#a78bfa', border: '1px solid rgba(124,58,237,0.2)', fontWeight: '600', cursor: 'pointer'
            }}>
              Start Your First Map
            </button>
          </Link>
        </div>
      ) : (
        <div style={{ display: 'grid', gridTemplateColumns: '1fr', gap: '16px' }}>
          {jobs.map((job) => (
            <div key={job.job_id} className="glass" style={{
              padding: '24px', borderRadius: '12px', display: 'flex',
              justifyContent: 'space-between', alignItems: 'center',
              border: '1px solid rgba(124,58,237,0.1)'
            }}>
              <div style={{ flex: 1 }}>
                <h3 style={{ fontSize: '18px', fontWeight: '600', marginBottom: '4px' }}>{job.topic}</h3>
                <div style={{ display: 'flex', gap: '16px', fontSize: '13px', color: '#64748b' }}>
                  <span>{new Date(job.created_at * 1000).toLocaleDateString()}</span>
                  <span style={{
                    color: job.status === 'done' ? '#10b981' : job.status === 'error' ? '#ef4444' : '#7c3aed',
                    fontWeight: '600', textTransform: 'capitalize'
                  }}>
                    {job.status}
                  </span>
                </div>
              </div>
              <div style={{ display: 'flex', gap: '12px' }}>
                <Link href={`/results/${job.job_id}`}>
                  <button style={{
                    padding: '8px 16px', borderRadius: '6px', background: 'rgba(255,255,255,0.05)',
                    color: '#e2e8f0', border: '1px solid rgba(255,255,255,0.1)', cursor: 'pointer', fontSize: '14px'
                  }}>
                    View Result
                  </button>
                </Link>
                <button
                  onClick={() => handleDelete(job.job_id)}
                  style={{
                    padding: '8px 16px', borderRadius: '6px', background: 'rgba(239,68,68,0.1)',
                    color: '#f87171', border: '1px solid rgba(239,68,68,0.2)', cursor: 'pointer', fontSize: '14px'
                  }}
                >
                  Delete
                </button>
              </div>
            </div>
          ))}
        </div>
      )}
    </div>
  );
}
