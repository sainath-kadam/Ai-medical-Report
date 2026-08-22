import { Navigate, Outlet } from 'react-router-dom';
import { useAuth } from '../hooks/useAuth';
import { UserRole } from '../types';
import { SKIP_AUTH } from '../utils/devFlags';

interface RoleRouteProps {
  roles: UserRole[];
}

/** Gates an entire route subtree to specific roles (e.g. Users/Organization/Audit Logs
 *  are org_admin-only). Use nested under <ProtectedRoute> so auth is already resolved. */
export default function RoleRoute({ roles }: RoleRouteProps) {
  const { user } = useAuth();
  if (SKIP_AUTH) {
    return <Outlet />;
  }
  if (!user || !roles.includes(user.role)) {
    return <Navigate to="/dashboard" replace />;
  }
  return <Outlet />;
}
