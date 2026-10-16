import './Loader.css';

interface LoaderProps {
  size?: 'sm' | 'md' | 'lg';
  label?: string;
}

export default function Loader({ size = 'md', label }: LoaderProps) {
  return (
    <div className="loader" role="status" aria-live="polite">
      {/* An "AI orb": a rotating spectrum ring, plus (md/lg only) a breathing core and a
          counter-rotating inner arc. Purely decorative -- the label carries the meaning. */}
      <span className={`loader__spinner loader__spinner--${size}`} aria-hidden="true">
        <span className="loader__ring" />
        {size !== 'sm' && <span className="loader__arc" />}
        {size !== 'sm' && <span className="loader__core" />}
      </span>
      {label && <span className="loader__label">{label}</span>}
    </div>
  );
}
