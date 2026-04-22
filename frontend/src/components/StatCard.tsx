'use client';

interface Props {
  icon: string;   // emoji
  label: string;
  value: number | string;
  color: string;
  subtext?: string;
}

export default function StatCard({ icon, label, value, color, subtext }: Props) {
  return (
    <div className="glass" style={{ padding: '20px 22px', borderTop: `2px solid ${color}40`, transition: 'border-color 0.2s, transform 0.2s' }}
      onMouseEnter={e => { e.currentTarget.style.borderTopColor = color; e.currentTarget.style.transform = 'translateY(-2px)'; }}
      onMouseLeave={e => { e.currentTarget.style.borderTopColor = color + '40'; e.currentTarget.style.transform = 'translateY(0)'; }}
    >
      <div style={{ fontSize: 22, marginBottom: 8 }}>{icon}</div>
      <div style={{ fontSize: 32, fontWeight: 800, color: '#fff', lineHeight: 1 }}>{value}</div>
      <div style={{ fontSize: 11, color, textTransform: 'uppercase', letterSpacing: '0.08em', fontWeight: 600, marginTop: 6 }}>{label}</div>
      {subtext && <div style={{ fontSize: 11, color: '#334155', marginTop: 4 }}>{subtext}</div>}
    </div>
  );
}
