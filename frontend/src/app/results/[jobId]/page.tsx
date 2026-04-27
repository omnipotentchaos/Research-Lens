'use client';

import { useEffect, useState, useRef } from 'react';
import { useParams, useRouter } from 'next/navigation';
import { pollStatus, getWsProgressUrl } from '@/lib/api';
import { JobStatus, PipelineResult, Cluster } from '@/lib/types';
import ClusterPlot from '@/components/ClusterPlot';
import TimelineChart from '@/components/TimelineChart';
import GapCards from '@/components/GapCards';
import TopPapers from '@/components/TopPapers';
import StatCard from '@/components/StatCard';

const STEPS = [
  { label: 'Retrieving papers',      match: 'retrieving' },
  { label: 'Extracting information', match: 'extracting' },
  { label: 'Embedding + Clustering', match: 'embedding' },
  { label: 'Temporal analysis',      match: 'temporal' },
  { label: 'Detecting research gaps',  match: 'detecting' },
];

const TABS = [
  { id: 'clusters', label: '🗺 Cluster Map' },
  { id: 'timeline', label: '📈 Timeline' },
  { id: 'gaps',     label: '✨ Research Gaps' },
  { id: 'graph',    label: '📄 Papers' },
] as const;

type TabId = typeof TABS[number]['id'];

const S = {
  page: { minHeight: '100vh', background: '#080b14', color: '#f1f5f9', fontFamily: 'var(--font-inter), system-ui, sans-serif' } as React.CSSProperties,
  header: { position: 'sticky', top: 0, zIndex: 50, borderBottom: '1px solid rgba(124,58,237,0.15)', background: 'rgba(8,11,20,0.85)', backdropFilter: 'blur(20px)', padding: '0 24px', height: 60, display: 'flex', alignItems: 'center', gap: 16 } as React.CSSProperties,
  content: { maxWidth: 1280, margin: '0 auto', padding: '32px 24px' } as React.CSSProperties,
  statGrid: { display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(160px, 1fr))', gap: 16, marginBottom: 28 } as React.CSSProperties,
  tabBar: { display: 'flex', gap: 4, padding: 4, borderRadius: 14, background: 'rgba(15,22,41,0.7)', border: '1px solid #1e293b', marginBottom: 24, overflowX: 'auto' as const },
};

