'use client';

import { useMemo, useState } from 'react';
import { Paper } from '@/lib/types';

interface Props {
  papers: Paper[];
}

export default function MethodologyTable({ papers }: Props) {
  const [searchTerm, setSearchTerm] = useState('');

  // Filter out papers that have absolutely no extracted fields
  const tableData = useMemo(() => {
    return papers
      .filter(p => p.method || p.dataset || p.metrics)
      .sort((a, b) => (b.year ?? 0) - (a.year ?? 0));
  }, [papers]);

  const filteredData = useMemo(() => {
    if (!searchTerm) return tableData;
    const term = searchTerm.toLowerCase();
    return tableData.filter(
      p =>
        p.title.toLowerCase().includes(term) ||
        (p.method && p.method.toLowerCase().includes(term)) ||
        (p.dataset && p.dataset.toLowerCase().includes(term))
    );
  }, [tableData, searchTerm]);

  const exportCSV = () => {
    const headers = ['Year', 'Title', 'Method', 'Dataset', 'Metrics', 'Citations'];
    const rows = filteredData.map(p => [
      p.year ?? '',
      `"${p.title.replace(/"/g, '""')}"`,
      `"${(p.method || '').replace(/"/g, '""')}"`,
      `"${(p.dataset || '').replace(/"/g, '""')}"`,
      `"${(p.metrics || '').replace(/"/g, '""')}"`,
      p.citation_count ?? 0,
    ]);
    
    const csvContent = [headers.join(','), ...rows.map(r => r.join(','))].join('\n');
    const blob = new Blob([csvContent], { type: 'text/csv;charset=utf-8;' });
    const link = document.createElement('a');
    link.href = URL.createObjectURL(blob);
    link.setAttribute('download', 'literature_review_table.csv');
    document.body.appendChild(link);
    link.click();
    document.body.removeChild(link);
  };

  if (tableData.length === 0) return null;

  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: 16 }}>
      <div className="glass" style={{ padding: '16px 20px', borderLeft: '3px solid #3b82f6', display: 'flex', alignItems: 'flex-start', gap: 12 }}>
        <span style={{ fontSize: 22, flexShrink: 0 }}>📊</span>
        <div style={{ flex: 1 }}>
          <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', flexWrap: 'wrap', gap: 12 }}>
            <div>
              <div style={{ fontSize: 13, fontWeight: 700, color: '#60a5fa', marginBottom: 4 }}>Methodology Comparison</div>
              <div style={{ fontSize: 12, color: '#64748b' }}>
                Auto-extracted state-of-the-art comparison table for your literature review.
              </div>
            </div>
            
            <div style={{ display: 'flex', gap: 10 }}>
              <input
                type="text"
                placeholder="Filter table..."
                value={searchTerm}
                onChange={e => setSearchTerm(e.target.value)}
                style={{
                  background: 'rgba(15,22,41,0.5)', border: '1px solid #1e293b', borderRadius: 8,
                  padding: '6px 12px', color: '#e2e8f0', fontSize: 12, outline: 'none'
                }}
              />
              <button
                onClick={exportCSV}
                style={{
                  background: 'rgba(59,130,246,0.1)', color: '#60a5fa', border: '1px solid rgba(59,130,246,0.3)',
                  padding: '6px 14px', borderRadius: 8, fontSize: 12, fontWeight: 600, cursor: 'pointer',
                  display: 'flex', alignItems: 'center', gap: 6, transition: 'all 0.2s'
                }}
              >
                <span>⬇️</span> Export CSV
              </button>
            </div>
          </div>
        </div>
      </div>

      <div className="glass" style={{ overflowX: 'auto', borderRadius: 12 }}>
        <table style={{ width: '100%', borderCollapse: 'collapse', textAlign: 'left', fontSize: 12 }}>
          <thead>
            <tr style={{ background: 'rgba(15,22,41,0.8)', borderBottom: '1px solid #1e293b' }}>
              <th style={{ padding: '12px 16px', color: '#94a3b8', fontWeight: 600, width: '60px' }}>Year</th>
              <th style={{ padding: '12px 16px', color: '#94a3b8', fontWeight: 600 }}>Title</th>
              <th style={{ padding: '12px 16px', color: '#94a3b8', fontWeight: 600, width: '20%' }}>Method</th>
              <th style={{ padding: '12px 16px', color: '#94a3b8', fontWeight: 600, width: '15%' }}>Dataset</th>
              <th style={{ padding: '12px 16px', color: '#94a3b8', fontWeight: 600, width: '15%' }}>Metrics</th>
            </tr>
          </thead>
          <tbody>
            {filteredData.map((p, i) => (
              <tr key={p.id ?? i} style={{ borderBottom: '1px solid #1e293b', background: i % 2 === 0 ? 'transparent' : 'rgba(15,22,41,0.3)' }}>
                <td style={{ padding: '12px 16px', color: '#e2e8f0', verticalAlign: 'top' }}>{p.year}</td>
                <td style={{ padding: '12px 16px', color: '#cbd5e1', verticalAlign: 'top', fontWeight: 500 }}>
                  {p.title}
                  {p.citation_count > 0 && (
                    <span style={{ display: 'inline-block', marginLeft: 8, fontSize: 10, color: '#f59e0b', background: 'rgba(245,158,11,0.1)', padding: '1px 6px', borderRadius: 4 }}>
                      ★ {p.citation_count}
                    </span>
                  )}
                </td>
                <td style={{ padding: '12px 16px', color: '#a78bfa', verticalAlign: 'top' }}>{p.method || '-'}</td>
                <td style={{ padding: '12px 16px', color: '#34d399', verticalAlign: 'top' }}>{p.dataset || '-'}</td>
                <td style={{ padding: '12px 16px', color: '#94a3b8', verticalAlign: 'top' }}>{p.metrics || '-'}</td>
              </tr>
            ))}
          </tbody>
        </table>
        {filteredData.length === 0 && (
          <div style={{ padding: 30, textAlign: 'center', color: '#64748b', fontSize: 13 }}>
            No papers match your filter.
          </div>
        )}
      </div>
    </div>
  );
}
