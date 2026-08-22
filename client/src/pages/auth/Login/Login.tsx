import { FormEvent, useState } from 'react';
import { Link, useNavigate } from 'react-router-dom';
import { FiLock, FiMail } from 'react-icons/fi';
import { useAuth } from '../../../hooks/useAuth';
import { TextField } from '../../../components/common/TextField/TextField';
import Button from '../../../components/common/Button/Button';
import GoogleButton from '../../../components/common/GoogleButton/GoogleButton';
import { apiErrorMessage } from '../../../api/axiosInstance';
import './Login.css';

export default function Login() {
  const { login, loginWithGoogle } = useAuth();
  const navigate = useNavigate();
  const [email, setEmail] = useState('');
  const [password, setPassword] = useState('');
  const [error, setError] = useState('');
  const [isSubmitting, setIsSubmitting] = useState(false);

  async function handleSubmit(event: FormEvent) {
    event.preventDefault();
    setError('');
    setIsSubmitting(true);
    try {
      await login(email, password);
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
      await loginWithGoogle(idToken);
      navigate('/dashboard');
    } catch (err) {
      setError(apiErrorMessage(err));
    }
  }

  return (
    <div className="auth-page">
      <div className="auth-card">
        <div className="auth-card__brand">
          <span className="auth-card__brand-mark">MS</span>
          <span>
            MedScan <strong>AI</strong>
          </span>
        </div>
        <h1 className="auth-card__title">Welcome back</h1>
        <p className="auth-card__subtitle">Sign in to review your organization&apos;s imaging reports.</p>

        {error && <div className="auth-card__error">{error}</div>}

        <form onSubmit={handleSubmit} className="auth-card__form">
          <TextField
            label="Email"
            type="email"
            icon={<FiMail size={16} />}
            value={email}
            onChange={(e) => setEmail(e.target.value)}
            required
            autoFocus
          />
          <TextField
            label="Password"
            type="password"
            icon={<FiLock size={16} />}
            value={password}
            onChange={(e) => setPassword(e.target.value)}
            required
          />
          <Button type="submit" fullWidth size="lg" isLoading={isSubmitting}>
            Sign in
          </Button>
        </form>

        <div className="auth-card__divider">
          <span>or</span>
        </div>
        <GoogleButton onCredential={handleGoogle} />

        <p className="auth-card__footer">
          Don&apos;t have an organization yet? <Link to="/signup">Create one</Link>
        </p>
      </div>
    </div>
  );
}
