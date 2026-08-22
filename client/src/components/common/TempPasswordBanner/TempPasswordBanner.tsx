import { useState } from 'react';
import { FiCheck, FiCopy, FiShield } from 'react-icons/fi';
import Button from '../Button/Button';
import './TempPasswordBanner.css';

interface TempPasswordBannerProps {
  password: string;
  /** e.g. "Dr. Priya Nair" — who this password is for, used in the copy note. */
  recipientName: string;
}

/** A one-time "here's the temporary password, copy it now" banner — shown right after
 * inviting a user (`Users.tsx`) or having a system_admin create a new organization's
 * first admin (`Platform/CreateOrganization.tsx`). No SMTP is configured (CONTRACTS.md
 * §2/§8), so this is the only place the password is ever shown. */
export default function TempPasswordBanner({ password, recipientName }: TempPasswordBannerProps) {
  const [copied, setCopied] = useState(false);

  async function handleCopy() {
    try {
      await navigator.clipboard.writeText(password);
      setCopied(true);
      window.setTimeout(() => setCopied(false), 2000);
    } catch {
      // Clipboard API can be unavailable (permissions / non-secure context) -- the
      // password is still shown as selectable text, so it can be copied manually either way.
    }
  }

  return (
    <div className="temp-password-banner">
      <FiShield size={18} className="temp-password-banner__icon" />
      <div className="temp-password-banner__body">
        <p className="temp-password-banner__title">Temporary password</p>
        <p className="temp-password-banner__note">
          This is the <strong>only time</strong> this password will be shown. Copy it now and share it with{' '}
          {recipientName} through a secure channel.
        </p>
        <div className="temp-password-banner__row">
          <code className="temp-password-banner__value">{password}</code>
          <Button size="sm" variant="outline" icon={copied ? <FiCheck size={14} /> : <FiCopy size={14} />} onClick={handleCopy}>
            {copied ? 'Copied' : 'Copy'}
          </Button>
        </div>
      </div>
    </div>
  );
}
