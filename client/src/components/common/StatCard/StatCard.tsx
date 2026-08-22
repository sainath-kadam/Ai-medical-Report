import { ReactNode } from 'react';
import Card from '../Card/Card';
import './StatCard.css';

interface StatCardProps {
  label: string;
  value: string | number;
  icon?: ReactNode;
  tone?: 'primary' | 'accent' | 'success' | 'warning';
  hint?: string;
}

export default function StatCard({ label, value, icon, tone = 'primary', hint }: StatCardProps) {
  return (
    <Card className="stat-card">
      <div className={`stat-card__icon stat-card__icon--${tone}`}>{icon}</div>
      <div className="stat-card__body">
        <span className="stat-card__label">{label}</span>
        <span className="stat-card__value">{value}</span>
        {hint && <span className="stat-card__hint">{hint}</span>}
      </div>
    </Card>
  );
}
