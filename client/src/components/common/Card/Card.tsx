import { HTMLAttributes, ReactNode } from 'react';
import './Card.css';

interface CardProps extends HTMLAttributes<HTMLDivElement> {
  children: ReactNode;
  padded?: boolean;
}

export default function Card({ children, padded = true, className = '', ...rest }: CardProps) {
  return (
    <div className={`card ${padded ? 'card--padded' : ''} ${className}`} {...rest}>
      {children}
    </div>
  );
}
