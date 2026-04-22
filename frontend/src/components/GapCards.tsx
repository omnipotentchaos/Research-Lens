'use client';

interface ResearchGap {
  title: string;
  description: string;
  priority?: 'high' | 'medium' | 'low';
  difficulty?: 'high' | 'medium' | 'low';
  why_it_matters?: string;
  suggested_methods?: string;
  evidence?: string;
  gap_type?: string;
}

interface Props { gaps: ResearchGap[]; }

const priorityConfig = {
  high:   { cls: 'badge-high',   emoji: '🔴', label: 'High Priority' },
  medium: { cls: 'badge-medium', emoji: '🟡', label: 'Medium Priority' },
  low:    { cls: 'badge-low',    emoji: '🟢', label: 'Low Priority' },
};

export default function GapCards({ gaps }: Props) {
  if (!gaps || gaps.length === 0) {
    return (
      <div className="glass" style={{ padding: 48, textAlign: 'center' }}>
        <p style={{ color: '#475569' }}>No research gaps were identified for this topic.</p>
      </div>
    );
  }

  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: 16 }}>
      <p style={{ color: '#64748b', fontSize: 14 }}>
        {gaps.length} unexplored research directions identified from{' '}
        <span style={{ color: '#a78bfa' }}>future-work analysis</span> and{' '}
        <span style={{ color: '#a78bfa' }}>embedding geometry</span>.
      </p>
      {gaps.map((gap, i) => {
        const level = gap.priority ?? gap.difficulty ?? 'medium';
        const cfg = priorityConfig[level] ?? priorityConfig.medium;
        return (
          <div key={i} className="glass" style={{ padding: 24, transition: 'border-color 0.2s' }}
            onMouseEnter={e => (e.currentTarget.style.borderColor = 'rgba(124,58,237,0.4)')}
            onMouseLeave={e => (e.currentTarget.style.borderColor = 'rgba(139,92,246,0.18)')}
          >
            <div style={{ display: 'flex', alignItems: 'flex-start', gap: 16 }}>
              <div style={{ width: 40, height: 40, borderRadius: 12, background: 'rgba(124,58,237,0.15)', display: 'flex', alignItems: 'center', justifyContent: 'center', fontSize: 18, flexShrink: 0 }}>
                {i + 1}
              </div>
              <div style={{ flex: 1 }}>
                <div style={{ display: 'flex', alignItems: 'center', gap: 10, marginBottom: 8, flexWrap: 'wrap' }}>
                  <h3 style={{ fontWeight: 600, color: '#f1f5f9', margin: 0 }}>{gap.title}</h3>
                  <span className={cfg.cls}>{cfg.emoji} {cfg.label}</span>
                  {gap.gap_type && <span style={{ fontSize: 11, color: '#64748b', background: '#1e293b', padding: '2px 8px', borderRadius: 999 }}>{gap.gap_type}</span>}
                </div>
                <p style={{ color: '#94a3b8', fontSize: 14, lineHeight: 1.65, margin: '0 0 8px' }}>{gap.description}</p>
                {gap.why_it_matters && (
                  <p style={{ color: '#64748b', fontSize: 13, lineHeight: 1.6, margin: '0 0 6px' }}>
                    <span style={{ color: '#7c3aed', fontWeight: 500 }}>Why it matters: </span>{gap.why_it_matters}
                  </p>
                )}
                {gap.suggested_methods && (
                  <p style={{ color: '#64748b', fontSize: 13, lineHeight: 1.6, margin: 0 }}>
                    <span style={{ color: '#0891b2', fontWeight: 500 }}>Suggested approach: </span>{gap.suggested_methods}
                  </p>
                )}
              </div>
            </div>
          </div>
        );
      })}
    </div>
  );
}
