'use client';

import dynamic from 'next/dynamic';
import { Temporal } from '@/lib/types';

const Plot = dynamic(() => import('react-plotly.js'), { ssr: false });

interface Props { temporal: Temporal; }

// Assign a stable color per method name
const PALETTE = ['#7c3aed', '#0891b2', '#059669', '#d97706', '#dc2626', '#a21caf', '#2563eb', '#0d9488'];

function colorFor(method: string, idx: number) {
  return PALETTE[idx % PALETTE.length];
}

export default function TimelineChart({ temporal }: Props) {
  if (!temporal) return (
    <div className="glass" style={{ padding: 48, textAlign: 'center', color: '#475569' }}>No temporal data available.</div>
  );

  const years = Object.keys(temporal.paper_counts_per_year ?? {}).sort();
  const counts = years.map(y => temporal.paper_counts_per_year[y]);

  // Sort methods by total mentions descending, keep top 8 to avoid legend clutter
  const methodEntries = Object.entries(temporal.method_frequency ?? {})
    .map(([method, byYear]) => ({
      method,
      total: Object.values(byYear).reduce((s, v) => s + v, 0),
      byYear,
    }))
    .sort((a, b) => b.total - a.total)
    .slice(0, 8);

  const totalMethods = Object.keys(temporal.method_frequency ?? {}).length;

  const methodTraces = methodEntries.map(({ method, byYear }, idx) => {
    const sortedYears = Object.keys(byYear).sort();
    return {
      type: 'scatter' as const,
      mode: 'lines+markers' as const,
      name: method.toUpperCase(),
      x: sortedYears,
      y: sortedYears.map(y => byYear[y] ?? 0),
      line: { width: 2, color: colorFor(method, idx) },
      marker: { size: 6, color: colorFor(method, idx) },
      hovertemplate: `<b>${method.toUpperCase()}</b>: %{y} mentions (%{x})<extra></extra>`,
    };
  });

  const paperBar = {
    type: 'bar' as const,
    name: '# Papers',
    x: years,
    y: counts,
    marker: { color: 'rgba(124,58,237,0.25)', line: { color: 'rgba(124,58,237,0.6)', width: 1 } },
    yaxis: 'y2' as const,
    hovertemplate: '<b>%{y} papers</b> published in %{x}<extra></extra>',
  };

  const timeline = temporal.timeline ?? [];
  const maxCount = Math.max(...counts, 1);

  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: 20 }}>

      {/* Summary stat row */}
      <div style={{ display: 'grid', gridTemplateColumns: 'repeat(4, 1fr)', gap: 12 }}>
        {[
          { icon: '📅', label: 'Year Span', value: years.length > 0 ? `${years[0]}–${years[years.length - 1]}` : '—', color: '#a78bfa' },
          { icon: '🔬', label: 'Methods Tracked', value: totalMethods, color: '#60a5fa' },
          { icon: '📈', label: 'Peak Year', value: years[counts.indexOf(maxCount)] ?? '—', color: '#34d399' },
          { icon: '📄', label: 'Peak Papers', value: maxCount, color: '#fbbf24' },
        ].map(s => (
          <div key={s.label} className="glass" style={{ padding: '14px 16px', textAlign: 'center' }}>
            <div style={{ fontSize: 18, marginBottom: 4 }}>{s.icon}</div>
            <div style={{ fontSize: 22, fontWeight: 800, color: s.color, lineHeight: 1 }}>{s.value}</div>
            <div style={{ fontSize: 10, color: '#475569', marginTop: 4, textTransform: 'uppercase', letterSpacing: '0.06em' }}>{s.label}</div>
          </div>
        ))}
      </div>

      {/* Main chart */}
      <div className="glass" style={{ padding: '20px 16px 8px' }}>
        <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: 4, paddingLeft: 8 }}>
          <div style={{ fontSize: 11, fontWeight: 700, color: '#7c3aed', textTransform: 'uppercase', letterSpacing: '0.1em' }}>
            Method Frequency Over Time
          </div>
          {totalMethods > 8 && (
            <div style={{ fontSize: 11, color: '#a78bfa', background: 'rgba(124,58,237,0.15)', border: '1px solid rgba(124,58,237,0.3)', padding: '3px 10px', borderRadius: 20, fontWeight: 600 }}>
              Top 8 of {totalMethods} methods shown
            </div>
          )}
        </div>
        <div style={{ height: 340 }}>
          <Plot
            data={[...methodTraces, paperBar]}
            layout={{
              paper_bgcolor: 'transparent',
              plot_bgcolor: 'transparent',
              margin: { t: 15, b: 85, l: 48, r: 52 },
              xaxis: {
                color: '#475569', tickfont: { size: 11, color: '#64748b' },
                gridcolor: 'rgba(255,255,255,0.03)', zeroline: false,
              },
              yaxis: {
                title: { text: 'Mentions', font: { size: 11, color: '#94a3b8' }, standoff: 4 },
                color: '#64748b', gridcolor: 'rgba(255,255,255,0.04)', rangemode: 'tozero' as const,
                tickfont: { size: 10 }, zeroline: false,
              },
              yaxis2: {
                title: { text: 'Papers', font: { size: 11, color: '#7c3aed' }, standoff: 4 },
                color: '#7c3aed', overlaying: 'y' as const, side: 'right' as const,
                rangemode: 'tozero' as const, showgrid: false,
                tickfont: { size: 10 }, zeroline: false,
              },
              legend: {
                font: { color: '#94a3b8', size: 11 },
                bgcolor: 'rgba(8,11,20,0.8)',
                bordercolor: '#1e293b',
                borderwidth: 1,
                orientation: 'h' as const,
                x: 0,
                y: -0.25,
                xanchor: 'left' as const,
              },
              font: { family: 'Inter, system-ui, sans-serif', color: '#94a3b8' },
              hovermode: 'x unified' as const,
              hoverlabel: { bgcolor: '#0f1629', font: { color: '#f1f5f9', size: 12 }, bordercolor: '#1e293b' },
            }}
            config={{ displayModeBar: false, responsive: true }}
            style={{ width: '100%', height: '100%' }}
          />
        </div>
      </div>

      {/* Year cards grid */}
      {timeline.length > 0 && (
        <div>
          <div style={{ fontSize: 11, fontWeight: 700, color: '#475569', textTransform: 'uppercase', letterSpacing: '0.1em', marginBottom: 12 }}>
            Year-by-Year Breakdown
          </div>
          <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fill, minmax(190px, 1fr))', gap: 12 }}>
            {timeline.map(entry => (
              <div key={entry.year} className="glass" style={{ padding: 16, transition: 'border-color 0.2s' }}
                onMouseEnter={e => (e.currentTarget.style.borderColor = 'rgba(124,58,237,0.35)')}
                onMouseLeave={e => (e.currentTarget.style.borderColor = 'rgba(139,92,246,0.18)')}
              >
                <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'baseline', marginBottom: 10 }}>
                  <span style={{ fontSize: 24, fontWeight: 800, color: '#a78bfa' }}>{entry.year}</span>
                  <span style={{ fontSize: 12, color: '#475569', fontWeight: 500 }}>{entry.paper_count} papers</span>
                </div>

                {/* Progress bar showing relative paper count */}
                <div style={{ height: 3, borderRadius: 2, background: '#1e293b', marginBottom: 12, overflow: 'hidden' }}>
                  <div style={{ height: '100%', borderRadius: 2, background: 'linear-gradient(90deg,#7c3aed,#0891b2)', width: `${Math.round((entry.paper_count / maxCount) * 100)}%`, transition: 'width 0.5s ease' }} />
                </div>

                {entry.emerging_methods.length > 0 && (
                  <div style={{ marginBottom: 8 }}>
                    <div style={{ fontSize: 9, color: '#10b981', marginBottom: 5, fontWeight: 700, letterSpacing: '0.06em' }}>↑ EMERGING</div>
                    <div style={{ display: 'flex', flexWrap: 'wrap', gap: 4 }}>
                      {entry.emerging_methods.slice(0, 4).map(m => (
                        <span key={m} style={{ fontSize: 10, padding: '2px 7px', borderRadius: 5, background: 'rgba(16,185,129,0.1)', color: '#34d399', border: '1px solid rgba(16,185,129,0.2)', fontWeight: 600 }}>
                          {m.toUpperCase()}
                        </span>
                      ))}
                    </div>
                  </div>
                )}
                {entry.fading_methods.length > 0 && (
                  <div>
                    <div style={{ fontSize: 9, color: '#ef4444', marginBottom: 5, fontWeight: 700, letterSpacing: '0.06em' }}>↓ FADING</div>
                    <div style={{ display: 'flex', flexWrap: 'wrap', gap: 4 }}>
                      {entry.fading_methods.slice(0, 3).map(m => (
                        <span key={m} style={{ fontSize: 10, padding: '2px 7px', borderRadius: 5, background: 'rgba(239,68,68,0.08)', color: '#f87171', border: '1px solid rgba(239,68,68,0.18)', fontWeight: 600 }}>
                          {m.toUpperCase()}
                        </span>
                      ))}
                    </div>
                  </div>
                )}
                {entry.emerging_methods.length === 0 && entry.fading_methods.length === 0 && (
                  <span style={{ fontSize: 11, color: '#334155' }}>Stable methods</span>
                )}
              </div>
            ))}
          </div>
        </div>
      )}
    </div>
  );
}
