import { NavLink } from 'react-router-dom';
import { FiX, FiLogOut } from 'react-icons/fi';
import { adminNavItems, primaryNavItems } from '../navItems';
import { useAuth } from '../../../hooks/useAuth';
import { getInitial } from '../../../utils/formatName';
import './Sidebar.css';

interface SidebarProps {
  isOpen: boolean;
  onClose: () => void;
}

/** Mobile-only slide-in drawer carrying the same primary navigation the
 *  Topbar shows horizontally on desktop (see Topbar.css breakpoint). */
export default function Sidebar({ isOpen, onClose }: SidebarProps) {
  const { user, logout } = useAuth();

  return (
    <>
      <div
        className={`sidebar-backdrop ${isOpen ? 'sidebar-backdrop--visible' : ''}`}
        onClick={onClose}
        aria-hidden="true"
      />
      <aside className={`sidebar ${isOpen ? 'sidebar--open' : ''}`} aria-label="Mobile navigation">
        <div className="sidebar__header">
          <span className="sidebar__brand">
            MedScan <strong>AI</strong>
          </span>
          <button className="sidebar__close" onClick={onClose} aria-label="Close navigation menu">
            <FiX size={20} />
          </button>
        </div>

        {user && (
          <div className="sidebar__user">
            <span className="sidebar__avatar">{getInitial(user.name)}</span>
            <div>
              <strong>{user.name}</strong>
              <span>{user.email}</span>
            </div>
          </div>
        )}

        <nav className="sidebar__nav">
          {primaryNavItems(user?.role).map((item) => (
            <NavLink
              key={item.to}
              to={item.to}
              end={item.end}
              onClick={onClose}
              className={({ isActive }) => `sidebar__link ${isActive ? 'sidebar__link--active' : ''}`}
            >
              <item.icon size={18} />
              <span>{item.label}</span>
            </NavLink>
          ))}

          {adminNavItems(user?.role).length > 0 && (
            <>
              <span className="sidebar__section-label">Admin</span>
              {adminNavItems(user?.role).map((item) => (
                <NavLink
                  key={item.to}
                  to={item.to}
                  end={item.end}
                  onClick={onClose}
                  className={({ isActive }) => `sidebar__link ${isActive ? 'sidebar__link--active' : ''}`}
                >
                  <item.icon size={18} />
                  <span>{item.label}</span>
                </NavLink>
              ))}
            </>
          )}
        </nav>

        <button className="sidebar__logout" onClick={logout}>
          <FiLogOut size={16} /> Log out
        </button>
      </aside>
    </>
  );
}
