'use client';

import { useState } from 'react';
import { generateLitReview } from '@/lib/api';

export default function LitReview({ jobId }: { jobId: string }) {
  const [loading, setLoading] = useState(false);
  const [reviewText, setReviewText] = useState('');
  const [error, setError] = useState('');

  const handleGenerate = async () => {
    setLoading(true);
    setError('');
    try {
      const res = await generateLitReview(jobId);
      setReviewText(res.literature_review);
    } catch (e: any) {
      setError(e.message || 'Failed to generate literature review.');
    } finally {
      setLoading(false);
    }
  };

  return (
    <div className="glass" style={{ padding: '24px', borderRadius: 12 }}>
      <div style={{ display: 'flex', alignItems: 'center', gap: 12, marginBottom: 16 }}>
        <span style={{ fontSize: 24 }}>📝</span>
        <div>
          <h2 style={{ fontSize: 16, fontWeight: 600, color: '#e2e8f0', margin: 0 }}>Literature Review Draft Generator</h2>
          <p style={{ fontSize: 13, color: '#94a3b8', marginTop: 4 }}>
            Auto-generate a 3-paragraph synthesized literature review based on the clusters and seminal papers identified in this corpus.
          </p>
        </div>
      </div>

      {!reviewText && !loading && (
        <button
          onClick={handleGenerate}
          style={{
            padding: '10px 20px', borderRadius: 8, background: '#7c3aed', color: '#fff',
            border: 'none', cursor: 'pointer', fontWeight: 600, fontSize: 14,
            transition: 'background 0.2s',
          }}
          onMouseOver={e => (e.currentTarget.style.background = '#6d28d9')}
          onMouseOut={e => (e.currentTarget.style.background = '#7c3aed')}
        >
          ✨ Generate Literature Review
        </button>
      )}

      {loading && (
        <div style={{ display: 'flex', alignItems: 'center', gap: 12, color: '#a78bfa', fontSize: 14 }}>
          <div style={{ width: 16, height: 16, border: '2px solid rgba(167,139,250,0.3)', borderTopColor: '#a78bfa', borderRadius: '50%', animation: 'spin 1s linear infinite' }} />
          Synthesizing papers... This may take up to 30 seconds.
        </div>
      )}

      {error && <div style={{ color: '#ef4444', fontSize: 13, marginTop: 12 }}>{error}</div>}

      {reviewText && (
        <div style={{ marginTop: 20 }}>
          <div style={{ 
            background: 'rgba(15,22,41,0.6)', border: '1px solid #1e293b', 
            borderRadius: 8, padding: '20px', color: '#cbd5e1', fontSize: 14, 
            lineHeight: 1.8, whiteSpace: 'pre-wrap' 
          }}>
            {reviewText}
          </div>
          <button
            onClick={() => navigator.clipboard.writeText(reviewText)}
            style={{
              marginTop: 12, padding: '8px 16px', borderRadius: 6,
              background: 'rgba(100,116,139,0.1)', color: '#94a3b8',
              border: '1px solid rgba(100,116,139,0.2)', cursor: 'pointer', fontSize: 12,
            }}
          >
            📋 Copy to Clipboard
          </button>
        </div>
      )}
      <style>{`@keyframes spin { to { transform: rotate(360deg); } }`}</style>
    </div>
  );
}