export default function ResultsPage() {
  const { jobId } = useParams<{ jobId: string }>();
  const router = useRouter();
  const [job, setJob] = useState<JobStatus | null>(null);
  const [activeTab, setActiveTab] = useState<TabId>('clusters');
  // Track which tabs have been visited — show skeleton on first visit
  const [mountedTabs, setMountedTabs] = useState<Set<TabId>>(new Set(['clusters']));

  function handleTabClick(id: TabId) {
    setActiveTab(id);
    setMountedTabs(prev => new Set([...prev, id]));
  }

  // --- WebSocket progress streaming (with polling fallback) ---
  useEffect(() => {
    if (!jobId) return;
    let cancelled = false;
    let ws: WebSocket | null = null;
    let fallbackPoll: ReturnType<typeof setInterval> | null = null;

    // Fetch initial state via REST
    pollStatus(jobId as string).then(status => {
      if (!cancelled) setJob(status);
    });

    // Try WebSocket first
    try {
      ws = new WebSocket(getWsProgressUrl(jobId as string));
      ws.onmessage = (evt) => {
        const event = JSON.parse(evt.data);
        setJob(prev => prev ? { ...prev, ...event } : prev);
        if (event.status === 'done' || event.status === 'error') {
          // Fetch full result via REST (WS only sends progress, not full result)
          pollStatus(jobId as string).then(status => {
            if (!cancelled) setJob(status);
          });
        }
      };
      ws.onerror = () => {
        // WebSocket failed — fall back to polling
        ws?.close();
        ws = null;
        if (!fallbackPoll) {
          fallbackPoll = setInterval(async () => {
            const status = await pollStatus(jobId as string);
            if (!cancelled) setJob(status);
            if (status.status === 'done' || status.status === 'error') {
              if (fallbackPoll) clearInterval(fallbackPoll);
            }
          }, 2500);
        }
      };
    } catch {
      // WebSocket not available — use polling
      fallbackPoll = setInterval(async () => {
        const status = await pollStatus(jobId as string);
        if (!cancelled) setJob(status);
        if (status.status === 'done' || status.status === 'error') {
          if (fallbackPoll) clearInterval(fallbackPoll);
        }
      }, 2500);
    }

    return () => {
      cancelled = true;
      ws?.close();
      if (fallbackPoll) clearInterval(fallbackPoll);
    };
  }, [jobId]);

  if (!job) return <CenteredSpinner message="Connecting…" />;
  if (job.status === 'error') return <ErrorScreen error={job.error ?? 'Unknown error'} onBack={() => router.push('/')} />;
  if (job.status !== 'done') return <PipelineProgress job={job} />;

  const result = job.result as PipelineResult;
  const clusters: Cluster[] = Object.values(result.clusters || {}).filter(c => !c.is_noise);

  const statCards = [
    { icon: '📄', label: 'Papers',         value: result.metadata.paper_count,                    color: '#7c3aed', subtext: `${result.metadata.year_range?.[0]}–${result.metadata.year_range?.[1]}` },
    { icon: '🗂️', label: 'Clusters',       value: result.metadata.cluster_count,                  color: '#2563eb', subtext: 'research themes' },
    { icon: '✨',  label: 'Research Gaps', value: result.gaps?.synthesized_gaps?.length ?? 0,     color: '#059669', subtext: `${result.metadata.pipeline_time_seconds?.toFixed(1)}s pipeline` },
    { icon: '📊', label: 'Silhouette',     value: result.clustering_metrics?.silhouette != null ? result.clustering_metrics.silhouette.toFixed(3) : 'N/A',  color: '#0891b2', subtext: 'higher = better (-1 to 1)' },
    { icon: '📏', label: 'Davies-Bouldin', value: result.clustering_metrics?.davies_bouldin != null ? result.clustering_metrics.davies_bouldin.toFixed(3) : 'N/A', color: '#d97706', subtext: 'lower = tighter clusters' },
  ];

  return (
    <div style={S.page}>
      {/* Ambient glow */}
      <div style={{ position: 'fixed', top: 0, left: 0, width: 500, height: 500, borderRadius: '50%', background: 'radial-gradient(circle, rgba(124,58,237,0.07) 0%, transparent 70%)', pointerEvents: 'none', zIndex: 0 }} />

      {/* Header */}
      <header style={S.header}>
        <button id="back-btn" onClick={() => router.push('/')} style={{ color: '#64748b', background: 'none', border: 'none', cursor: 'pointer', fontSize: 20, padding: 4, lineHeight: 1 }}>←</button>
        <div style={{ width: 1, height: 24, background: '#1e293b' }} />
        <div>
          <div style={{ color: '#7c3aed', fontSize: 11, fontWeight: 600, textTransform: 'uppercase', letterSpacing: '0.1em' }}>Research Topic</div>
          <div style={{ fontWeight: 700, color: '#f1f5f9', fontSize: 15 }}>{result.topic}</div>
        </div>
        <div style={{ marginLeft: 'auto', color: '#475569', fontSize: 12 }}>
          ⏱ {result.metadata.pipeline_time_seconds.toFixed(1)}s
        </div>
      </header>

      <div style={{ ...S.content, position: 'relative', zIndex: 1 }}>
        {/* Stat row */}
        <div style={S.statGrid}>
          {statCards.map(c => (
            <StatCard key={c.label} icon={c.icon} label={c.label} value={c.value} color={c.color} subtext={c.subtext} />
          ))}
        </div>

        {/* Tab bar */}
        <div style={S.tabBar}>
          {TABS.map(({ id, label }) => (
            <button
              key={id}
              id={`tab-${id}`}
              onClick={() => handleTabClick(id)}
              style={{
                flex: 1, padding: '9px 16px', borderRadius: 10, fontSize: 13, fontWeight: 500, border: 'none', cursor: 'pointer', transition: 'all 0.2s', whiteSpace: 'nowrap', fontFamily: 'inherit',
                background: activeTab === id ? '#7c3aed' : 'transparent',
                color: activeTab === id ? '#fff' : '#64748b',
                boxShadow: activeTab === id ? '0 4px 15px rgba(124,58,237,0.35)' : 'none',
              }}
            >
              {label}
            </button>
          ))}
        </div>

        {/* Tab content — skeleton shows on first visit to each tab */}
        <div className="animate-fadeUp">
          {activeTab === 'clusters' && (
            mountedTabs.has('clusters')
              ? <ClusterPlot result={result} clusters={clusters} />
              : <TabSkeleton />
          )}
          {activeTab === 'timeline' && (
            mountedTabs.has('timeline')
              ? <TimelineChart temporal={result.temporal} />
              : <TabSkeleton />
          )}
          {activeTab === 'gaps' && (
            mountedTabs.has('gaps')
              ? <GapCards gaps={result.gaps?.synthesized_gaps ?? []} />
              : <TabSkeleton />
          )}
          {activeTab === 'graph' && (
            mountedTabs.has('graph')
              ? <TopPapers papers={result.papers} clusters={clusters} />
              : <TabSkeleton />
          )}
        </div>
      </div>
    </div>
  );
}

function TabSkeleton() {
  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: 12 }}>
      <style>{`@keyframes shimmer { 0% { background-position: 200% 0; } 100% { background-position: -200% 0; } }`}</style>
      {[300, 180, 240, 200].map((w, i) => (
        <div key={i} style={{
          height: i === 0 ? 240 : 80, borderRadius: 14,
          background: 'linear-gradient(90deg, rgba(30,41,59,0.6) 25%, rgba(51,65,85,0.35) 50%, rgba(30,41,59,0.6) 75%)',
          backgroundSize: '200% 100%',
          animation: `shimmer 1.4s ease-in-out ${i * 0.12}s infinite`,
        }} />
      ))}
    </div>
  );
}

