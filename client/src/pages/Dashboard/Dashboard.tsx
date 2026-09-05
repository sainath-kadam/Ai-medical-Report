import { useState } from 'react';
import { Link, useNavigate, useSearchParams } from 'react-router-dom';
import { useQueryClient } from '@tanstack/react-query';
import {
  FiActivity,
  FiAlertTriangle,
  FiArrowLeft,
  FiCheckCircle,
  FiClock,
  FiCpu,
  FiFileText,
  FiPlus,
  FiTrendingUp,
  FiUploadCloud,
} from 'react-icons/fi';
import { reportApi } from '../../api/report.api';
import { studyApi } from '../../api/study.api';
import { apiErrorMessage } from '../../api/axiosInstance';
import { useDashboardRecentReports, useDashboardStats } from '../../hooks/queries/useDashboard';
import { queryKeys } from '../../lib/queryKeys';
import { GeneratedReportContent, Report, Study, StudyIntakeResult } from '../../types';
import StatCard from '../../components/common/StatCard/StatCard';
import Card from '../../components/common/Card/Card';
import Button from '../../components/common/Button/Button';
import Loader from '../../components/common/Loader/Loader';
import EmptyState from '../../components/common/EmptyState/EmptyState';
import ReportCard from '../../components/reports/ReportCard/ReportCard';
import ReportWorkspace from '../../components/reports/ReportWorkspace/ReportWorkspace';
import NewStudyForm from '../../components/studies/NewStudyForm/NewStudyForm';
import { getFirstName } from '../../utils/formatName';
import { useAuth } from '../../hooks/useAuth';
import './Dashboard.css';

