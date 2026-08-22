import { Navigate, Outlet } from 'react-router-dom';
import { useAuth } from '../hooks/useAuth';
import Loader from '../components/common/Loader/Loader';
import { SKIP_AUTH } from '../utils/devFlags';

export default function ProtectedRoute() {
  const { isAuthenticated, isLoading } = useAuth();

  if (SKIP_AUTH) {
    return <Outlet />;
  }

  if (isLoading) {
    return (
      <div className="app-loading-screen">
        <Loader size="lg" label="Loading MedScan AI…" />
      </div>
    );
  }

  if (!isAuthenticated) {
    return <Navigate to="/login" replace />;
  }

  return <Outlet />;
}
