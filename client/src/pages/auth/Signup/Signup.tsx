import { FormEvent, useState } from 'react';
import { Link, useNavigate } from 'react-router-dom';
import { FiBriefcase, FiLock, FiMail, FiUser } from 'react-icons/fi';
import { useAuth } from '../../../hooks/useAuth';
import { TextField } from '../../../components/common/TextField/TextField';
import Button from '../../../components/common/Button/Button';
import GoogleButton from '../../../components/common/GoogleButton/GoogleButton';
import ThemeToggle from '../../../components/common/ThemeToggle/ThemeToggle';
import { apiErrorMessage } from '../../../api/axiosInstance';
import '../Login/Login.css';

export default function Signup() {
  const { signup, loginWithGoogle } = useAuth();
  const navigate = useNavigate();
  const [form, setForm] = useState({ name: '', email: '', password: '', organizationName: '' });
  const [error, setError] = useState('');
  const [isSubmitting, setIsSubmitting] = useState(false);

  function update<K extends keyof typeof form>(key: K, value: string) {
    setForm((prev) => ({ ...prev, [key]: value }));
  }

  async function handleSubmit(event: FormEvent) {
    event.preventDefault();
    setError('');
    setIsSubmitting(true);
    try {
      await signup(form);
      navigate('/dashboard');
    } catch (err) {
      setError(apiErrorMessage(err));
    } finally {
      setIsSubmitting(false);
    }
  }

  async function handleGoogle(idToken: string) {
    setError('');
    try {
      await loginWithGoogle(idToken, form.organizationName || undefined);
      navigate('/dashboard');
    } catch (err) {
      setError(apiErrorMessage(err));
    }
  }

  return (
    <div className="auth-page">
      <ThemeToggle variant="fixed" />
      <div className="auth-card">
        <div className="auth-card__brand">
          <span className="auth-card__brand-mark">MS</span>
          <span>
            MedScan <strong>AI</strong>
          </span>
        </div>
        <h1 className="auth-card__title">Create your organization</h1>
        <p className="auth-card__subtitle">
          Set up a workspace for your clinic or hospital — you can invite teammates afterward.
        </p>

        {error && <div className="auth-card__error">{error}</div>}

        <form onSubmit={handleSubmit} className="auth-card__form">
          <TextField
            label="Organization name"
            icon={<FiBriefcase size={16} />}
            value={form.organizationName}
            onChange={(e) => update('organizationName', e.target.value)}
            placeholder="Sunrise Radiology Clinic"
            required
          />
          <TextField
            label="Your full name"
            icon={<FiUser size={16} />}
            value={form.name}
            onChange={(e) => update('name', e.target.value)}
            required
          />
          <TextField
            label="Email"
            type="email"
            icon={<FiMail size={16} />}
            value={form.email}
            onChange={(e) => update('email', e.target.value)}
            required
          />
          <TextField
            label="Password"
            type="password"
            icon={<FiLock size={16} />}
            value={form.password}
            onChange={(e) => update('password', e.target.value)}
            hint="At least 8 characters"
            minLength={8}
            required
          />
          <Button type="submit" fullWidth size="lg" isLoading={isSubmitting}>
            Create organization
          </Button>
        </form>

        <div className="auth-card__divider">
          <span>or</span>
        </div>
        <GoogleButton onCredential={handleGoogle} />

        <p className="auth-card__footer">
          Already have an account? <Link to="/login">Sign in</Link>
        </p>
      </div>
    </div>
  );
}
