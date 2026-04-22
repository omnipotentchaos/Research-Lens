'use client';

import { useMemo, useState } from 'react';
import { Paper, Cluster } from '@/lib/types';

interface Props { papers: Paper[]; clusters: Cluster[]; }

const CLUSTER_COLORS = [
  '#7c3aed', '#2563eb', '#0891b2', '#059669',
  '#d97706', '#dc2626', '#a21caf', '#0d9488',
];

export default function MethodHeatmap({ papers, clusters }: Props) {
  const [hovered, setHovered] = useState<{ ci: number; mi: number } | null>(null);

  const sortedClusters = useMemo(
    () => [...clusters].sort((a, b) => a.cluster_id - b.cluster_id),
    [clusters],
  );

  const { methods, matrix, barData } = useMemo(() => {
    const globalCounts: Record<string, number> = {};
    const clusterCounts: Record<number, Record<string, number>> = {};

    for (const p of papers) {
      const cid = Number(p.cluster_id);
      if (cid === -1) continue;
      if (!clusterCounts[cid]) clusterCounts[cid] = {};

      // Prefer ner_models array; fall back to single method string
      const methods: string[] = p.ner_models?.length
        ? p.ner_models
        : p.method ? [p.method] : [];

      for (const raw of methods) {
        const m = raw.trim();
        if (m.length < 2 || m.length > 50) continue;
        clusterCounts[cid][m] = (clusterCounts[cid][m] || 0) + 1;
        globalCounts[m] = (globalCounts[m] || 0) + 1;
      }
    }

    // Top 12 methods for heatmap columns
    const methods = Object.entries(globalCounts)
      .sort((a, b) => b[1] - a[1])
      .slice(0, 12)
      .map(([m]) => m);

    // Matrix: rows = sorted clusters, cols = top methods
    const matrix = sortedClusters.map(c =>
      methods.map(m => clusterCounts[c.cluster_id]?.[m] || 0),
    );

    // Top 10 for bar chart
    const barData = Object.entries(globalCounts)
      .sort((a, b) => b[1] - a[1])
      .slice(0, 10);

    return { methods, matrix, barData };
  }, [papers, sortedClusters]);

  const maxVal = Math.max(...matrix.flat(), 1);

  const cellBg = (val: number) => {
    if (val === 0) return 'rgba(15,22,41,0.6)';
    const t = val / maxVal;
    // dark navy → vivid violet
    const r = Math.round(15 + t * (139 - 15));
    const g = Math.round(22 + t * (92 - 22));
    const b = Math.round(41 + t * (246 - 41));
    return `rgba(${r},${g},${b},${0.2 + t * 0.8})`;
  };

  if (methods.length === 0) {
    return (
      <div className="glass" style={{ padding: 40, textAlign: 'center', color: '#475569' }}>
        <div style={{ fontSize: 32, marginBottom: 12 }}>🔍</div>
        <div>No method data extracted yet. Run a fresh topic to see the landscape.</div>
      </div>
    );
  }

  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: 20 }}>

      {/* Header banner */}
      <div className="glass" style={{ padding: '14px 20px', borderLeft: '3px solid #7c3aed', display: 'flex', alignItems: 'flex-start', gap: 12 }}>
        <span style={{ fontSize: 22, flexShrink: 0 }}>🔥</span>
        <div>
          <div style={{ fontSize: 13, fontWeight: 700, color: '#a78bfa', marginBottom: 4 }}>Method Landscape</div>
          <div style={{ fontSize: 12, color: '#64748b', lineHeight: 1.7 }}>
            Each cell shows how many papers in a research cluster use a given method or technique.{' '}
            <strong style={{ color: '#94a3b8' }}>Brighter = more papers rely on it.</strong>{' '}
            Spot which techniques dominate each research direction and which methods cross cluster boundaries.
          </div>
        </div>
      </div>

      {/* Heatmap */}
      <div className="glass" style={{ padding: '24px 20px', overflowX: 'auto' }}>
        <div style={{ minWidth: 640 }}>

          {/* Column headers (method names, angled) */}
          <div style={{ display: 'flex', marginLeft: 190 }}>
            {methods.map((m, mi) => (
              <div key={m} style={{
                flex: 1, display: 'flex', alignItems: 'flex-end', justifyContent: 'center',
                height: 72, paddingBottom: 6,
              }}>
                <span style={{
                  display: 'block', fontSize: 10, fontWeight: hovered?.mi === mi ? 700 : 400,
                  color: hovered?.mi === mi ? '#c4b5fd' : '#475569',
                  transform: 'rotate(-40deg)', transformOrigin: 'bottom center',
                  whiteSpace: 'nowrap', maxWidth: 80, overflow: 'hidden', textOverflow: 'ellipsis',
                  transition: 'color 0.15s',
                }}>
                  {m.length > 14 ? m.slice(0, 14) + '…' : m}
                </span>
              </div>
            ))}
          </div>

          {/* Rows */}
          {sortedClusters.map((cluster, ci) => {
            const color = CLUSTER_COLORS[cluster.cluster_id % CLUSTER_COLORS.length];
            return (
              <div key={cluster.cluster_id} style={{ display: 'flex', alignItems: 'center', marginBottom: 5 }}>
                {/* Cluster label */}
                <div style={{
                  width: 185, flexShrink: 0, paddingRight: 12, textAlign: 'right',
                  fontSize: 11, fontWeight: 500,
                  color: hovered?.ci === ci ? '#e2e8f0' : '#64748b',
                  whiteSpace: 'nowrap', overflow: 'hidden', textOverflow: 'ellipsis',
                  transition: 'color 0.15s',
                  borderRight: `2px solid ${color}40`,
                }}>
                  <span style={{ display: 'inline-block', width: 6, height: 6, borderRadius: '50%', background: color, marginRight: 5, verticalAlign: 'middle' }} />
                  {cluster.label}
                </div>

                {/* Cells */}
                {matrix[ci].map((val, mi) => {
                  const isHov = hovered?.ci === ci && hovered?.mi === mi;
                  return (
                    <div
                      key={mi}
                      onMouseEnter={() => setHovered({ ci, mi })}
                      onMouseLeave={() => setHovered(null)}
                      title={`${cluster.label} × ${methods[mi]}: ${val} paper${val !== 1 ? 's' : ''}`}
                      style={{
                        flex: 1, height: 38, margin: '0 2px', borderRadius: 5,
                        background: cellBg(val),
                        border: `1px solid rgba(124,58,237,${val > 0 ? 0.35 : 0.08})`,
                        display: 'flex', alignItems: 'center', justifyContent: 'center',
                        fontSize: 11, fontWeight: 700,
                        color: val === 0 ? 'transparent' : val / maxVal > 0.5 ? '#fff' : '#c4b5fd',
                        cursor: 'default',
                        outline: isHov ? '2px solid #7c3aed' : '2px solid transparent',
                        transform: isHov ? 'scale(1.08)' : 'scale(1)',
                        transition: 'all 0.12s',
                        boxShadow: isHov ? '0 0 12px rgba(124,58,237,0.5)' : 'none',
                      }}
                    >
                      {val > 0 ? val : ''}
                    </div>
                  );
                })}
              </div>
            );
          })}

          {/* Colour scale legend */}
          <div style={{ display: 'flex', alignItems: 'center', gap: 10, marginTop: 16, marginLeft: 190, justifyContent: 'flex-end' }}>
            <span style={{ fontSize: 10, color: '#334155' }}>0</span>
            <div style={{ width: 120, height: 8, borderRadius: 4, background: 'linear-gradient(90deg, rgba(15,22,41,0.6), rgba(139,92,246,1))' }} />
            <span style={{ fontSize: 10, color: '#a78bfa' }}>{maxVal} papers</span>
          </div>
        </div>

        {/* Hover tooltip */}
        {hovered && (
          <div style={{
            marginTop: 16, padding: '10px 18px', borderRadius: 10,
            background: 'rgba(124,58,237,0.12)', border: '1px solid rgba(124,58,237,0.3)',
            fontSize: 13, display: 'flex', alignItems: 'center', gap: 8, flexWrap: 'wrap',
          }}>
            <span style={{ color: '#a78bfa', fontWeight: 600 }}>{methods[hovered.mi]}</span>
            <span style={{ color: '#334155' }}>in</span>
            <span style={{ color: '#94a3b8' }}>{sortedClusters[hovered.ci]?.label}</span>
            <span style={{ color: '#334155' }}>→</span>
            <span style={{ color: '#fff', fontWeight: 700, fontSize: 15 }}>
              {matrix[hovered.ci][hovered.mi]} paper{matrix[hovered.ci][hovered.mi] !== 1 ? 's' : ''}
            </span>
          </div>
        )}
      </div>

      {/* Top Methods Bar Chart */}
      <div className="glass" style={{ padding: '20px 24px' }}>
        <div style={{ fontSize: 11, fontWeight: 700, color: '#475569', textTransform: 'uppercase', letterSpacing: '0.1em', marginBottom: 16 }}>
          Most-Used Methods Across All Clusters
        </div>
        <div style={{ display: 'flex', flexDirection: 'column', gap: 9 }}>
          {barData.map(([method, count], i) => {
            const pct = (count / barData[0][1]) * 100;
            const color = CLUSTER_COLORS[i % CLUSTER_COLORS.length];
            return (
              <div key={method} style={{ display: 'flex', alignItems: 'center', gap: 12 }}>
                <div style={{ width: 150, fontSize: 11, color: '#94a3b8', textAlign: 'right', flexShrink: 0, overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>
                  {method}
                </div>
                <div style={{ flex: 1, height: 22, background: 'rgba(15,22,41,0.8)', borderRadius: 5, overflow: 'hidden', position: 'relative' }}>
                  <div style={{
                    height: '100%', width: `${pct}%`, borderRadius: 5,
                    background: `linear-gradient(90deg, ${color}, ${color}aa)`,
                    transition: 'width 0.7s cubic-bezier(0.4,0,0.2,1)',
                    display: 'flex', alignItems: 'center', paddingLeft: 10,
                  }}>
                    <span style={{ fontSize: 10, color: '#fff', fontWeight: 700 }}>{count}</span>
                  </div>
                </div>
                <div style={{ fontSize: 10, color: '#334155', width: 28, textAlign: 'right' }}>
                  {Math.round(pct)}%
                </div>
              </div>
            );
          })}
        </div>
      </div>

    </div>
  );
}
