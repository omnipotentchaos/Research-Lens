'use client';

import dynamic from 'next/dynamic';
import { useState, useMemo } from 'react';
import { PipelineResult, Cluster, Paper, GeometricGap } from '@/lib/types';

const Plot = dynamic(() => import('react-plotly.js'), { ssr: false });

const CLUSTER_COLORS = [
  '#7c3aed', '#2563eb', '#0891b2', '#059669',
  '#d97706', '#dc2626', '#a21caf', '#0d9488',
  '#b45309', '#be185d',
];

interface Props { result: PipelineResult; clusters: Cluster[]; }

export default function ClusterPlot({ result, clusters }: Props) {
  const [selected, setSelected] = useState<Paper | null>(null);
  const showHeatmap = false;
  const showGaps = false;

  const papers = result.papers || [];
  const points = result.reduced_2d || [];
  const labels = result.labels || [];
  const geometricGaps: GeometricGap[] = (result.gaps?.geometric_gaps as GeometricGap[]) || [];

  const allNoise = clusters.length === 0;
  const noiseCount = labels.filter(l => l === -1).length;

  // --- Build cluster scatter traces ---
  const clusterGroups: Record<number, { x: number[], y: number[], text: string[], papers: Paper[] }> = {};
  papers.forEach((paper, i) => {
    const cid = labels[i] ?? -1;
    if (!clusterGroups[cid]) clusterGroups[cid] = { x: [], y: [], text: [], papers: [] };
    clusterGroups[cid].x.push(points[i]?.[0] ?? 0);
    clusterGroups[cid].y.push(points[i]?.[1] ?? 0);
    clusterGroups[cid].text.push(paper.title);
    clusterGroups[cid].papers.push(paper);
  });

  const scatterTraces = Object.entries(clusterGroups).map(([cidStr, data]) => {
    const cid = Number(cidStr);
    const cluster = clusters.find(c => c.cluster_id === cid);
    const isNoise = cid === -1;
    const color = isNoise ? '#374151' : CLUSTER_COLORS[cid % CLUSTER_COLORS.length];
    return {
      type: 'scatter' as const,
      mode: 'markers' as const,
      name: isNoise ? 'Unclustered' : (cluster?.label ?? `Cluster ${cid}`),
      x: data.x, y: data.y,
      text: data.text,
      hovertemplate: '<b>%{text}</b><extra></extra>',
      marker: { size: 11, color, opacity: isNoise ? 0.35 : 0.9, line: { color: 'rgba(255,255,255,0.2)', width: 1.5 } },
      customdata: data.papers,
    };
  });

  // --- KDE density heatmap trace (shows where papers are dense / sparse) ---
  const heatmapTrace = useMemo(() => {
    if (!showHeatmap || points.length < 5) return null;
    const xs = points.map(p => p[0]);
    const ys = points.map(p => p[1]);
    return {
      type: 'histogram2dcontour' as const,
      x: xs, y: ys,
      ncontours: 20,
      showscale: false,
      contours: { coloring: 'fill' as const },
      colorscale: [
        [0, 'rgba(0,0,0,0)'],
        [0.15, 'rgba(124,58,237,0.03)'],
        [0.3, 'rgba(124,58,237,0.06)'],
        [0.5, 'rgba(37,99,235,0.09)'],
        [0.7, 'rgba(8,145,178,0.12)'],
        [1, 'rgba(5,150,105,0.18)'],
      ],
      hoverinfo: 'skip' as const,
      name: 'Paper density',
      showlegend: false,
    };
  }, [points, showHeatmap]);

  // --- Geometric gap markers (✕ at low-density voids between clusters) ---
  const gapTrace = useMemo(() => {
    if (!showGaps || geometricGaps.length === 0) return null;
    return {
      type: 'scatter' as const,
      mode: 'markers+text' as const,
      name: '⚠ Research Gaps',
      x: geometricGaps.map(g => g.position_2d[0]),
      y: geometricGaps.map(g => g.position_2d[1]),
      text: geometricGaps.map((_, i) => `G${i + 1}`),
      textposition: 'top center' as const,
      textfont: { color: '#fbbf24', size: 10, family: 'Inter, system-ui' },
      hovertemplate: geometricGaps.map(
        g => `<b>Research Gap</b><br>${g.description}<extra></extra>`
      ),
      marker: {
        size: 16,
        symbol: 'x',
        color: '#fbbf24',
        opacity: 0.85,
        line: { color: '#f59e0b', width: 2 },
      },
    };
  }, [geometricGaps, showGaps]);

  // Assemble all traces
  const traces: any[] = [];
  if (heatmapTrace) traces.push(heatmapTrace);
  traces.push(...scatterTraces);
  if (gapTrace) traces.push(gapTrace);

  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: 16 }}>

      {/* Explainer banner */}
      <div className="glass" style={{ padding: '12px 18px', display: 'flex', alignItems: 'flex-start', gap: 12, borderLeft: '3px solid #7c3aed' }}>
        <span style={{ fontSize: 20, flexShrink: 0 }}>🗺️</span>
        <div>
          <div style={{ fontSize: 13, fontWeight: 600, color: '#c4b5fd', marginBottom: 3 }}>How to read this map</div>
          <div style={{ fontSize: 12, color: '#64748b', lineHeight: 1.6 }}>
            Each dot = one paper. Papers with similar methods/topics are placed <strong style={{ color: '#94a3b8' }}>close together</strong> by UMAP.
            Dots of the <strong style={{ color: '#94a3b8' }}>same colour</strong> belong to the same cluster (HDBSCAN).
          </div>
        </div>
      </div>

      <div style={{ display: 'grid', gridTemplateColumns: '1fr 300px', gap: 16 }}>
        {/* Plot */}
        <div className="glass" style={{ height: 460, padding: 16, position: 'relative' }}>
          {allNoise && (
            <div style={{ position: 'absolute', top: '50%', left: '50%', transform: 'translate(-50%,-50%)', textAlign: 'center', zIndex: 10, pointerEvents: 'none' }}>
              <div style={{ fontSize: 32, marginBottom: 8 }}>🔍</div>
              <div style={{ fontSize: 14, color: '#64748b', fontWeight: 500 }}>Too few papers for clustering</div>
              <div style={{ fontSize: 12, color: '#334155', marginTop: 4 }}>
                HDBSCAN needs ≥15 papers to form clusters.<br />
                {papers.length < 20 ? `Only ${papers.length} papers found — try a broader topic.` : `All ${noiseCount} papers marked as noise.`}
              </div>
            </div>
          )}
          <Plot
            data={traces}
            layout={{
              paper_bgcolor: 'transparent', plot_bgcolor: 'transparent',
              margin: { t: 10, b: 10, l: 10, r: 10 },
              xaxis: { showgrid: false, zeroline: false, showticklabels: false },
              yaxis: { showgrid: false, zeroline: false, showticklabels: false },
              legend: { font: { color: '#94a3b8', size: 11 }, bgcolor: 'transparent', bordercolor: 'transparent', orientation: 'h', x: 0, y: -0.05 },
              font: { family: 'Inter, system-ui, sans-serif', color: '#94a3b8' },
              hovermode: 'closest',
            }}
            config={{ displayModeBar: false, responsive: true }}
            style={{ width: '100%', height: '100%' }}
            onClick={(e) => {
              const pt = e.points?.[0];
              if (pt?.customdata) setSelected(pt.customdata as unknown as Paper);
            }}
          />


        </div>

        {/* Side panel */}
        <div style={{ display: 'flex', flexDirection: 'column', gap: 12 }}>
          {/* Cluster legend */}
          <div className="glass" style={{ padding: 16 }}>
            <div style={{ fontSize: 11, fontWeight: 700, color: '#7c3aed', textTransform: 'uppercase', letterSpacing: '0.1em', marginBottom: 12 }}>
              {allNoise ? '0 Clusters' : `${clusters.length} Clusters`}
            </div>
            {allNoise ? (
              <p style={{ fontSize: 12, color: '#334155', lineHeight: 1.6, margin: 0 }}>
                Not enough papers to form meaningful clusters. All papers appear grey (unclustered).
                Try a more specific topic with more published research.
              </p>
            ) : (
              <div style={{ display: 'flex', flexDirection: 'column', gap: 10 }}>
                {clusters.map((c) => (
                  <div key={c.cluster_id} style={{ display: 'flex', alignItems: 'center', gap: 10 }}>
                    <div style={{ width: 10, height: 10, borderRadius: '50%', background: CLUSTER_COLORS[c.cluster_id % CLUSTER_COLORS.length], flexShrink: 0, boxShadow: `0 0 6px ${CLUSTER_COLORS[c.cluster_id % CLUSTER_COLORS.length]}60` }} />
                    <div style={{ flex: 1, minWidth: 0 }}>
                      <div style={{ fontSize: 12, color: '#cbd5e1', overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>{c.label}</div>
                      <div style={{ fontSize: 11, color: '#475569' }}>{c.paper_count} papers</div>
                    </div>
                  </div>
                ))}
                {noiseCount > 0 && (
                  <div style={{ display: 'flex', alignItems: 'center', gap: 10, marginTop: 4, paddingTop: 8, borderTop: '1px solid #1e293b' }}>
                    <div style={{ width: 10, height: 10, borderRadius: '50%', background: '#374151', flexShrink: 0 }} />
                    <div style={{ fontSize: 11, color: '#334155' }}>{noiseCount} unclustered papers</div>
                  </div>
                )}
              </div>
            )}
          </div>



          {/* Paper detail on click */}
          {selected ? (
            <div className="glass animate-fadeUp" style={{ padding: 16, flex: 1 }}>
              <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: 10 }}>
                <span style={{ fontSize: 10, fontWeight: 700, color: '#7c3aed', textTransform: 'uppercase', letterSpacing: '0.1em' }}>Selected Paper</span>
                <button onClick={() => setSelected(null)} style={{ color: '#475569', background: 'none', border: 'none', cursor: 'pointer', fontSize: 14, lineHeight: 1 }}>✕</button>
              </div>
              <h4 style={{ fontSize: 13, fontWeight: 600, color: '#f1f5f9', lineHeight: 1.5, marginBottom: 10 }}>{selected.title}</h4>
              <div style={{ display: 'flex', flexWrap: 'wrap', gap: 6, marginBottom: 10 }}>
                <span style={{ fontSize: 11, padding: '2px 8px', borderRadius: 6, background: 'rgba(124,58,237,0.15)', color: '#a78bfa', border: '1px solid rgba(124,58,237,0.25)' }}>{selected.year}</span>
                {selected.citation_count > 0 && (
                  <span title="Number of times other papers have cited this work — a measure of influence" style={{ fontSize: 11, padding: '2px 8px', borderRadius: 6, background: 'rgba(245,158,11,0.12)', color: '#fbbf24', border: '1px solid rgba(245,158,11,0.2)', cursor: 'help' }}>
                    ★ {selected.citation_count.toLocaleString()} citations
                  </span>
                )}
              </div>
              {selected.key_contribution && <p style={{ fontSize: 12, color: '#94a3b8', lineHeight: 1.65, margin: 0 }}>{selected.key_contribution}</p>}
              {selected.method && <div style={{ marginTop: 10, fontSize: 11 }}><span style={{ color: '#475569' }}>Method: </span><span style={{ color: '#c4b5fd' }}>{selected.method}</span></div>}
              {selected.pdf_url && (
                <a href={selected.pdf_url} target="_blank" rel="noopener noreferrer"
                  style={{ display: 'inline-flex', alignItems: 'center', gap: 4, marginTop: 10, fontSize: 12, color: '#7c3aed', textDecoration: 'none', fontWeight: 500 }}>
                  📄 View PDF ↗
                </a>
              )}
            </div>
          ) : (
            <div className="glass" style={{ padding: 20, flex: 1, display: 'flex', alignItems: 'center', justifyContent: 'center', border: '1px dashed rgba(124,58,237,0.2)' }}>
              <p style={{ color: '#334155', fontSize: 12, textAlign: 'center', lineHeight: 1.8, margin: 0 }}>
                👆 <strong style={{ color: '#475569' }}>Click any dot</strong><br />
                to inspect the paper,<br />
                see its contribution<br />
                and open the PDF
              </p>
            </div>
          )}
        </div>
      </div>
    </div>
  );
}
