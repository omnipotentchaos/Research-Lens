'use client';

import { getGraphUrl } from '@/lib/api';

interface Props { jobId: string; }

const LEGEND = [
  { shape: 'circle',  color: '#38bdf8', size: 14, label: 'Paper',            desc: 'A research paper. Larger = more cited (more influential).' },
  { shape: 'diamond', color: '#f97316', size: 14, label: 'Method / Technique', desc: 'An ML method or technique used across papers (e.g. LoRA, BERT).' },
  { shape: 'square',  color: '#10b981', size: 14, label: 'Dataset / Benchmark', desc: 'A dataset or benchmark used for training or evaluation.' },
  { shape: 'star',    color: '#fbbf24', size: 16, label: 'Seminal paper',     desc: 'The most highly cited / foundational paper in this topic.' },
];

export default function KnowledgeGraph({ jobId }: Props) {
  const url = getGraphUrl(jobId);
  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: 16 }}>

      {/* Explainer banner */}
      <div className="glass" style={{ padding: '12px 18px', display: 'flex', alignItems: 'flex-start', gap: 12, borderLeft: '3px solid #0891b2' }}>
        <span style={{ fontSize: 20, flexShrink: 0 }}>🕸️</span>
        <div>
          <div style={{ fontSize: 13, fontWeight: 600, color: '#67e8f9', marginBottom: 3 }}>What does this graph show?</div>
          <div style={{ fontSize: 12, color: '#64748b', lineHeight: 1.7 }}>
            This is a <strong style={{ color: '#94a3b8' }}>citation + method co-occurrence graph</strong>. Papers are <strong style={{ color: '#94a3b8' }}>nodes</strong>; edges connect papers that share methods or cite each other.
            The <strong style={{ color: '#fbbf24' }}>largest / brightest node</strong> is the most influential paper (seminal work).
            This helps you spot <strong style={{ color: '#94a3b8' }}>which papers are central to the field</strong> and which methods appear across multiple works.
          </div>
        </div>
      </div>

      {/* Legend */}
      <div className="glass" style={{ padding: '12px 18px' }}>
        <div style={{ fontSize: 11, fontWeight: 700, color: '#64748b', textTransform: 'uppercase', letterSpacing: '0.1em', marginBottom: 10 }}>Node Legend</div>
        <div style={{ display: 'flex', flexWrap: 'wrap', gap: 20 }}>
          {LEGEND.map(({ shape, color, size, label, desc }) => (
            <div key={label} style={{ display: 'flex', alignItems: 'center', gap: 10 }} title={desc}>
              <div style={{
                width: size, height: size, flexShrink: 0,
                background: color,
                borderRadius: shape === 'circle' ? '50%' : shape === 'square' ? 3 : shape === 'star' ? 0 : 3,
                transform: shape === 'diamond' ? 'rotate(45deg)' : 'none',
                clipPath: shape === 'star' ? 'polygon(50% 0%, 61% 35%, 98% 35%, 68% 57%, 79% 91%, 50% 70%, 21% 91%, 32% 57%, 2% 35%, 39% 35%)' : 'none',
                boxShadow: `0 0 8px ${color}80`,
              }} />
              <div>
                <div style={{ fontSize: 12, color: '#cbd5e1', fontWeight: 500 }}>{label}</div>
                <div style={{ fontSize: 11, color: '#475569' }}>{desc}</div>
              </div>
            </div>
          ))}
        </div>
      </div>

      {/* Graph iframe */}
      <div className="glass" style={{ overflow: 'hidden', height: 520 }}>
        <div style={{ padding: '10px 18px', borderBottom: '1px solid rgba(8,145,178,0.15)', display: 'flex', alignItems: 'center', justifyContent: 'space-between', background: 'rgba(15,22,41,0.5)' }}>
          <div style={{ display: 'flex', gap: 20 }}>
            {['🖱️ Drag to pan', '⚲ Scroll to zoom', '● Click node for details'].map(tip => (
              <span key={tip} style={{ fontSize: 11, color: '#334155' }}>{tip}</span>
            ))}
          </div>
          <a href={url} target="_blank" rel="noopener noreferrer"
            style={{ fontSize: 12, color: '#0891b2', textDecoration: 'none', fontWeight: 500 }}>
            Open fullscreen ↗
          </a>
        </div>
        <iframe
          src={url}
          title="Knowledge Graph"
          style={{ width: '100%', height: 'calc(100% - 41px)', border: 'none', background: '#080b14' }}
        />
      </div>
    </div>
  );
}
