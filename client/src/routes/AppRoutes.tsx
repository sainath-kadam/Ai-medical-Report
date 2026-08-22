import { Navigate, Route, Routes } from 'react-router-dom';
import ProtectedRoute from './ProtectedRoute';
import RoleRoute from './RoleRoute';
import DashboardLayout from '../components/layout/DashboardLayout/DashboardLayout';
import Landing from '../pages/Landing/Landing';
import Login from '../pages/auth/Login/Login';
import Signup from '../pages/auth/Signup/Signup';
import ForgotPassword from '../pages/auth/ForgotPassword/ForgotPassword';
import Dashboard from '../pages/Dashboard/Dashboard';
import Patients from '../pages/Patients/Patients';
import PatientDetail from '../pages/Patients/PatientDetail';
import Studies from '../pages/Studies/Studies';
import StudyDetail from '../pages/Studies/StudyDetail';
import ReportsList from '../pages/ReportsList/ReportsList';
import ReportDetail from '../pages/ReportDetail/ReportDetail';
import Templates from '../pages/Templates/Templates';
import Users from '../pages/Users/Users';
import OrganizationSettings from '../pages/OrganizationSettings/OrganizationSettings';
import Billing from '../pages/Billing/Billing';
import AuditLogs from '../pages/AuditLogs/AuditLogs';
import Settings from '../pages/Settings/Settings';
import Profile from '../pages/Profile/Profile';
import CreateOrganization from '../pages/Platform/CreateOrganization';
import NotFound from '../pages/NotFound/NotFound';
import Loader from '../components/common/Loader/Loader';
import { useAuth } from '../hooks/useAuth';

/** `/dashboard` renders the clinical Dashboard for org_admin/doctor — but system_admin has
 * no organization (CONTRACTS.md §2a), so Dashboard's own data calls would just 403. Send it
 * straight to the one page that's actually relevant to it instead. */
function Home() {
  const { user } = useAuth();
  if (user?.role === 'system_admin') {
    return <Navigate to="/platform/organizations" replace />;
  }
  return <Dashboard />;
}

/** `/` is the public marketing page — logged out, it's the one page anyone (no account
 * needed) can see; logged in, there's nothing for it to show, so it hands off to the real
 * app at `/dashboard` instead of rendering both at the same path. */
function RootGate() {
  const { isAuthenticated, isLoading } = useAuth();
  if (isLoading) {
    return (
      <div className="app-loading-screen">
        <Loader size="lg" label="Loading MedScan AI…" />
      </div>
    );
  }
  if (isAuthenticated) {
    return <Navigate to="/dashboard" replace />;
  }
  return <Landing />;
}

export default function AppRoutes() {
  return (
    <Routes>
      <Route path="/" element={<RootGate />} />
      <Route path="/login" element={<Login />} />
      <Route path="/signup" element={<Signup />} />
      <Route path="/forgot-password" element={<ForgotPassword />} />

      <Route element={<ProtectedRoute />}>
        <Route element={<DashboardLayout />}>
          <Route path="/dashboard" element={<Home />} />

          <Route path="/patients" element={<Patients />} />
          <Route path="/patients/:id" element={<PatientDetail />} />

          <Route path="/studies" element={<Studies />} />
          <Route path="/studies/:id" element={<StudyDetail />} />

          <Route path="/reports" element={<ReportsList />} />
          <Route path="/reports/:id" element={<ReportDetail />} />

          <Route path="/billing" element={<Billing />} />
          <Route path="/profile" element={<Profile />} />
          <Route path="/settings" element={<Settings />} />

          <Route element={<RoleRoute roles={['org_admin']} />}>
            <Route path="/templates" element={<Templates />} />
            <Route path="/users" element={<Users />} />
            <Route path="/organization" element={<OrganizationSettings />} />
            <Route path="/audit-logs" element={<AuditLogs />} />
          </Route>

          <Route element={<RoleRoute roles={['system_admin']} />}>
            <Route path="/platform/organizations" element={<CreateOrganization />} />
          </Route>
        </Route>
      </Route>

      <Route path="/404" element={<NotFound />} />
      <Route path="*" element={<Navigate to="/404" replace />} />
    </Routes>
  );
}
