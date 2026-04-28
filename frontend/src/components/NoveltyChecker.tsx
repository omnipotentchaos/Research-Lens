'use client';

import { useState } from 'react';
import { checkNovelty } from '@/lib/api';

export default function NoveltyChecker({ jobId }: { jobId: string }) {
  const [proposal, setProposal] = useState('');
  const [loading, setLoading] = useState(false);
  const [result, setResult] = useState<any>(null);
  const [error, setError] = useState('');

  const handleCheck = async () => {
    if (proposal.length < 10) {
      setError('Please enter a more detailed proposal (at least 10 characters).');
      return;
    }
    setLoading(true);
    setError('');
    setResult(null);
    try {
      const res = await checkNovelty(jobId, proposal);
      setResult(res);
    } catch (e: any) {
      setError(e.message || 'Failed to check novelty.');
    } finally {
      setLoading(false);
    }
  };

  return (
    <div className="glass" style={{ padding: '24px', borderRadius: 12 }}>
      <div style={{ display: 'flex', alignItems: 'center', gap: 12, marginBottom: 16 }}>
        <span style={{ fontSize: 24 }}>💡</span>
        <div>
          <h2 style={{ fontSize: 16, fontWeight: 600, color: '#e2e8f0', margin: 0 }}>"Am I Reinventing the Wheel?" Checker</h2>
          <p style={{ fontSize: 13, color: '#94a3b8', marginTop: 4 }}>
            Paste your thesis proposal or research idea. We'll compare it against the retrieved papers to see if it's truly novel.
          </p>
        </div>
      </div>

      <textarea
        value={proposal}
        onChange={e => setProposal(e.target.value)}
        placeholder="e.g., I want to use a Graph Neural Network combined with a multi-agent reinforcement learning approach for real-time fake news detection on encrypted messaging apps..."
        style={{
          width: '100%', minHeight: '120px', padding: '16px', borderRadius: 8,
          background: 'rgba(15,22,41,0.5)', border: '1px solid #1e293b',
          color: '#e2e8f0', fontSize: 14, fontFamily: 'inherit', resize: 'vertical',
          outline: 'none', marginBottom: 16
        }}
      />

      <button
        onClick={handleCheck}
        disabled={loading || !proposal}
        style={{
          padding: '10px 20px', borderRadius: 8, background: loading || !proposal ? '#475569' : '#059669', color: '#fff',
          border: 'none', cursor: loading || !proposal ? 'not-allowed' : 'pointer', fontWeight: 600, fontSize: 14,
          transition: 'background 0.2s', display: 'flex', alignItems: 'center', gap: 8
        }}
      >
        {loading && <div style={{ width: 14, height: 14, border: '2px solid rgba(255,255,255,0.3)', borderTopColor: '#fff', borderRadius: '50%', animation: 'spin 1s linear infinite' }} />}
        {loading ? 'Checking Novelty...' : '🔍 Check Novelty'}
      </button>

      {error && <div style={{ color: '#ef4444', fontSize: 13, marginTop: 12 }}>{error}</div>}

      {result && (
        <div style={{ marginTop: 24, paddingTop: 24, borderTop: '1px solid rgba(51,65,85,0.5)' }}>
          <div style={{ display: 'flex', alignItems: 'center', gap: 10, marginBottom: 16 }}>
            <div style={{
              padding: '6px 12px', borderRadius: 6, fontSize: 14, fontWeight: 700,
              background: result.is_novel ? 'rgba(16,185,129,0.15)' : 'rgba(239,68,68,0.15)',
              color: result.is_novel ? '#34d399' : '#f87171',
              border: `1px solid ${result.is_novel ? 'rgba(16,185,129,0.3)' : 'rgba(239,68,68,0.3)'}`
            }}>
              {result.is_novel ? '✅ Idea Appears Novel' : '⚠️ Potential Collision Detected'}
            </div>
            <div style={{ fontSize: 12, color: '#64748b' }}>
              Max similarity score: <span style={{ color: '#94a3b8', fontWeight: 600 }}>{(result.similarity_score * 100).toFixed(1)}%</span>
            </div>
          </div>

          <div style={{ fontSize: 14, color: '#e2e8f0', lineHeight: 1.7, marginBottom: 20 }}>
            {result.analysis}
          </div>

          <div style={{ fontSize: 12, fontWeight: 600, color: '#94a3b8', textTransform: 'uppercase', letterSpacing: '0.05em', marginBottom: 12 }}>
            Closest Existing Papers
          </div>
          <div style={{ display: 'flex', flexDirection: 'column', gap: 12 }}>
            {result.closest_papers.map((p: any, i: number) => (
              <div key={i} style={{ padding: '12px', borderRadius: 8, background: 'rgba(15,22,41,0.6)', border: '1px solid #1e293b' }}>
                <div style={{ fontWeight: 600, color: '#cbd5e1', fontSize: 13, marginBottom: 4 }}>{p.title} ({p.year})</div>
                <div style={{ fontSize: 12, color: '#64748b' }}>Similarity: {(p.similarity * 100).toFixed(1)}%</div>
              </div>
            ))}
          </div>
        </div>
      )}
      <style>{`@keyframes spin { to { transform: rotate(360deg); } }`}</style>
    </div>
  );
}