export default function Dashboard() {
  const { user } = useAuth();
  const navigate = useNavigate();
  const queryClient = useQueryClient();
  const [searchParams, setSearchParams] = useSearchParams();

  // Both cached (see hooks/queries/useDashboard.ts) -- returning to the Dashboard from
  // another page within the freshness window shows the same stats/reports instantly
  // instead of a loading flash, then silently refreshes if they've actually changed.
  const statsQuery = useDashboardStats();
  const reportsQuery = useDashboardRecentReports();
  const stats = statsQuery.data;
  const recentReports = reportsQuery.data?.items ?? [];
  const isLoading = statsQuery.isLoading || reportsQuery.isLoading;
  const error = statsQuery.isError ? apiErrorMessage(statsQuery.error) : reportsQuery.isError ? apiErrorMessage(reportsQuery.error) : '';

  function invalidateDashboard() {
    queryClient.invalidateQueries({ queryKey: queryKeys.dashboard.all });
  }
  // Anything that changes a report's content/status also needs the reports list and any
  // cached study to catch up, not just this page's own dashboard queries.
  function invalidateReportRelated() {
    invalidateDashboard();
    queryClient.invalidateQueries({ queryKey: queryKeys.reports.all });
    queryClient.invalidateQueries({ queryKey: queryKeys.studies.all });
  }

  // Starting a study is an inline mode, not a separate route, so the rest of the
  // dashboard hides while it's active. `startUpload`/`patientId` let PatientDetail's
  // "New study for this patient" link open straight into it with that patient preselected.
  const [isUploading, setIsUploading] = useState(searchParams.has('startUpload'));
  const preselectedPatientId = searchParams.get('patientId') ?? undefined;

  // Once intake finishes analysis, the freshly generated report is reviewed right here
  // (edit anything that needs a correction, then finalize) instead of jumping straight to
  // another page -- `reviewStudyId` is where "Finalize" sends the doctor once they're done.
  const [reviewReport, setReviewReport] = useState<Report | null>(null);
  const [reviewStudyId, setReviewStudyId] = useState<string | null>(null);
  const [reviewSelectedVersion, setReviewSelectedVersion] = useState(1);
  const [isSavingReview, setIsSavingReview] = useState(false);
  const [isRegeneratingReview, setIsRegeneratingReview] = useState(false);
  const [isFinalizingReview, setIsFinalizingReview] = useState(false);
  const [isDownloadingReview, setIsDownloadingReview] = useState(false);
  const [isApplyingReviewChanges, setIsApplyingReviewChanges] = useState(false);
  const [reviewError, setReviewError] = useState('');

  // Upload succeeded but the AI analysis produced no report: stay on the dashboard and
  // say why (with a Retry), rather than silently landing on the study's Overview tab.
  const [intakeFailure, setIntakeFailure] = useState<{ study: Study; message: string } | null>(null);
  const [isRetryingAnalysis, setIsRetryingAnalysis] = useState(false);

  const canManage = user?.role === 'org_admin' || user?.role === 'doctor';
  const isReviewBusy = isSavingReview || isRegeneratingReview || isFinalizingReview || isApplyingReviewChanges;

  function openUpload() {
    setIsUploading(true);
  }

  function closeUpload() {
    setIsUploading(false);
    if (searchParams.has('startUpload') || searchParams.has('patientId')) {
      setSearchParams({}, { replace: true });
    }
  }

  // Locates the report that belongs to `study` the same indirect way StudyDetail does
  // (there is no GET /studies/{id}/report yet -- CONTRACTS.md §9). Returns false if none.
  async function openReportForStudy(study: Study): Promise<boolean> {
    const { items } = await reportApi.list({ patientId: study.patientId, pageSize: 50 });
    const match = items.find((r) => r.studyId === study.id);
    if (!match) return false;
    const full = await reportApi.getById(match.id);
    setReviewReport(full);
    setReviewStudyId(study.id);
    setReviewSelectedVersion(full.currentVersion);
    setIntakeFailure(null);
    return true;
  }

  async function handleIntakeComplete(result: StudyIntakeResult) {
    closeUpload();
    invalidateReportRelated(); // a new study/report now exists, whatever else happened below
    queryClient.invalidateQueries({ queryKey: queryKeys.patients.all });
    if (result.report) {
      setReviewReport(result.report);
      setReviewStudyId(result.study.id);
      setReviewSelectedVersion(result.report.currentVersion);
      return;
    }
    if (!result.analysisJobId) {
      // Analysis wasn't requested, so there's nothing to review here -- go to the study.
      navigate(`/studies/${result.study.id}`);
      return;
    }
    // Analysis ran but failed (the backend runs it inline, so the job is already terminal):
    // fetch its error so the doctor sees *why* there is no report, and can retry from here.
    let message = 'The AI analysis did not complete.';
    try {
      const job = await studyApi.getJob(result.analysisJobId);
      if (job.error) message = job.error;
    } catch {
      /* keep the generic message */
    }
    setIntakeFailure({ study: result.study, message });
  }

  async function handleRetryAnalysis() {
    if (!intakeFailure) return;
    const { study } = intakeFailure;
    setIsRetryingAnalysis(true);
    try {
      // Runs inline server-side and resolves once the analysis has finished (or failed).
      const { jobId } = await studyApi.runAnalysis(study.id);
      const found = await openReportForStudy(study);
      invalidateReportRelated();
      if (!found) {
        const job = await studyApi.getJob(jobId);
        setIntakeFailure({ study, message: job.error || 'The AI analysis did not complete.' });
      }
    } catch (err) {
      setIntakeFailure({ study, message: apiErrorMessage(err) });
    } finally {
      setIsRetryingAnalysis(false);
    }
  }

  function dismissFailure() {
    setIntakeFailure(null);
    invalidateDashboard();
  }

  async function handleReviewSaveEdit(content: GeneratedReportContent) {
    if (!reviewReport) return;
    setReviewError('');
    setIsSavingReview(true);
    try {
      const updated = await reportApi.update(reviewReport.id, content);
      setReviewReport(updated);
      setReviewSelectedVersion(updated.currentVersion);
      invalidateReportRelated();
    } catch (err) {
      setReviewError(apiErrorMessage(err));
      throw err; // re-thrown so ReportViewer knows the save failed and stays in edit mode
    } finally {
      setIsSavingReview(false);
    }
  }

  async function handleReviewRequestChanges(instruction: string) {
    if (!reviewReport) return;
    setReviewError('');
    setIsApplyingReviewChanges(true);
    try {
      // The change-request endpoint runs the AI revision inline and only resolves once
      // it's actually done (no background worker -- see CLAUDE.md), so the report is
      // already updated server-side by the time this await returns; just re-fetch it.
      await reportApi.requestChanges(reviewReport.id, instruction);
      const updated = await reportApi.getById(reviewReport.id);
      setReviewReport(updated);
      setReviewSelectedVersion(updated.currentVersion);
      invalidateReportRelated();
    } catch (err) {
      setReviewError(apiErrorMessage(err));
    } finally {
      setIsApplyingReviewChanges(false);
    }
  }

  async function handleReviewRegenerate() {
    if (!reviewReport) return;
    setReviewError('');
    setIsRegeneratingReview(true);
    try {
      const updated = await reportApi.regenerate(reviewReport.id);
      setReviewReport(updated);
      setReviewSelectedVersion(updated.currentVersion);
      invalidateReportRelated();
    } catch (err) {
      setReviewError(apiErrorMessage(err));
    } finally {
      setIsRegeneratingReview(false);
    }
  }

  async function handleReviewFinalize() {
    if (!reviewReport || !reviewStudyId) return;
    setReviewError('');
    setIsFinalizingReview(true);
    try {
      await reportApi.finalize(reviewReport.id);
      invalidateReportRelated();
      // Finalizing is the one action that leaves the inline review screen -- the doctor's
      // done here, so hand off to the study's own Report tab (the "report page").
      navigate(`/studies/${reviewStudyId}?tab=report`);
    } catch (err) {
      setReviewError(apiErrorMessage(err));
    } finally {
      setIsFinalizingReview(false);
    }
  }

  async function handleReviewDownload() {
    if (!reviewReport) return;
    setReviewError('');
    setIsDownloadingReview(true);
    try {
      const blob = await reportApi.downloadPdf(reviewReport.id);
      const url = URL.createObjectURL(blob);
      const link = document.createElement('a');
      link.href = url;
      link.download = `report-${reviewReport.id}.pdf`;
      document.body.appendChild(link);
      link.click();
      link.remove();
      URL.revokeObjectURL(url);
    } catch (err) {
      setReviewError(apiErrorMessage(err));
    } finally {
      setIsDownloadingReview(false);
    }
  }

  function dismissReview() {
    setReviewReport(null);
    setReviewStudyId(null);
    setReviewError('');
    invalidateDashboard();
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

  if (intakeFailure) {
    return (
      <div className="dashboard-page">
        <div className="dashboard-page__upload-header">
          <button className="dashboard-page__back" onClick={dismissFailure}>
            <FiArrowLeft size={15} /> Back to dashboard
          </button>
          <h1 className="dashboard-page__upload-title">Report format</h1>
        </div>
        <Card>
          <div className="dashboard-page__review-banner dashboard-page__review-banner--error">
            <FiAlertTriangle size={16} />
            <span>The study and its file were saved, but the AI analysis failed — there is no report to review yet.</span>
          </div>
          <p className="dashboard-page__failure-detail">{intakeFailure.message}</p>
          <div className="dashboard-page__failure-actions">
            <Button icon={<FiCpu size={16} />} onClick={handleRetryAnalysis} isLoading={isRetryingAnalysis}>
              Retry AI analysis
            </Button>
            <Button variant="outline" onClick={() => navigate(`/studies/${intakeFailure.study.id}`)} disabled={isRetryingAnalysis}>
              Open study
            </Button>
          </div>
        </Card>
      </div>
    );
  }

  if (reviewReport) {
    return (
      <div className="dashboard-page">
        <div className="dashboard-page__upload-header">
          <button className="dashboard-page__back" onClick={dismissReview}>
            <FiArrowLeft size={15} /> Back to dashboard
          </button>
          <h1 className="dashboard-page__upload-title">Report format</h1>
        </div>
        <div className="dashboard-page__review-banner">
          <FiCheckCircle size={16} />
          <span>Analysis complete — review the draft below, edit anything that needs a correction, then finalize.</span>
        </div>
        <ReportWorkspace
          report={reviewReport}
          selectedVersion={reviewSelectedVersion}
          onSelectVersion={setReviewSelectedVersion}
          canManage={canManage}
          isBusy={isReviewBusy}
          actionError={reviewError}
          onSaveEdit={handleReviewSaveEdit}
          isSavingEdit={isSavingReview}
          onRequestChanges={handleReviewRequestChanges}
          isApplyingChanges={isApplyingReviewChanges}
          onRegenerate={handleReviewRegenerate}
          isRegenerating={isRegeneratingReview}
          onFinalize={handleReviewFinalize}
          isFinalizing={isFinalizingReview}
          onDownload={handleReviewDownload}
          isDownloading={isDownloadingReview}
        />
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