function CenteredSpinner({ message }: { message: string }) {
  return (
    <div style={{ minHeight: '100vh', background: '#080b14', display: 'flex', alignItems: 'center', justifyContent: 'center', flexDirection: 'column', gap: 16 }}>
      <div style={{ width: 40, height: 40, border: '3px solid rgba(124,58,237,0.2)', borderTopColor: '#7c3aed', borderRadius: '50%', animation: 'spin 0.8s linear infinite' }} />
      <p style={{ color: '#475569', fontFamily: 'system-ui' }}>{message}</p>
      <style>{`@keyframes spin { to { transform: rotate(360deg); } }`}</style>
    </div>
  );
}

function ErrorScreen({ error, onBack }: { error: string; onBack: () => void }) {
  return (
    <div style={{ minHeight: '100vh', background: '#080b14', display: 'flex', alignItems: 'center', justifyContent: 'center' }}>
      <div className="glass" style={{ padding: 40, textAlign: 'center', maxWidth: 440 }}>
        <div style={{ fontSize: 48, marginBottom: 16 }}>⚠️</div>
        <h2 style={{ color: '#f87171', marginBottom: 8, fontFamily: 'system-ui' }}>Pipeline Failed</h2>
        <p style={{ color: '#475569', fontSize: 14, marginBottom: 24, fontFamily: 'system-ui' }}>{error}</p>
        <button onClick={onBack} style={{ padding: '10px 24px', borderRadius: 10, background: '#7c3aed', color: '#fff', border: 'none', cursor: 'pointer', fontFamily: 'system-ui', fontSize: 14 }}>
          Try Again
        </button>
      </div>
    </div>
  );
}

function PipelineProgress({ job }: { job: JobStatus }) {
  const step = job.current_step?.toLowerCase() ?? '';
  const idx = STEPS.findIndex(s => step.includes(s.match)) ?? 0;
  const activeIdx = idx < 0 ? 0 : idx;

  return (
    <div style={{ minHeight: '100vh', background: '#080b14', display: 'flex', alignItems: 'center', justifyContent: 'center', padding: 24 }}>
      <div className="glass" style={{ padding: 40, width: '100%', maxWidth: 500 }}>
        <div style={{ display: 'flex', alignItems: 'center', gap: 14, marginBottom: 28 }}>
          <div style={{ width: 36, height: 36, border: '3px solid rgba(124,58,237,0.2)', borderTopColor: '#7c3aed', borderRadius: '50%', animation: 'spin 0.8s linear infinite', flexShrink: 0 }} />
          <div>
            <div style={{ fontWeight: 700, color: '#f1f5f9', fontSize: 15 }}>Analysing: <span style={{ color: '#a78bfa' }}>{job.topic}</span></div>
            <div style={{ color: '#64748b', fontSize: 13, marginTop: 3 }}>{job.current_step}</div>
          </div>
        </div>

        {/* Progress bar */}
        <div style={{ height: 5, borderRadius: 999, background: '#1e293b', marginBottom: 32, overflow: 'hidden' }}>
          <div style={{ height: '100%', borderRadius: 999, background: 'linear-gradient(90deg, #7c3aed, #2563eb)', width: `${job.progress || 5}%`, transition: 'width 1s ease' }} />
        </div>

        {/* Step list */}
        <div style={{ display: 'flex', flexDirection: 'column', gap: 12 }}>
          {STEPS.map((s, i) => {
            const done = i < activeIdx;
            const active = i === activeIdx;
            return (
              <div key={s.label} style={{ display: 'flex', alignItems: 'center', gap: 14 }}>
                <div style={{
                  width: 30, height: 30, borderRadius: '50%', display: 'flex', alignItems: 'center', justifyContent: 'center', fontSize: 12, fontWeight: 700, flexShrink: 0, border: '1.5px solid', transition: 'all 0.4s',
                  borderColor: done ? '#10b981' : active ? '#7c3aed' : '#1e293b',
                  background: done ? 'rgba(16,185,129,0.15)' : active ? 'rgba(124,58,237,0.2)' : 'rgba(15,22,41,0.6)',
                  color: done ? '#10b981' : active ? '#a78bfa' : '#334155',
                  boxShadow: active ? '0 0 12px rgba(124,58,237,0.4)' : 'none',
                }}>
                  {done ? '✓' : i + 1}
                </div>
                <span style={{ fontSize: 14, fontWeight: active ? 600 : 400, transition: 'color 0.4s', color: done ? '#10b981' : active ? '#a78bfa' : '#334155' }}>
                  {s.label}
                </span>
                {active && <div style={{ marginLeft: 'auto', width: 6, height: 6, borderRadius: '50%', background: '#7c3aed', animation: 'pulse 1.2s ease-in-out infinite' }} />}
              </div>
            );
          })}
        </div>
      </div>
      <style>{`
        @keyframes spin { to { transform: rotate(360deg); } }
        @keyframes pulse { 0%,100% { opacity:1; transform:scale(1); } 50% { opacity:0.4; transform:scale(0.7); } }
        @keyframes shimmer { 0% { background-position: 200% 0; } 100% { background-position: -200% 0; } }
      `}</style>
    </div>
  );
}
