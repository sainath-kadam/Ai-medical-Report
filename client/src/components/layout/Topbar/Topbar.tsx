import { useRef, useState } from 'react';
import { NavLink, useLocation } from 'react-router-dom';
import { FiMenu, FiSun, FiMoon, FiLogOut, FiUser, FiSettings, FiChevronDown, FiShield } from 'react-icons/fi';
import { adminNavItems, primaryNavItems } from '../navItems';
import { useAuth } from '../../../hooks/useAuth';
import { useTheme } from '../../../hooks/useTheme';
import { useClickOutside } from '../../../hooks/useClickOutside';
import { getInitial } from '../../../utils/formatName';
import './Topbar.css';

interface TopbarProps {
  onMenuClick: () => void;
}

/** Renders the horizontal primary navigation on desktop. On narrow viewports the
 *  links are hidden by CSS and this collapses to logo + hamburger (which opens
 *  the Sidebar drawer) + avatar — see Topbar.css for the breakpoint. */
export default function Topbar({ onMenuClick }: TopbarProps) {
  const { user, organization, logout } = useAuth();
  const { theme, toggleTheme } = useTheme();
  const location = useLocation();
  const [menuOpen, setMenuOpen] = useState(false);
  const [adminMenuOpen, setAdminMenuOpen] = useState(false);
  const menuRef = useRef<HTMLDivElement>(null);
  const adminMenuRef = useRef<HTMLDivElement>(null);
  useClickOutside(menuRef, () => setMenuOpen(false), menuOpen);
  useClickOutside(adminMenuRef, () => setAdminMenuOpen(false), adminMenuOpen);

  const adminItems = adminNavItems(user?.role);
  const isAdminSectionActive = adminItems.some((item) => location.pathname.startsWith(item.to));

  return (
    <header className="topbar">
      <div className="topbar__left">
        <button className="topbar__menu-btn" onClick={onMenuClick} aria-label="Open navigation menu">
          <FiMenu size={22} />
        </button>
        <NavLink to="/dashboard" className="topbar__brand">
          <span className="topbar__brand-mark">MS</span>
          <span className="topbar__brand-name">
            MedScan <strong>AI</strong>
          </span>
        </NavLink>
      </div>

      <nav className="topbar__nav" aria-label="Primary">
        {primaryNavItems(user?.role).map((item) => (
          <NavLink
            key={item.to}
            to={item.to}
            end={item.end}
            className={({ isActive }) => `topbar__link ${isActive ? 'topbar__link--active' : ''}`}
          >
            <item.icon size={17} />
            <span>{item.label}</span>
          </NavLink>
        ))}

        {adminItems.length > 0 && (
          <div className="topbar__admin" ref={adminMenuRef}>
            <button
              type="button"
              className={`topbar__link topbar__admin-trigger ${isAdminSectionActive ? 'topbar__link--active' : ''}`}
              onClick={() => setAdminMenuOpen((v) => !v)}
              aria-haspopup="true"
              aria-expanded={adminMenuOpen}
            >
              <FiShield size={17} />
              <span>Admin</span>
              <FiChevronDown size={13} className={`topbar__admin-chevron ${adminMenuOpen ? 'topbar__admin-chevron--open' : ''}`} />
            </button>
            {adminMenuOpen && (
              <div className="topbar__dropdown topbar__dropdown--admin">
                {adminItems.map((item) => (
                  <NavLink
                    key={item.to}
                    to={item.to}
                    end={item.end}
                    onClick={() => setAdminMenuOpen(false)}
                    className={({ isActive }) =>
                      `topbar__dropdown-item ${isActive ? 'topbar__dropdown-item--active' : ''}`
                    }
                  >
                    <item.icon size={15} />
                    {item.label}
                  </NavLink>
                ))}
              </div>
            )}
          </div>
        )}
      </nav>

      <div className="topbar__right">
        {organization && <span className="topbar__org-name">{organization.name}</span>}
        <button className="topbar__icon-btn" onClick={toggleTheme} aria-label="Toggle color theme">
          {theme === 'dark' ? <FiSun size={18} /> : <FiMoon size={18} />}
        </button>
        <div className="topbar__user" ref={menuRef}>
          <button className="topbar__user-btn" onClick={() => setMenuOpen((v) => !v)} aria-label="Open account menu">
            <span className="topbar__avatar">{getInitial(user?.name)}</span>
            <FiChevronDown size={14} />
          </button>
          {menuOpen && (
            <div className="topbar__dropdown">
              <div className="topbar__dropdown-header">
                <strong>{user?.name}</strong>
                <span>{user?.email}</span>
              </div>
              <NavLink to="/profile" className="topbar__dropdown-item" onClick={() => setMenuOpen(false)}>
                <FiUser size={15} /> Profile
              </NavLink>
              <NavLink to="/settings" className="topbar__dropdown-item" onClick={() => setMenuOpen(false)}>
                <FiSettings size={15} /> Settings
              </NavLink>
              <button className="topbar__dropdown-item topbar__dropdown-item--danger" onClick={logout}>
                <FiLogOut size={15} /> Log out
              </button>
            </div>
          )}
        </div>
      </div>
    </header>
  );
}
