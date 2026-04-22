'use client';

import { useState } from 'react';
import { useRouter } from 'next/navigation';
import { startResearch } from '@/lib/api';

const EXAMPLE_TOPICS = [
  'Retrieval-Augmented Generation in NLP',
  'Graph Neural Networks',
  'Large Language Model Alignment',
  'Diffusion Models for Image Generation',
  'Federated Learning Privacy',
];

const FEATURES = [
  { emoji: '📚', label: 'Smart Retrieval', desc: 'arXiv + OpenAlex across expanded query variants' },
  { emoji: '🔬', label: 'SPECTER2 Clustering', desc: 'Citation-aware embeddings + UMAP/HDBSCAN' },
  { emoji: '🕸️', label: 'Knowledge Graph', desc: 'Interactive graph of papers, methods & relations' },
  { emoji: '📈', label: 'Temporal Evolution', desc: 'Track method emergence & field drift over time' },
  { emoji: '✨', label: 'Research Gaps', desc: 'LLM-synthesised gaps from future-work analysis' },
  { emoji: '⚡', label: 'Fast & Cached', desc: 'Under 20s on repeat queries with smart caching' },
];

export default function HomePage() {
  const router = useRouter();
  const [topic, setTopic] = useState('');
  const [maxPapers, setMaxPapers] = useState(50);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState('');

  async function handleSearch(e: React.FormEvent) {
    e.preventDefault();
    if (!topic.trim() || loading) return;
    setLoading(true);
    setError('');
    try {
      const job = await startResearch(topic.trim(), maxPapers);
      router.push(`/results/${job.job_id}`);
    } catch (err: unknown) {
      const message = err instanceof Error ? err.message : 'Failed to start pipeline';
      setError(message);
      setLoading(false);
    }
  }

  return (
    <main style={{ minHeight: '100vh', background: '#080b14', position: 'relative', overflow: 'hidden' }} className="bg-grid">
      {/* Ambient glow orbs */}
      <div style={{ position: 'absolute', top: -200, left: -200, width: 600, height: 600, borderRadius: '50%', background: 'radial-gradient(circle, rgba(124,58,237,0.12) 0%, transparent 70%)', pointerEvents: 'none' }} />
      <div style={{ position: 'absolute', bottom: -200, right: -100, width: 500, height: 500, borderRadius: '50%', background: 'radial-gradient(circle, rgba(37,99,235,0.08) 0%, transparent 70%)', pointerEvents: 'none' }} />

      <div style={{ maxWidth: 900, margin: '0 auto', padding: '64px 24px', display: 'flex', flexDirection: 'column', alignItems: 'center', position: 'relative' }}>

        {/* Badge */}
        <div style={{ display: 'flex', alignItems: 'center', gap: 8, padding: '6px 16px', borderRadius: 999, border: '1px solid rgba(124,58,237,0.35)', background: 'rgba(124,58,237,0.1)', color: '#c4b5fd', fontSize: 13, fontWeight: 500, marginBottom: 32 }}>
          ✨ AI-Powered Research Intelligence
        </div>

        {/* Hero */}
        <h1 style={{ fontSize: 'clamp(2.5rem, 7vw, 4.5rem)', fontWeight: 800, textAlign: 'center', lineHeight: 1.15, marginBottom: 20 }}>
          <span className="gradient-text">Map Any Research</span>
          <br />
          <span style={{ color: '#e2e8f0' }}>Field in Minutes</span>
        </h1>
        <p style={{ color: '#64748b', textAlign: 'center', fontSize: 17, maxWidth: 600, marginBottom: 48, lineHeight: 1.7 }}>
          Enter any research topic. ResearchLens automatically retrieves papers,
          clusters them into research directions, tracks their evolution over time,
          and surfaces unexplored gaps — powered by SPECTER2 + LLM analysis.
        </p>

        {/* Search form */}
        <form onSubmit={handleSearch} style={{ width: '100%', maxWidth: 680 }}>
          <div className="glass" style={{ padding: 6, display: 'flex', gap: 8, marginBottom: 12, animation: 'glowPulse 3s ease-in-out infinite' }}>
            <div style={{ flex: 1, display: 'flex', alignItems: 'center', gap: 12, padding: '0 16px' }}>
              <span style={{ color: '#7c3aed', fontSize: 18 }}>🔍</span>
              <input
                id="topic-input"
                type="text"
                value={topic}
                onChange={e => setTopic(e.target.value)}
                placeholder="e.g. Retrieval-Augmented Generation in NLP"
                className="input-glow"
                style={{ flex: 1, background: 'transparent', color: '#f1f5f9', border: 'none', fontSize: 15, padding: '12px 0', fontFamily: 'inherit' }}
              />
            </div>
            <button
              id="search-btn"
              type="submit"
              disabled={!topic.trim() || loading}
              style={{
                padding: '12px 24px', borderRadius: 12, background: loading || !topic.trim() ? '#4c1d95' : '#7c3aed',
                color: '#fff', fontWeight: 600, fontSize: 14, border: 'none', cursor: loading || !topic.trim() ? 'not-allowed' : 'pointer',
                opacity: !topic.trim() ? 0.5 : 1, display: 'flex', alignItems: 'center', gap: 8, transition: 'background 0.2s', whiteSpace: 'nowrap',
              }}
            >
              {loading ? <>
                <span style={{ display: 'inline-block', width: 14, height: 14, border: '2px solid rgba(255,255,255,0.3)', borderTopColor: '#fff', borderRadius: '50%', animation: 'spin 0.8s linear infinite' }} />
                Starting…
              </> : <>Analyse →</>}
            </button>
          </div>

          {/* Slider */}
          <div style={{ display: 'flex', alignItems: 'center', gap: 12, padding: '0 4px' }}>
            <span style={{ color: '#475569', fontSize: 13, whiteSpace: 'nowrap' }}>Papers: {maxPapers}</span>
            <input type="range" min={10} max={100} step={10} value={maxPapers} onChange={e => setMaxPapers(Number(e.target.value))}
              style={{ flex: 1, accentColor: '#7c3aed' }} />
            <span style={{ color: '#475569', fontSize: 13 }}>100</span>
          </div>

          {error && <p style={{ color: '#f87171', fontSize: 13, marginTop: 10, textAlign: 'center' }}>{error}</p>}
        </form>

        {/* Example topics */}
        <div style={{ display: 'flex', flexWrap: 'wrap', gap: 8, marginTop: 20, justifyContent: 'center' }}>
          {EXAMPLE_TOPICS.map(t => (
            <button key={t} onClick={() => setTopic(t)}
              style={{ padding: '6px 14px', borderRadius: 10, border: '1px solid #1e293b', background: 'rgba(30,41,59,0.5)', color: '#64748b', fontSize: 13, cursor: 'pointer', transition: 'all 0.2s', fontFamily: 'inherit' }}
              onMouseEnter={e => { (e.target as HTMLElement).style.borderColor = 'rgba(124,58,237,0.5)'; (e.target as HTMLElement).style.color = '#c4b5fd'; }}
              onMouseLeave={e => { (e.target as HTMLElement).style.borderColor = '#1e293b'; (e.target as HTMLElement).style.color = '#64748b'; }}
            >
              {t}
            </button>
          ))}
        </div>

        {/* Feature grid */}
        <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(240px, 1fr))', gap: 16, marginTop: 80, width: '100%' }}>
          {FEATURES.map(({ emoji, label, desc }) => (
            <div key={label} className="glass" style={{ padding: 20, transition: 'border-color 0.2s' }}
              onMouseEnter={e => (e.currentTarget.style.borderColor = 'rgba(124,58,237,0.4)')}
              onMouseLeave={e => (e.currentTarget.style.borderColor = 'rgba(139,92,246,0.18)')}
            >
              <div style={{ width: 40, height: 40, borderRadius: 12, background: 'rgba(124,58,237,0.15)', display: 'flex', alignItems: 'center', justifyContent: 'center', fontSize: 20, marginBottom: 12 }}>{emoji}</div>
              <div style={{ fontWeight: 600, color: '#e2e8f0', marginBottom: 4 }}>{label}</div>
              <div style={{ color: '#475569', fontSize: 13 }}>{desc}</div>
            </div>
          ))}
        </div>

      </div>

      <style>{`
        @keyframes spin { to { transform: rotate(360deg); } }
      `}</style>
    </main>
  );
}
