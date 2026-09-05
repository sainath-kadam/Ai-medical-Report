import { FiMoon, FiSun } from 'react-icons/fi';
import { useTheme } from '../../../hooks/useTheme';
import './ThemeToggle.css';

interface ThemeToggleProps {
  // 'inline' matches Topbar's compact icon button, meant to sit among other icon
  // buttons inside an existing toolbar. 'fixed' pins itself to the viewport's top-right
  // corner with its own visible surface/border, for pages with no toolbar to live in
  // (Landing, and the pre-login auth pages) -- so a visitor can pick a theme before
  // ever signing in, not just after (previously the only way in was system preference).
  variant?: 'inline' | 'fixed';
}

export default function ThemeToggle({ variant = 'inline' }: ThemeToggleProps) {
  const { theme, toggleTheme } = useTheme();
  return (
    <button
      type="button"
      className={`theme-toggle theme-toggle--${variant}`}
      onClick={toggleTheme}
      aria-label="Toggle color theme"
      title={theme === 'dark' ? 'Switch to light mode' : 'Switch to dark mode'}
    >
      {theme === 'dark' ? <FiSun size={18} /> : <FiMoon size={18} />}
    </button>
  );
}
