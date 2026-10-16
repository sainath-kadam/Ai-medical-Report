import { useEffect, useRef, useState } from 'react';
import { Outlet, useLocation } from 'react-router-dom';
import Topbar from '../Topbar/Topbar';
import Sidebar from '../Sidebar/Sidebar';
import ReadOnlyBanner from '../ReadOnlyBanner/ReadOnlyBanner';
import './DashboardLayout.css';

/** Page shell for every authenticated route: top navigation on desktop
 *  (Topbar), a slide-in drawer on mobile (Sidebar), and the routed page
 *  content in between. See Topbar.css / Sidebar.css for the breakpoint. */
export default function DashboardLayout() {
  const [sidebarOpen, setSidebarOpen] = useState(false);
  const contentRef = useRef<HTMLElement>(null);
  const { pathname } = useLocation();

  // Only <main> scrolls (the Topbar stays fixed above it), so keyboard scrolling --
  // Space / PageDown / arrows -- needs focus inside it. Move focus there on every page
  // change, without jumping the scroll position.
  useEffect(() => {
    if (!contentRef.current?.contains(document.activeElement)) {
      contentRef.current?.focus({ preventScroll: true });
    }
  }, [pathname]);

  return (
    <div className="dashboard-layout">
      <Topbar onMenuClick={() => setSidebarOpen(true)} />
      <Sidebar isOpen={sidebarOpen} onClose={() => setSidebarOpen(false)} />
      <main className="dashboard-layout__content" ref={contentRef} tabIndex={-1}>
        <div className="dashboard-layout__inner">
          <ReadOnlyBanner />
          <Outlet />
        </div>
      </main>
    </div>
  );
}
