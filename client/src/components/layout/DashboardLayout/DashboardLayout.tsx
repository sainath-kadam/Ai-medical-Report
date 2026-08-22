import { useState } from 'react';
import { Outlet } from 'react-router-dom';
import Topbar from '../Topbar/Topbar';
import Sidebar from '../Sidebar/Sidebar';
import './DashboardLayout.css';

/** Page shell for every authenticated route: top navigation on desktop
 *  (Topbar), a slide-in drawer on mobile (Sidebar), and the routed page
 *  content in between. See Topbar.css / Sidebar.css for the breakpoint. */
export default function DashboardLayout() {
  const [sidebarOpen, setSidebarOpen] = useState(false);

  return (
    <div className="dashboard-layout">
      <Topbar onMenuClick={() => setSidebarOpen(true)} />
      <Sidebar isOpen={sidebarOpen} onClose={() => setSidebarOpen(false)} />
      <main className="dashboard-layout__content">
        <div className="dashboard-layout__inner">
          <Outlet />
        </div>
      </main>
    </div>
  );
}
