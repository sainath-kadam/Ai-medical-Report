import './StatusBadge.css';

interface StatusBadgeProps {
  label: string;
  tone?: 'info' | 'warning' | 'success' | 'danger' | 'muted';
}

export default function StatusBadge({ label, tone = 'muted' }: StatusBadgeProps) {
  return <span className={`status-badge status-badge--${tone}`}>{label}</span>;
}
