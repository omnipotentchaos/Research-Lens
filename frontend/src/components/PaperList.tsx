'use client';

import { useState } from 'react';
import { Paper, Cluster } from '@/lib/types';

const CLUSTER_COLORS = [
  '#7c3aed', '#2563eb', '#0891b2', '#059669',
  '#d97706', '#dc2626', '#a21caf', '#0d9488',
  '#b45309', '#be185d',
];

const SOURCE_LABELS: Record<string, { label: string; color: string; bg: string }> = {
  arxiv:      { label: 'arXiv',    color: '#f97316', bg: 'rgba(249,115,22,0.12)' },
  openalex:   { label: 'OpenAlex', color: '#38bdf8', bg: 'rgba(56,189,248,0.12)' },
  semantic_scholar: { label: 'S2', color: '#a78bfa', bg: 'rgba(167,139,250,0.12)' },
};

interface Props { papers: Paper[]; clusters: Cluster[]; }

export default function PaperList({ papers, clusters }: Props) {
  const [expandedId, setExpandedId] = useState<number | null>(null);
  const [filterCluster, setFilterCluster] = useState<number | 'all'>('all');
  const [search, setSearch] = useState('');

  const SOURCE_ORDER: Record<string, number> = { openalex: 0, semantic_scholar: 1, arxiv: 2 };

  const filtered = papers
    .filter(p => {
      const matchCluster =
        filterCluster === 'all' ||
        Number(p.cluster_id) === Number(filterCluster);
      const matchSearch = !search || p.title.toLowerCase().includes(search.toLowerCase());
      return matchCluster && matchSearch;
    })
    .sort((a, b) => {
      const srcA = SOURCE_ORDER[a.source] ?? 99;
      const srcB = SOURCE_ORDER[b.source] ?? 99;
      if (srcA !== srcB) return srcA - srcB;                          // source group first
      return (b.citation_count ?? 0) - (a.citation_count ?? 0);      // within group: citations desc
    });


  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: 16 }}>

      {/* Search */}
      <div style={{ position: 'relative' }}>
        <span style={{ position: 'absolute', left: 14, top: '50%', transform: 'translateY(-50%)', color: '#475569', fontSize: 16 }}>🔍</span>
        <input
          type="text"
          value={search}
          onChange={e => setSearch(e.target.value)}
          placeholder="Search papers by title…"
          style={{ width: '100%', padding: '11px 16px 11px 40px', borderRadius: 12, background: 'rgba(15,22,41,0.9)', border: '1px solid #1e293b', color: '#f1f5f9', fontSize: 14, fontFamily: 'inherit', boxSizing: 'border-box' }}
          onFocus={e => (e.target.style.borderColor = 'rgba(124,58,237,0.5)')}
          onBlur={e => (e.target.style.borderColor = '#1e293b')}
        />
      </div>

      {/* Cluster filter chips */}
      <div style={{ display: 'flex', flexWrap: 'wrap', gap: 8 }}>
        <button
          onClick={() => setFilterCluster('all')}
          style={{
            padding: '6px 14px', borderRadius: 20, fontSize: 12, fontWeight: 500, border: '1px solid', cursor: 'pointer', fontFamily: 'inherit', transition: 'all 0.15s',
            borderColor: filterCluster === 'all' ? '#7c3aed' : '#1e293b',
            background: filterCluster === 'all' ? 'rgba(124,58,237,0.2)' : 'transparent',
            color: filterCluster === 'all' ? '#c4b5fd' : '#475569',
          }}
        >
          All · {papers.length}
        </button>
        {clusters.map((c) => {
          const active = filterCluster === c.cluster_id;
          const color = CLUSTER_COLORS[c.cluster_id % CLUSTER_COLORS.length];
          return (
            <button key={c.cluster_id} onClick={() => setFilterCluster(c.cluster_id)}
              style={{
                padding: '6px 14px', borderRadius: 20, fontSize: 12, fontWeight: 500, border: '1px solid', cursor: 'pointer', fontFamily: 'inherit', transition: 'all 0.15s',
                borderColor: active ? color : '#1e293b',
                background: active ? color + '25' : 'transparent',
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
        Showing <span style={{ color: '#7c3aed', fontWeight: 600 }}>{filtered.length}</span> of {papers.length} papers
      </div>

      {/* Paper rows */}
      <div style={{ display: 'flex', flexDirection: 'column', gap: 8 }}>
        {filtered.map((paper, i) => {
          const clusterIdx = clusters.findIndex(c => c.cluster_id === paper.cluster_id);
          const color = clusterIdx >= 0 ? CLUSTER_COLORS[paper.cluster_id % CLUSTER_COLORS.length] : '#334155';
          const expanded = expandedId === (paper.id ?? i);
          const srcInfo = SOURCE_LABELS[paper.source] ?? { label: paper.source, color: '#64748b', bg: 'rgba(100,116,139,0.1)' };

          return (
            <div key={paper.id ?? i} className="glass" style={{ overflow: 'hidden', transition: 'border-color 0.2s' }}
              onMouseEnter={e => (e.currentTarget.style.borderColor = color + '50')}
              onMouseLeave={e => (e.currentTarget.style.borderColor = 'rgba(139,92,246,0.18)')}
            >
              <button
                style={{ width: '100%', background: 'none', border: 'none', cursor: 'pointer', padding: '14px 16px', display: 'flex', alignItems: 'flex-start', gap: 14, textAlign: 'left', fontFamily: 'inherit' }}
                onClick={() => setExpandedId(expanded ? null : (paper.id ?? i))}
              >
                {/* Color accent bar */}
                <div style={{ width: 3, minHeight: 40, borderRadius: 2, background: color, flexShrink: 0, alignSelf: 'stretch' }} />

                <div style={{ flex: 1, minWidth: 0 }}>
                  <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'flex-start', gap: 12 }}>
                    <h4 style={{ fontSize: 14, fontWeight: 500, color: '#e2e8f0', lineHeight: 1.5, margin: 0 }}>{paper.title}</h4>
                    <span style={{ color: '#334155', fontSize: 16, flexShrink: 0, marginTop: 2 }}>{expanded ? '▲' : '▼'}</span>
                  </div>

                  {/* Meta badges */}
                  <div style={{ display: 'flex', alignItems: 'center', gap: 8, marginTop: 8, flexWrap: 'wrap' }}>
                    <span style={{ fontSize: 12, fontWeight: 600, color: '#94a3b8' }}>{paper.year}</span>
                    <span style={{ width: 3, height: 3, borderRadius: '50%', background: '#334155' }} />
                    {paper.citation_count > 0 && <>
                      <span
                        title="Citation count — how many other papers have cited this work. Higher = more influential."
                        style={{ fontSize: 12, color: '#f59e0b', cursor: 'help' }}
                      >★ {paper.citation_count.toLocaleString()}</span>
                      <span style={{ width: 3, height: 3, borderRadius: '50%', background: '#334155' }} />
                    </>}
                    <span style={{ fontSize: 11, padding: '2px 8px', borderRadius: 6, background: srcInfo.bg, color: srcInfo.color, border: `1px solid ${srcInfo.color}30`, fontWeight: 500 }}>
                      {srcInfo.label}
                    </span>
                    {clusterIdx >= 0 && (
                      <span style={{ fontSize: 11, padding: '2px 8px', borderRadius: 6, background: color + '18', color, border: `1px solid ${color}30`, fontWeight: 500, maxWidth: 180, overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>
                        {clusters[clusterIdx]?.label}
                      </span>
                    )}
                  </div>
                </div>
              </button>

              {/* Expanded detail */}
              {expanded && (
                <div style={{ padding: '0 16px 16px', paddingLeft: 33, display: 'flex', flexDirection: 'column', gap: 12 }} className="animate-fadeUp">
                  <div style={{ height: 1, background: 'rgba(124,58,237,0.12)', margin: '0 0 4px' }} />

                  {paper.key_contribution && (
                    <div>
                      <div style={{ fontSize: 10, fontWeight: 700, color: '#7c3aed', textTransform: 'uppercase', letterSpacing: '0.1em', marginBottom: 6 }}>Key Contribution</div>
                      <p style={{ fontSize: 13, color: '#cbd5e1', lineHeight: 1.7, margin: 0 }}>{paper.key_contribution}</p>
                    </div>
                  )}

                  {paper.abstract && (
                    <div>
                      <div style={{ fontSize: 10, fontWeight: 700, color: '#334155', textTransform: 'uppercase', letterSpacing: '0.1em', marginBottom: 6 }}>Abstract</div>
                      <p style={{ fontSize: 12, color: '#64748b', lineHeight: 1.7, margin: 0, display: '-webkit-box', WebkitLineClamp: 4, WebkitBoxOrient: 'vertical', overflow: 'hidden' }}>{paper.abstract}</p>
                    </div>
                  )}

                  {/* Inline metadata chips */}
                  {(paper.method || paper.dataset || paper.task || paper.metrics) && (
                    <div style={{ display: 'flex', flexWrap: 'wrap', gap: 8 }}>
                      {[
                        { label: 'Method', val: paper.method, color: '#a78bfa', bg: 'rgba(167,139,250,0.1)' },
                        { label: 'Dataset', val: paper.dataset, color: '#34d399', bg: 'rgba(52,211,153,0.1)' },
                        { label: 'Task', val: paper.task, color: '#60a5fa', bg: 'rgba(96,165,250,0.1)' },
                        { label: 'Metrics', val: paper.metrics, color: '#fbbf24', bg: 'rgba(251,191,36,0.1)' },
                      ].filter(m => m.val).map(m => (
                        <div key={m.label} style={{ padding: '4px 10px', borderRadius: 8, background: m.bg, border: `1px solid ${m.color}25`, fontSize: 11 }}>
                          <span style={{ color: '#475569' }}>{m.label}: </span>
                          <span style={{ color: m.color, fontWeight: 500 }}>{m.val}</span>
                        </div>
                      ))}
                    </div>
                  )}

                  {(() => {
                    // Derive best available PDF URL
                    const directPdf = paper.pdf_url;
                    const arxivPdf = paper.arxiv_id
                      ? `https://arxiv.org/pdf/${paper.arxiv_id}.pdf`
                      : (paper.source === 'arxiv' && paper.id
                          ? null // arXiv papers from pipeline always have pdf_url set
                          : null);
                    const doiUrl = paper.doi ? `https://doi.org/${paper.doi}` : null;
                    const bestUrl = directPdf || arxivPdf;

                    return (
                      <div style={{ display: 'flex', alignItems: 'center', gap: 12, flexWrap: 'wrap' }}>
                        {bestUrl ? (
                          <a href={bestUrl} target="_blank" rel="noopener noreferrer"
                            style={{ display: 'inline-flex', alignItems: 'center', gap: 6, fontSize: 12, color: '#7c3aed', textDecoration: 'none', fontWeight: 600, padding: '4px 12px', borderRadius: 8, background: 'rgba(124,58,237,0.12)', border: '1px solid rgba(124,58,237,0.25)' }}>
                            📄 View PDF ↗
                          </a>
                        ) : (
                          <span
                            title="This paper is published in a paywalled journal. arXiv papers are always free; OpenAlex papers only show a PDF link when the authors posted an open-access version."
                            style={{ fontSize: 11, color: '#334155', cursor: 'help', fontStyle: 'italic' }}
                          >
                            🔒 No open-access PDF (paywalled)
                          </span>
                        )}
                        {doiUrl && !bestUrl && (
                          <a href={doiUrl} target="_blank" rel="noopener noreferrer"
                            style={{ fontSize: 12, color: '#475569', textDecoration: 'none', fontWeight: 500 }}>
                            🔗 View via DOI ↗
                          </a>
                        )}
                      </div>
                    );
                  })()}
                </div>
              )}
            </div>
          );
        })}
      </div>
    </div>
  );
}
