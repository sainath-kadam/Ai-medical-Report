import { FormEvent, useState } from 'react';
import { FiLock, FiMoon, FiSun } from 'react-icons/fi';
import { authApi } from '../../api/auth.api';
import { apiErrorMessage } from '../../api/axiosInstance';
import { useTheme } from '../../hooks/useTheme';
import Card from '../../components/common/Card/Card';
import Button from '../../components/common/Button/Button';
import { TextField } from '../../components/common/TextField/TextField';
import './Settings.css';

interface PasswordForm {
  currentPassword: string;
  newPassword: string;
  confirmPassword: string;
}

const EMPTY_FORM: PasswordForm = { currentPassword: '', newPassword: '', confirmPassword: '' };

// Generic account-settings shell. Distinct from Profile (which shows who the
// signed-in user is) — this page is about how the account behaves: security
// (password) and local preferences (appearance).
export default function Settings() {
  const { theme, toggleTheme } = useTheme();
  const [form, setForm] = useState<PasswordForm>(EMPTY_FORM);
  const [isSaving, setIsSaving] = useState(false);
  const [error, setError] = useState('');
  const [message, setMessage] = useState('');

  function update<K extends keyof PasswordForm>(key: K, value: string) {
    setForm((prev) => ({ ...prev, [key]: value }));
  }

  async function handleSubmit(event: FormEvent) {
    event.preventDefault();
    setError('');
    setMessage('');

    if (form.newPassword !== form.confirmPassword) {
      setError('New password and confirmation do not match');
      return;
    }
    if (form.newPassword.length < 8) {
      setError('New password must be at least 8 characters');
      return;
    }

    setIsSaving(true);
    try {
      await authApi.changePassword({ currentPassword: form.currentPassword, newPassword: form.newPassword });
      setMessage('Your password has been updated.');
      setForm(EMPTY_FORM);
    } catch (err) {
      setError(apiErrorMessage(err));
    } finally {
      setIsSaving(false);
    }
  }

  return (
    <div className="settings-page">
      <div className="settings-page__header">
        <h1>Settings</h1>
        <p>Manage your account security and app preferences.</p>
      </div>

      <Card className="settings-page__card">
        <h3>Change password</h3>
        <p className="settings-page__hint">Use a strong password you don&apos;t reuse anywhere else.</p>

        {error && <div className="settings-page__error">{error}</div>}
        {message && <div className="settings-page__success">{message}</div>}

        <form onSubmit={handleSubmit} className="settings-page__form">
          <TextField
            label="Current password"
            type="password"
            icon={<FiLock size={16} />}
            value={form.currentPassword}
            onChange={(e) => update('currentPassword', e.target.value)}
            autoComplete="current-password"
            required
          />
          <TextField
            label="New password"
            type="password"
            icon={<FiLock size={16} />}
            value={form.newPassword}
            onChange={(e) => update('newPassword', e.target.value)}
            hint="At least 8 characters"
            autoComplete="new-password"
            minLength={8}
            required
          />
          <TextField
            label="Confirm new password"
            type="password"
            icon={<FiLock size={16} />}
            value={form.confirmPassword}
            onChange={(e) => update('confirmPassword', e.target.value)}
            autoComplete="new-password"
            required
          />
          <Button type="submit" isLoading={isSaving}>
            Update password
          </Button>
        </form>
      </Card>

      <Card className="settings-page__card">
        <h3>Appearance</h3>
        <p className="settings-page__hint">Choose how Medo AI looks on this device.</p>

        <div className="settings-page__theme-row">
          <div className="settings-page__theme-info">
            {theme === 'dark' ? <FiMoon size={18} /> : <FiSun size={18} />}
            <div>
              <span className="settings-page__theme-label">{theme === 'dark' ? 'Dark mode' : 'Light mode'}</span>
              <span className="settings-page__theme-desc">
                {theme === 'dark' ? 'Easier on the eyes in dim reading rooms.' : 'Best in bright, well-lit environments.'}
              </span>
            </div>
          </div>
          <button
            type="button"
            className="settings-page__theme-switch"
            role="switch"
            aria-checked={theme === 'dark'}
            aria-label="Toggle dark mode"
            onClick={toggleTheme}
          >
            <span className="settings-page__theme-switch-thumb" />
          </button>
        </div>
      </Card>
    </div>
  );
}
