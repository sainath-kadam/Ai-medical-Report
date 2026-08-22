import { useEffect, useState } from 'react';
import { Link, useNavigate, useSearchParams } from 'react-router-dom';
import {
  FiActivity,
  FiArrowLeft,
  FiCheckCircle,
  FiClock,
  FiCpu,
  FiFileText,
  FiPlus,
  FiTrendingUp,
  FiUploadCloud,
} from 'react-icons/fi';
import { dashboardApi } from '../../api/dashboard.api';
import { reportApi } from '../../api/report.api';
import { apiErrorMessage } from '../../api/axiosInstance';
import { DashboardStats, Report, StudyIntakeResult } from '../../types';
import StatCard from '../../components/common/StatCard/StatCard';
import Card from '../../components/common/Card/Card';
import Button from '../../components/common/Button/Button';
import Loader from '../../components/common/Loader/Loader';
import EmptyState from '../../components/common/EmptyState/EmptyState';
import ReportCard from '../../components/reports/ReportCard/ReportCard';
import NewStudyForm from '../../components/studies/NewStudyForm/NewStudyForm';
import { getFirstName } from '../../utils/formatName';
import { useAuth } from '../../hooks/useAuth';
import './Dashboard.css';

export default function Dashboard() {
  const { user } = useAuth();
  const navigate = useNavigate();
  const [searchParams, setSearchParams] = useSearchParams();
  const [stats, setStats] = useState<DashboardStats | null>(null);
  const [recentReports, setRecentReports] = useState<Report[]>([]);
  const [isLoading, setIsLoading] = useState(true);
  const [error, setError] = useState('');

  // Starting a study is an inline mode, not a separate route, so the rest of the
  // dashboard hides while it's active. `startUpload`/`patientId` let PatientDetail's
  // "New study for this patient" link open straight into it with that patient preselected.
  const [isUploading, setIsUploading] = useState(searchParams.has('startUpload'));
  const preselectedPatientId = searchParams.get('patientId') ?? undefined;

  function openUpload() {
    setIsUploading(true);
  }

  function closeUpload() {
    setIsUploading(false);
    if (searchParams.has('startUpload') || searchParams.has('patientId')) {
      setSearchParams({}, { replace: true });
    }
  }

  useEffect(() => {
    Promise.all([dashboardApi.stats(), reportApi.list({ page: 1, pageSize: 6 })])
      .then(([statsData, reports]) => {
        setStats(statsData);
        setRecentReports(reports.items);
      })
      .catch((err) => setError(apiErrorMessage(err)))
      .finally(() => setIsLoading(false));
  }, []);

  function handleIntakeComplete(result: StudyIntakeResult) {
    navigate(result.report ? `/reports/${result.report.id}` : `/studies/${result.study.id}`);
  }

  if (isUploading) {
    return (
      <div className="dashboard-page">
        <div className="dashboard-page__upload-header">
          <button className="dashboard-page__back" onClick={closeUpload}>
            <FiArrowLeft size={15} /> Back to dashboard
          </button>
          <h1 className="dashboard-page__upload-title">New study</h1>
        </div>
        <NewStudyForm initialPatientId={preselectedPatientId} onComplete={handleIntakeComplete} />
      </div>
    );
  }

  return (
    <div className="dashboard-page">
      <div className="dashboard-page__header">
        <div>
          <h1>Welcome back{user ? `, ${getFirstName(user.name)}` : ''}</h1>
        </div>
        {!isLoading && !error && recentReports.length > 0 && (
          <Button icon={<FiPlus size={16} />} size="lg" onClick={openUpload}>
            Upload study
          </Button>
        )}
      </div>

      {isLoading ? (
        <div className="dashboard-page__loading">
          <Loader size="lg" label="Loading dashboard…" />
        </div>
      ) : error ? (
        <div className="dashboard-page__error">{error}</div>
      ) : (
        <>
          {recentReports.length === 0 && (
            <div className="dashboard-page__hero">
              <Card className="dashboard-page__hero-card">
                <EmptyState
                  icon={<FiUploadCloud size={32} />}
                  title="Upload your first study"
                  description="Upload a study and AI will draft a structured preliminary report for review in seconds."
                  action={
                    <Button icon={<FiPlus size={16} />} size="lg" onClick={openUpload}>
                      Upload study
                    </Button>
                  }
                />
              </Card>
            </div>
          )}

          <div className="dashboard-page__stats">
            <StatCard label="Total studies" value={stats?.totalStudies ?? 0} icon={<FiActivity />} tone="primary" />
            <StatCard label="Pending review" value={stats?.pendingReview ?? 0} icon={<FiClock />} tone="warning" />
            <StatCard label="AI processing" value={stats?.aiProcessing ?? 0} icon={<FiCpu />} tone="accent" />
            <StatCard label="Completed reports" value={stats?.completedReports ?? 0} icon={<FiCheckCircle />} tone="success" />
            <StatCard
              label="Reports this week"
              value={stats?.reportsThisWeek ?? 0}
              icon={<FiTrendingUp />}
              tone="primary"
              hint={`${stats?.reportsThisMonth ?? 0} this month`}
            />
            <StatCard label="Reports this month" value={stats?.reportsThisMonth ?? 0} icon={<FiFileText />} tone="accent" />
          </div>

          {recentReports.length > 0 && (
            <Card>
              <div className="dashboard-page__section-header">
                <h2>Recent reports</h2>
                <Link to="/reports">View all</Link>
              </div>
              <div className="dashboard-page__report-grid">
                {recentReports.map((report) => (
                  <ReportCard key={report.id} report={report} />
                ))}
              </div>
            </Card>
          )}
        </>
      )}
    </div>
  );
}
