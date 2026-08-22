import { FiMail, FiMoon, FiShield, FiSun, FiUser } from 'react-icons/fi';
import Card from '../../components/common/Card/Card';
import { useAuth } from '../../hooks/useAuth';
import { useTheme } from '../../hooks/useTheme';
import { UserRole } from '../../types';
import { getInitial } from '../../utils/formatName';
import './Profile.css';

const ROLE_LABELS: Record<UserRole, string> = {
  org_admin: 'Organization Admin',
  doctor: 'Doctor / Radiologist',
  // Unlike the exhaustiveness-only system_admin entries elsewhere (e.g. Users.tsx, whose
  // organization-scoped list can never include one), this one is reachable: `/profile`
  // isn't RoleRoute-gated, so a system_admin viewing their own profile hits this line.
  system_admin: 'Platform Admin',
};

export default function Profile() {
  const { user, organization } = useAuth();
  const { theme, toggleTheme } = useTheme();

  if (!user) return null;

  return (
    <div className="profile-page">
      <div className="profile-page__header">
        <h1>Profile</h1>
        <p>Your account details for this organization.</p>
      </div>

      <Card className="profile-page__card">
        <div className="profile-page__avatar">{getInitial(user.name)}</div>
        <div>
          <h2>{user.name}</h2>
          <p>{organization?.name}</p>
        </div>
      </Card>

      <Card className="profile-page__card profile-page__details">
        <div className="profile-page__row">
          <FiUser size={16} />
          <div>
            <span className="profile-page__label">Full name</span>
            <span>{user.name}</span>
          </div>
        </div>
        <div className="profile-page__row">
          <FiMail size={16} />
          <div>
            <span className="profile-page__label">Email</span>
            <span>{user.email}</span>
          </div>
        </div>
        <div className="profile-page__row">
          <FiShield size={16} />
          <div>
            <span className="profile-page__label">Role</span>
            <span className="profile-page__role">{ROLE_LABELS[user.role]}</span>
          </div>
        </div>
        <div className="profile-page__row">
          {theme === 'dark' ? <FiMoon size={16} /> : <FiSun size={16} />}
          <div>
            <span className="profile-page__label">Appearance</span>
            <button className="profile-page__theme-toggle" onClick={toggleTheme}>
              Switch to {theme === 'dark' ? 'light' : 'dark'} mode
            </button>
          </div>
        </div>
      </Card>
    </div>
  );
}
