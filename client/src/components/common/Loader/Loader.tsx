import './Loader.css';

interface LoaderProps {
  size?: 'sm' | 'md' | 'lg';
  label?: string;
}

export default function Loader({ size = 'md', label }: LoaderProps) {
  return (
    <div className="loader" role="status" aria-live="polite">
      <span className={`loader__spinner loader__spinner--${size}`} />
      {label && <span className="loader__label">{label}</span>}
    </div>
  );
}
