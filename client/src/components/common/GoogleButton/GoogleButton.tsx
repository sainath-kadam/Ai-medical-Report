import { useEffect, useRef } from 'react';
import './GoogleButton.css';

interface GoogleButtonProps {
  onCredential: (idToken: string) => void;
}

/** Thin wrapper around Google Identity Services' hosted button (loaded via the
 *  <script> tag in index.html). Google renders and styles the button itself
 *  into the target div — there is nothing to theme on our side. */
export default function GoogleButton({ onCredential }: GoogleButtonProps) {
  const containerRef = useRef<HTMLDivElement>(null);
  const clientId = import.meta.env.VITE_GOOGLE_CLIENT_ID;

  useEffect(() => {
    if (!clientId || !window.google || !containerRef.current) return;
    window.google.accounts.id.initialize({
      client_id: clientId,
      callback: (response) => onCredential(response.credential),
    });
    window.google.accounts.id.renderButton(containerRef.current, {
      theme: 'outline',
      size: 'large',
      width: 320,
      text: 'continue_with',
    });
  }, [clientId, onCredential]);

  if (!clientId) {
    return <p className="google-button-hint">Google sign-in isn&apos;t configured on this deployment yet.</p>;
  }

  return <div className="google-button" ref={containerRef} />;
}
