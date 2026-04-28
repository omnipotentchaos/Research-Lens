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
        setJob(prev => {
          if (!prev) return prev;
          const nextLogs = event.new_log ? [...(prev.logs || []), event.new_log] : (prev.logs || []);
          return { ...prev, ...event, logs: nextLogs };
        });
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
  if (job.status !== 'done' || !job.result) return <PipelineProgress job={job} />;

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
    <div className="bg-grid" style={{ minHeight: '100vh', display: 'flex', alignItems: 'center', justifyContent: 'center', padding: 24, position: 'relative', overflow: 'hidden' }}>
      {/* Ambient glow */}
      <div style={{ position: 'absolute', top: '50%', left: '50%', transform: 'translate(-50%, -50%)', width: 600, height: 600, borderRadius: '50%', background: 'radial-gradient(circle, rgba(124,58,237,0.15) 0%, transparent 60%)', filter: 'blur(40px)', pointerEvents: 'none', zIndex: 0 }} />
      
      <div className="glass animate-fadeUp" style={{ padding: 40, width: '100%', maxWidth: 600, position: 'relative', zIndex: 1, boxShadow: '0 25px 50px -12px rgba(0, 0, 0, 0.5)' }}>
        <div style={{ display: 'flex', alignItems: 'center', gap: 18, marginBottom: 32 }}>
          <div style={{ position: 'relative', width: 44, height: 44 }}>
            <div style={{ position: 'absolute', inset: 0, border: '3px solid rgba(124,58,237,0.2)', borderTopColor: '#7c3aed', borderRadius: '50%', animation: 'spin 1s cubic-bezier(0.55, 0.085, 0.68, 0.53) infinite' }} />
            <div style={{ position: 'absolute', inset: 6, border: '2px solid rgba(56,189,248,0.2)', borderBottomColor: '#38bdf8', borderRadius: '50%', animation: 'spin 1.5s cubic-bezier(0.25, 0.46, 0.45, 0.94) infinite reverse' }} />
          </div>
          <div>
            <div style={{ fontWeight: 700, color: '#f8fafc', fontSize: 18, letterSpacing: '-0.01em' }}>Analysing: <span className="gradient-text">{job.topic}</span></div>
            <div style={{ color: '#94a3b8', fontSize: 13, marginTop: 4, display: 'flex', alignItems: 'center', gap: 6 }}>
              <span style={{ display: 'inline-block', width: 8, height: 8, borderRadius: '50%', background: '#38bdf8', animation: 'pulse 2s infinite' }} /> 
              {job.current_step}
            </div>
          </div>
        </div>

        {/* Progress bar */}
        <div style={{ height: 6, borderRadius: 999, background: 'rgba(30,41,59,0.8)', marginBottom: 36, overflow: 'hidden', boxShadow: 'inset 0 1px 3px rgba(0,0,0,0.5)' }}>
          <div style={{ height: '100%', borderRadius: 999, background: 'linear-gradient(90deg, #7c3aed, #3b82f6, #34d399)', width: `${job.progress || 5}%`, transition: 'width 1s cubic-bezier(0.4, 0, 0.2, 1)', position: 'relative' }}>
            <div style={{ position: 'absolute', top: 0, left: 0, right: 0, bottom: 0, background: 'linear-gradient(90deg, transparent, rgba(255,255,255,0.4), transparent)', animation: 'shimmer 2s infinite' }} />
          </div>
        </div>

        {/* Step list */}
        <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(200px, 1fr))', gap: 16, marginBottom: 32 }}>
          {STEPS.map((s, i) => {
            const done = i < activeIdx;
            const active = i === activeIdx;
            return (
              <div key={s.label} style={{ display: 'flex', alignItems: 'center', gap: 12, padding: '12px 16px', borderRadius: 12, background: done ? 'rgba(16,185,129,0.05)' : active ? 'rgba(124,58,237,0.1)' : 'rgba(15,22,41,0.4)', border: '1px solid', borderColor: done ? 'rgba(16,185,129,0.2)' : active ? 'rgba(124,58,237,0.3)' : 'rgba(30,41,59,0.8)', transition: 'all 0.3s ease' }}>
                <div style={{ width: 24, height: 24, borderRadius: '50%', display: 'flex', alignItems: 'center', justifyContent: 'center', fontSize: 11, fontWeight: 700, flexShrink: 0, border: '1.5px solid', transition: 'all 0.4s', borderColor: done ? '#10b981' : active ? '#7c3aed' : '#334155', background: done ? '#10b981' : active ? 'rgba(124,58,237,0.2)' : 'transparent', color: done ? '#0f172a' : active ? '#c4b5fd' : '#475569', boxShadow: active ? '0 0 12px rgba(124,58,237,0.4)' : 'none' }}>
                  {done ? '✓' : i + 1}
                </div>
                <span style={{ fontSize: 13, fontWeight: active || done ? 500 : 400, color: done ? '#34d399' : active ? '#e2e8f0' : '#64748b' }}>
                  {s.label}
                </span>
                {active && <div style={{ marginLeft: 'auto', width: 6, height: 6, borderRadius: '50%', background: '#a78bfa', animation: 'pulse 1s ease-in-out infinite', boxShadow: '0 0 8px #a78bfa' }} />}
              </div>
            );
          })}
        </div>
        
        {/* Live Logs Terminal */}
        <div style={{ background: '#020617', border: '1px solid rgba(51,65,85,0.5)', borderRadius: 12, overflow: 'hidden', boxShadow: '0 10px 30px -10px rgba(0,0,0,0.5)' }}>
          {/* Terminal Header */}
          <div style={{ display: 'flex', alignItems: 'center', gap: 6, padding: '12px 16px', background: '#0f172a', borderBottom: '1px solid rgba(51,65,85,0.5)' }}>
            <div style={{ width: 10, height: 10, borderRadius: '50%', background: '#ef4444' }} />
            <div style={{ width: 10, height: 10, borderRadius: '50%', background: '#eab308' }} />
            <div style={{ width: 10, height: 10, borderRadius: '50%', background: '#22c55e' }} />
            <div style={{ marginLeft: 8, color: '#64748b', fontSize: 11, fontWeight: 600, letterSpacing: '0.05em', fontFamily: 'monospace' }}>pipeline.log</div>
          </div>
          {/* Terminal Output */}
          <div style={{ height: 200, padding: '16px', overflowY: 'auto', display: 'flex', flexDirection: 'column', gap: 8, fontFamily: '"JetBrains Mono", "Fira Code", monospace', fontSize: 12, color: '#94a3b8', scrollBehavior: 'smooth' }}>
            {job.logs?.map((log, i) => (
              <div key={i} style={{ display: 'flex', gap: 10, animation: 'fadeUp 0.3s ease-out' }}>
                <span style={{ color: '#38bdf8', opacity: 0.8 }}>❯</span>
                <span style={{ color: log.includes('✓') || log.includes('Kept') ? '#34d399' : log.includes('LLM') || log.includes('Generating') || log.includes('Title Mode') || log.includes('Topic Mode') ? '#c084fc' : '#e2e8f0', lineHeight: 1.5 }}>
                  {log}
                </span>
              </div>
            ))}
            {(!job.logs || job.logs.length === 0) && <div style={{ opacity: 0.5, fontStyle: 'italic', display: 'flex', gap: 10 }}><span style={{ color: '#38bdf8' }}>❯</span><span>Awaiting system initialization...</span></div>}
            {/* Blinking cursor */}
            <div style={{ display: 'flex', gap: 10 }}>
              <span style={{ color: '#38bdf8', opacity: 0.8 }}>❯</span>
              <span style={{ width: 8, height: 15, background: '#94a3b8', animation: 'blink 1s step-end infinite', marginTop: 2 }} />
            </div>
            {/* Empty element to scroll to bottom */}
            <div ref={(el) => { el?.scrollIntoView({ behavior: 'smooth' }) }} />
          </div>
        </div>
      </div>
      <style>{`
        @keyframes spin { to { transform: rotate(360deg); } }
        @keyframes pulse { 0%,100% { opacity:1; transform:scale(1); } 50% { opacity:0.4; transform:scale(0.8); } }
        @keyframes shimmer { 0% { transform: translateX(-100%); } 100% { transform: translateX(100%); } }
        @keyframes blink { 0%, 100% { opacity: 1; } 50% { opacity: 0; } }
      `}</style>
    </div>
  );
}
