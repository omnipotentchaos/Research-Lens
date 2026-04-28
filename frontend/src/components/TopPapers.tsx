'use client';

import { useMemo, useState } from 'react';
import { Paper, Cluster } from '@/lib/types';

interface Props { papers: Paper[]; clusters: Cluster[]; }

const CLUSTER_COLORS = [
  '#7c3aed', '#2563eb', '#0891b2', '#059669',
  '#d97706', '#dc2626', '#a21caf', '#0d9488',
];

const SOURCE_LABELS: Record<string, { label: string; color: string; bg: string }> = {
  arxiv:            { label: 'arXiv',    color: '#f97316', bg: 'rgba(249,115,22,0.12)' },
  openalex:         { label: 'OpenAlex', color: '#38bdf8', bg: 'rgba(56,189,248,0.12)' },
  semantic_scholar: { label: 'S2',       color: '#a78bfa', bg: 'rgba(167,139,250,0.12)' },
};

const MEDAL = ['🥇', '🥈', '🥉'];

export default function TopPapers({ papers, clusters }: Props) {
  const [filterCluster, setFilterCluster] = useState<number | 'all'>('all');
  const [expandedAbstracts, setExpandedAbstracts] = useState<Record<number, boolean>>({});

  const toggleAbstract = (id: number) => {
    setExpandedAbstracts(prev => ({ ...prev, [id]: !prev[id] }));
  };

  const clusterMap = useMemo(
    () => Object.fromEntries(clusters.map(c => [c.cluster_id, c])),
    [clusters],
  );

  // Sort: cited papers first (desc), then arXiv by year desc
  const sorted = useMemo(() => {
    return [...papers].sort((a, b) => {
      const ca = a.citation_count ?? 0;
      const cb = b.citation_count ?? 0;
      if (cb !== ca) return cb - ca;
      return (b.year ?? 0) - (a.year ?? 0);
    });
  }, [papers]);

  const filtered = useMemo(() => {
    if (filterCluster === 'all') return sorted;
    return sorted.filter(p => Number(p.cluster_id) === Number(filterCluster));
  }, [sorted, filterCluster]);

  // Find citation max for the influence bar
  const maxCitations = sorted[0]?.citation_count ?? 1;

  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: 20 }}>

      {/* Header */}
      <div className="glass" style={{ padding: '14px 20px', borderLeft: '3px solid #f59e0b', display: 'flex', alignItems: 'flex-start', gap: 12 }}>
        <span style={{ fontSize: 22, flexShrink: 0 }}>🏆</span>
        <div>
          <div style={{ fontSize: 13, fontWeight: 700, color: '#fbbf24', marginBottom: 4 }}>Top Papers Spotlight</div>
          <div style={{ fontSize: 12, color: '#64748b', lineHeight: 1.7 }}>
            The most influential papers in this topic, ranked by citation count.{' '}
            <strong style={{ color: '#94a3b8' }}>OpenAlex papers have real citation data</strong>; arXiv-only papers are listed after.
            Use this to identify foundational works before writing a literature review.
          </div>
        </div>
      </div>

      {/* Cluster filter chips */}
      <div style={{ display: 'flex', flexWrap: 'wrap', gap: 8 }}>
        <button
          onClick={() => setFilterCluster('all')}
          style={{
            padding: '6px 14px', borderRadius: 20, fontSize: 12, fontWeight: 500,
            border: '1px solid', cursor: 'pointer', fontFamily: 'inherit', transition: 'all 0.15s',
            borderColor: filterCluster === 'all' ? '#f59e0b' : '#1e293b',
            background: filterCluster === 'all' ? 'rgba(245,158,11,0.15)' : 'transparent',
            color: filterCluster === 'all' ? '#fbbf24' : '#475569',
          }}
        >
          All · {papers.length}
        </button>
        {clusters.map(c => {
          const active = filterCluster === c.cluster_id;
          const color = CLUSTER_COLORS[c.cluster_id % CLUSTER_COLORS.length];
          return (
            <button key={c.cluster_id} onClick={() => setFilterCluster(c.cluster_id)}
              style={{
                padding: '6px 14px', borderRadius: 20, fontSize: 12, fontWeight: 500,
                border: '1px solid', cursor: 'pointer', fontFamily: 'inherit', transition: 'all 0.15s',
                borderColor: active ? color : '#1e293b',
                background: active ? color + '22' : 'transparent',
                color: active ? color : '#475569',
              }}
            >
              {c.label} · {c.paper_count}
            </button>
          );
        })}
      </div>

      {/* Count */}
      <div style={{ color: '#334155', fontSize: 13 }}>
        Showing <span style={{ color: '#f59e0b', fontWeight: 600 }}>{filtered.length}</span> of {papers.length} papers
      </div>

      {/* Paper Cards */}
      <div style={{ display: 'flex', flexDirection: 'column', gap: 14 }}>
        {filtered.map((paper, i) => {
          const cluster = clusterMap[Number(paper.cluster_id)];
          const clusterColor = cluster ? CLUSTER_COLORS[Number(paper.cluster_id) % CLUSTER_COLORS.length] : '#334155';
          const srcInfo = SOURCE_LABELS[paper.source] ?? { label: paper.source, color: '#64748b', bg: 'rgba(100,116,139,0.1)' };
          const isSeminal = (paper.citation_count ?? 0) >= 50;
          const citations = paper.citation_count ?? 0;
          const infPct = maxCitations > 0 ? Math.min((citations / maxCitations) * 100, 100) : 0;
          const medal = i < 3 && citations > 0 ? MEDAL[i] : null;

          const pdfUrl = paper.pdf_url || (paper.arxiv_id ? `https://arxiv.org/pdf/${paper.arxiv_id}.pdf` : null);
          const doiUrl = paper.doi ? `https://doi.org/${paper.doi}` : null;

          return (
            <div
              key={paper.id ?? i}
              className="glass"
              style={{
                padding: '18px 20px',
                borderLeft: `3px solid ${clusterColor}`,
                transition: 'border-color 0.2s, box-shadow 0.2s',
                position: 'relative',
                overflow: 'hidden',
              }}
              onMouseEnter={e => {
                (e.currentTarget as HTMLElement).style.boxShadow = `0 4px 24px ${clusterColor}25`;
              }}
              onMouseLeave={e => {
                (e.currentTarget as HTMLElement).style.boxShadow = '';
              }}
            >
              {/* Influence bar (subtle background) */}
              {citations > 0 && (
                <div style={{
                  position: 'absolute', top: 0, right: 0, height: '100%',
                  width: `${infPct}%`, maxWidth: '60%',
                  background: `linear-gradient(90deg, transparent, ${clusterColor}08)`,
                  pointerEvents: 'none',
                }} />
              )}

              {/* Top row: rank + title + badges */}
              <div style={{ display: 'flex', alignItems: 'flex-start', gap: 14, position: 'relative' }}>
                {/* Rank */}
                <div style={{
                  flexShrink: 0, width: 32, height: 32, borderRadius: '50%',
                  display: 'flex', alignItems: 'center', justifyContent: 'center',
                  background: medal ? 'transparent' : `${clusterColor}18`,
                  border: `1.5px solid ${medal ? 'transparent' : clusterColor + '40'}`,
                  fontSize: medal ? 20 : 11, fontWeight: 700,
                  color: clusterColor,
                }}>
                  {medal || (i + 1)}
                </div>

                <div style={{ flex: 1, minWidth: 0 }}>
                  {/* Title */}
                  <div style={{ display: 'flex', alignItems: 'center', gap: 8, flexWrap: 'wrap', marginBottom: 8 }}>
                    {isSeminal && (
                      <span title="Highly cited — seminal work" style={{ fontSize: 14 }}>⭐</span>
                    )}
                    <h3 style={{ fontSize: 14, fontWeight: 600, color: '#e2e8f0', lineHeight: 1.5, margin: 0 }}>
                      {paper.title}
                    </h3>
                  </div>

                  {/* Meta row */}
                  <div style={{ display: 'flex', alignItems: 'center', gap: 8, flexWrap: 'wrap', marginBottom: 10 }}>
                    <span style={{ fontSize: 12, fontWeight: 600, color: '#64748b' }}>{paper.year}</span>

                    {citations > 0 && <>
                      <span style={{ width: 3, height: 3, borderRadius: '50%', background: '#1e293b', flexShrink: 0 }} />
                      <span
                        title={`${citations.toLocaleString()} citations — higher means more influential in the field`}
                        style={{ fontSize: 12, color: '#f59e0b', fontWeight: 700, cursor: 'help', display: 'flex', alignItems: 'center', gap: 3 }}
                      >
                        ★ {citations.toLocaleString()}
                        <span style={{ fontSize: 10, color: '#78716c', fontWeight: 400 }}>citations</span>
                      </span>
                    </>}

                    <span style={{ width: 3, height: 3, borderRadius: '50%', background: '#1e293b', flexShrink: 0 }} />
                    <span style={{ fontSize: 11, padding: '2px 8px', borderRadius: 6, background: srcInfo.bg, color: srcInfo.color, border: `1px solid ${srcInfo.color}30`, fontWeight: 500 }}>
                      {srcInfo.label}
                    </span>

                    {cluster && (
                      <span style={{ fontSize: 11, padding: '2px 10px', borderRadius: 6, background: clusterColor + '18', color: clusterColor, border: `1px solid ${clusterColor}30`, fontWeight: 500 }}>
                        {cluster.label}
                      </span>
                    )}
                  </div>

                  {/* Citation influence bar */}
                  {citations > 0 && (
                    <div style={{ display: 'flex', alignItems: 'center', gap: 8, marginBottom: 12 }}>
                      <span style={{ fontSize: 10, color: '#334155', width: 60, flexShrink: 0 }}>Influence</span>
                      <div style={{ flex: 1, maxWidth: 200, height: 4, borderRadius: 4, background: 'rgba(15,22,41,0.8)', overflow: 'hidden' }}>
                        <div style={{
                          height: '100%', width: `${infPct}%`, borderRadius: 4,
                          background: `linear-gradient(90deg, ${clusterColor}, ${clusterColor}aa)`,
                          transition: 'width 0.6s ease',
                        }} />
                      </div>
                    </div>
                  )}

                  {/* Key contribution */}
                  {paper.key_contribution && (
                    <div style={{ marginBottom: 10 }}>
                      <span style={{ fontSize: 10, fontWeight: 700, color: '#7c3aed', textTransform: 'uppercase', letterSpacing: '0.08em' }}>Key Contribution · </span>
                      <span style={{ fontSize: 12, color: '#94a3b8', lineHeight: 1.6 }}>{paper.key_contribution}</span>
                    </div>
                  )}

                  {/* Method + Dataset chips */}
                  <div style={{ display: 'flex', flexWrap: 'wrap', gap: 6, marginBottom: 10 }}>
                    {paper.method && (
                      <span style={{ fontSize: 10, padding: '2px 8px', borderRadius: 5, background: 'rgba(167,139,250,0.1)', color: '#a78bfa', border: '1px solid rgba(167,139,250,0.2)' }}>
                        ⚙ {paper.method}
                      </span>
                    )}
                    {paper.dataset && (
                      <span style={{ fontSize: 10, padding: '2px 8px', borderRadius: 5, background: 'rgba(52,211,153,0.1)', color: '#34d399', border: '1px solid rgba(52,211,153,0.2)' }}>
                        📊 {paper.dataset}
                      </span>
                    )}
                    {paper.task && (
                      <span style={{ fontSize: 10, padding: '2px 8px', borderRadius: 5, background: 'rgba(96,165,250,0.1)', color: '#60a5fa', border: '1px solid rgba(96,165,250,0.2)' }}>
                        🎯 {paper.task}
                      </span>
                    )}
                  </div>

                  {/* Links and Actions */}
                  <div style={{ display: 'flex', gap: 10, flexWrap: 'wrap', alignItems: 'center' }}>
                    {pdfUrl ? (
                      <a href={pdfUrl} target="_blank" rel="noopener noreferrer" style={{
                        display: 'inline-flex', alignItems: 'center', gap: 5, fontSize: 11,
                        color: '#7c3aed', textDecoration: 'none', fontWeight: 600,
                        padding: '4px 12px', borderRadius: 8,
                        background: 'rgba(124,58,237,0.1)', border: '1px solid rgba(124,58,237,0.25)',
                        transition: 'background 0.15s',
                      }}>
                        📄 Read Paper ↗
                      </a>
                    ) : doiUrl ? (
                      <a href={doiUrl} target="_blank" rel="noopener noreferrer" style={{
                        display: 'inline-flex', alignItems: 'center', gap: 5, fontSize: 11,
                        color: '#475569', textDecoration: 'none', fontWeight: 500,
                        padding: '4px 12px', borderRadius: 8,
                        background: 'rgba(71,85,105,0.1)', border: '1px solid rgba(71,85,105,0.25)',
                      }}>
                        🔗 View via DOI ↗
                      </a>
                    ) : (
                      <span style={{ fontSize: 11, color: '#334155', fontStyle: 'italic' }}>
                        🔒 Paywalled — no open access PDF
                      </span>
                    )}
                    
                    {/* Expand Abstract Button */}
                    {paper.abstract && (
                      <button
                        onClick={() => toggleAbstract(paper.id ?? i)}
                        style={{
                          background: 'none', border: 'none', color: '#64748b', fontSize: 11,
                          cursor: 'pointer', padding: '4px 8px', display: 'flex', alignItems: 'center', gap: 4,
                        }}
                      >
                        {expandedAbstracts[paper.id ?? i] ? 'Hide Abstract ▲' : 'Read Abstract ▼'}
                      </button>
                    )}
                  </div>
                  
                  {/* Expanded Abstract Section */}
                  {expandedAbstracts[paper.id ?? i] && paper.abstract && (
                    <div style={{
                      marginTop: 14, padding: '12px 14px', borderRadius: 8,
                      background: 'rgba(15,22,41,0.5)', border: '1px solid #1e293b',
                      fontSize: 12, color: '#94a3b8', lineHeight: 1.6,
                    }}>
                      <div style={{ fontWeight: 600, color: '#e2e8f0', marginBottom: 6 }}>Abstract</div>
                      {paper.abstract}
                    </div>
                  )}
                </div>
              </div>
            </div>
          );
        })}
      </div>
    </div>
  );
}
