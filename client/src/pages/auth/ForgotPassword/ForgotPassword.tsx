import { FormEvent, useState } from 'react';
import { Link } from 'react-router-dom';
import { FiMail } from 'react-icons/fi';
import { authApi } from '../../../api/auth.api';
import { TextField } from '../../../components/common/TextField/TextField';
import Button from '../../../components/common/Button/Button';
import ThemeToggle from '../../../components/common/ThemeToggle/ThemeToggle';
import '../Login/Login.css';

export default function ForgotPassword() {
  const [email, setEmail] = useState('');
  const [isSubmitting, setIsSubmitting] = useState(false);
  const [isSubmitted, setIsSubmitted] = useState(false);

  async function handleSubmit(event: FormEvent) {
    event.preventDefault();
    setIsSubmitting(true);
    try {
      await authApi.forgotPassword(email);
    } catch {
      // Deliberately ignored: whether the account exists, the email fails to send,
      // or anything else goes wrong, the user always sees the same generic message
      // below — never confirm or deny that an account exists for this address.
    } finally {
      setIsSubmitting(false);
      setIsSubmitted(true);
    }
  }

  return (
    <div className="auth-page">
      <ThemeToggle variant="fixed" />
      <div className="auth-card">
        <div className="auth-card__brand">
          <img src="/LogoMedicalAI2.jpg" alt="" className="auth-card__brand-mark" />
          <span>
            Medo <strong>AI</strong>
          </span>
        </div>
        <h1 className="auth-card__title">Forgot your password?</h1>
        <p className="auth-card__subtitle">Enter the email on your account and we&apos;ll send you a link to reset it.</p>

        {isSubmitted ? (
          <div className="auth-card__success">
            If an account exists for that email, a reset link has been sent.
          </div>
        ) : (
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
            <Button type="submit" fullWidth size="lg" isLoading={isSubmitting}>
              Send reset link
            </Button>
          </form>
        )}

        <p className="auth-card__footer">
          Remembered your password? <Link to="/login">Back to sign in</Link>
        </p>
      </div>
    </div>
  );
}
