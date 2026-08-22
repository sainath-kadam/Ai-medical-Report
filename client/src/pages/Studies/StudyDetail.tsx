import { useCallback, useEffect, useState } from 'react';
import { Link, useNavigate, useParams, useSearchParams } from 'react-router-dom';
import {
  FiAlertTriangle,
  FiArrowLeft,
  FiCheckCircle,
  FiClock,
  FiCpu,
  FiDownload,
  FiFile,
  FiImage,
  FiRefreshCw,
  FiUploadCloud,
} from 'react-icons/fi';
import { studyApi } from '../../api/study.api';
import { patientApi } from '../../api/patient.api';
import { reportApi } from '../../api/report.api';
import { apiErrorMessage } from '../../api/axiosInstance';
import { AnalysisJob, Patient, Report, Study, StudyFile } from '../../types';
import {
  ANALYSIS_JOB_STAGES,
  ANALYSIS_JOB_STATUS_META,
  MODALITY_LABELS,
  STUDY_STATUS_META,
  TERMINAL_JOB_STATUSES,
} from '../../utils/studyMeta';
import { formatDate, formatDateTime, formatRelative } from '../../utils/formatDate';
import { useAuth } from '../../hooks/useAuth';
import { useAnalysisJobPolling } from '../../hooks/useAnalysisJobPolling';
import Card from '../../components/common/Card/Card';
import Button from '../../components/common/Button/Button';
import Loader from '../../components/common/Loader/Loader';
import EmptyState from '../../components/common/EmptyState/EmptyState';
import StatusBadge from '../../components/common/StatusBadge/StatusBadge';
import FileDropzone from '../../components/upload/FileDropzone/FileDropzone';
import Tabs from '../../components/ui/Tabs/Tabs';
import ReportViewer from '../../components/reports/ReportViewer/ReportViewer';
import RequestChangesPanel from '../../components/reports/RequestChangesPanel/RequestChangesPanel';
import './StudyDetail.css';

type TabKey = 'overview' | 'images' | 'report' | 'history';

function formatFileSize(bytes: number): string {
  if (bytes < 1024) return `${bytes} B`;
  if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(1)} KB`;
  return `${(bytes / (1024 * 1024)).toFixed(2)} MB`;
}

/** One workspace per study -- overview/images/report/history as tabs, instead of splitting
 *  the same patient/study/report data across two separate pages (the old StudyDetail +
 *  ReportDetail). `ReportDetail.tsx` now just redirects here with `?tab=report` for any
 *  link that still points at `/reports/{id}`. */
export default function StudyDetail() {
  const { id } = useParams<{ id: string }>();
  const navigate = useNavigate();
  const [searchParams, setSearchParams] = useSearchParams();
  const { user } = useAuth();

  const [study, setStudy] = useState<Study | null>(null);
  const [patient, setPatient] = useState<Patient | null>(null);
  const [isLoading, setIsLoading] = useState(true);
  const [error, setError] = useState('');

  const [report, setReport] = useState<Report | null>(null);
  const [isReportLoading, setIsReportLoading] = useState(false);
  const [selectedVersion, setSelectedVersion] = useState(1);
  const [jobHistory, setJobHistory] = useState<AnalysisJob[]>([]);

  const [pendingFile, setPendingFile] = useState<File | null>(null);
  const [isUploading, setIsUploading] = useState(false);
  const [uploadError, setUploadError] = useState('');
  const [selectedFileId, setSelectedFileId] = useState<string | null>(null);

  const [isRunningAnalysis, setIsRunningAnalysis] = useState(false);
  const [isRegenerating, setIsRegenerating] = useState(false);
  const [isFinalizing, setIsFinalizing] = useState(false);
  const [isApplyingChanges, setIsApplyingChanges] = useState(false);
  const [isDownloading, setIsDownloading] = useState(false);
  const [actionError, setActionError] = useState('');

  const canManage = user?.role === 'org_admin' || user?.role === 'doctor';

  const activeTab = (searchParams.get('tab') as TabKey) || 'overview';
  function setActiveTab(key: TabKey) {
    const next = new URLSearchParams(searchParams);
    next.set('tab', key);
    setSearchParams(next, { replace: true });
  }

  const loadStudy = useCallback(() => {
    if (!id) return;
    setIsLoading(true);
    setError('');
    studyApi
      .getById(id)
      .then(setStudy)
      .catch((err) => setError(apiErrorMessage(err)))
      .finally(() => setIsLoading(false));
  }, [id]);

  useEffect(() => {
    loadStudy();
  }, [loadStudy]);

  // The study's own patient field may or may not be embedded by the backend -- fetch it
  // separately as a fallback so the Overview tab always has something to show.
  useEffect(() => {
    if (!study) return;
    if (study.patient) {
      setPatient(study.patient);
      return;
    }
    patientApi.getById(study.patientId).then(setPatient).catch(() => { });
  }, [study]);

  // KNOWN GAP (see CONTRACTS.md §9): there is no `GET /studies/{id}/report` convenience
  // endpoint yet, so the report for this study is located the same indirect way the old
  // StudyDetail did -- narrow reports by patientId and match the exact study client-side.
  const loadReport = useCallback(async () => {
    if (!study) return;
    setIsReportLoading(true);
    try {
      const { items } = await reportApi.list({ patientId: study.patientId, pageSize: 50 });
      const match = items.find((r) => r.studyId === study.id);
      if (match) {
        const full = await reportApi.getById(match.id);
        setReport(full);
        setSelectedVersion(full.currentVersion);
      } else {
        setReport(null);
      }
    } catch {
      setReport(null);
    } finally {
      setIsReportLoading(false);
    }
  }, [study?.id, study?.patientId]);

  useEffect(() => {
    loadReport();
  }, [loadReport]);

  const refreshJobHistory = useCallback(() => {
    if (!study) return;
    studyApi.getJobsForStudy(study.id).then((jobs) => setJobHistory(jobs)).catch(() => { });
  }, [study?.id]);

  const { job, poll } = useAnalysisJobPolling((finished) => {
    setIsRunningAnalysis(false);
    setIsApplyingChanges(false);
    loadStudy();
    refreshJobHistory();
    if (finished.status === 'failed') {
      setActionError(finished.error || 'The AI analysis failed. Please try again.');
    } else {
      loadReport();
    }
  });

  // Resume watching an in-flight job, and populate the History tab, on (re)load -- e.g. the
  // user navigated away mid-analysis.
  useEffect(() => {
    if (!study) return;
    let cancelled = false;
    studyApi
      .getJobsForStudy(study.id)
      .then((jobs) => {
        if (cancelled) return;
        setJobHistory(jobs);
        if (jobs.length === 0) return;
        const latest = [...jobs].sort((a, b) => new Date(b.createdAt).getTime() - new Date(a.createdAt).getTime())[0];
        if (!TERMINAL_JOB_STATUSES.includes(latest.status)) {
          setIsRunningAnalysis(true);
          poll(latest.id);
        }
      })
      .catch(() => { });
    return () => {
      cancelled = true;
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [study?.id]);

  const canRunAnalysis = user?.role === 'org_admin' || user?.role === 'doctor';
  const isBusy = isRunningAnalysis || isRegenerating || isFinalizing || isApplyingChanges;

  async function handleRunAnalysis() {
    if (!study) return;
    setActionError('');
    setIsRunningAnalysis(true);
    try {
      const { jobId } = await studyApi.runAnalysis(study.id);
      poll(jobId);
    } catch (err) {
      setIsRunningAnalysis(false);
      setActionError(apiErrorMessage(err));
    }
  }

  async function handleUpload() {
    if (!pendingFile || !study) return;
    setIsUploading(true);
    setUploadError('');
    try {
      const updated = await studyApi.uploadFile(study.id, pendingFile);
      setStudy(updated);
      setPendingFile(null);
    } catch (err) {
      setUploadError(apiErrorMessage(err));
    } finally {
      setIsUploading(false);
    }
  }

  async function handleRequestChanges(instruction: string) {
    if (!report) return;
    setActionError('');
    setIsApplyingChanges(true);
    try {
      const { jobId } = await reportApi.requestChanges(report.id, instruction);
      poll(jobId);
    } catch (err) {
      setIsApplyingChanges(false);
      setActionError(apiErrorMessage(err));
    }
  }

  async function handleRegenerate() {
    if (!report) return;
    setActionError('');
    setIsRegenerating(true);
    try {
      const updated = await reportApi.regenerate(report.id);
      setReport(updated);
      setSelectedVersion(updated.currentVersion);
    } catch (err) {
      setActionError(apiErrorMessage(err));
    } finally {
      setIsRegenerating(false);
    }
  }

  async function handleFinalize() {
    if (!report) return;
    setActionError('');
    setIsFinalizing(true);
    try {
      const updated = await reportApi.finalize(report.id);
      setReport(updated);
    } catch (err) {
      setActionError(apiErrorMessage(err));
    } finally {
      setIsFinalizing(false);
    }
  }

  async function handleDownload() {
    if (!report) return;
    setActionError('');
    setIsDownloading(true);
    try {
      const blob = await reportApi.downloadPdf(report.id);
      const url = URL.createObjectURL(blob);
      const link = document.createElement('a');
      link.href = url;
      link.download = `report-${report.id}.pdf`;
      document.body.appendChild(link);
      link.click();
      link.remove();
      URL.revokeObjectURL(url);
    } catch (err) {
      setActionError(apiErrorMessage(err));
    } finally {
      setIsDownloading(false);
    }
  }

  if (isLoading) {
    return (
      <div className="study-detail__loading">
        <Loader size="lg" label="Loading study…" />
      </div>
    );
  }

  if (!study) {
    return (
      <Card>
        <p className="study-detail__error-text">{error || 'Study not found.'}</p>
        <Button variant="outline" onClick={() => navigate('/studies')} icon={<FiArrowLeft size={15} />}>
          Back to studies
        </Button>
      </Card>
    );
  }

  const statusMeta = STUDY_STATUS_META[study.status];
  const currentStageIndex = job ? ANALYSIS_JOB_STAGES.findIndex((s) => s.status === job.status) : -1;
  const jobIsTerminal = job ? TERMINAL_JOB_STATUSES.includes(job.status) : false;
  const selectedFile: StudyFile | undefined = study.files.find((f) => f.id === selectedFileId) ?? study.files[0];

  return (
    <div className="study-detail">
      <button className="study-detail__back" onClick={() => navigate('/studies')}>
        <FiArrowLeft size={15} /> Back to studies
      </button>

      <div className="study-detail__header">
        <div>
          <h1>
            {MODALITY_LABELS[study.modality]} · {study.bodyPart}
          </h1>
          <p>
            Study date {formatDate(study.studyDate)} · Added {formatRelative(study.createdAt)}
          </p>
        </div>
        <StatusBadge label={statusMeta.label} tone={statusMeta.tone} />
      </div>

      {error && <div className="study-detail__banner-error">{error}</div>}

      <Tabs
        activeKey={activeTab}
        onChange={(key) => setActiveTab(key as TabKey)}
        items={[
          { key: 'overview', label: 'Overview' },
          { key: 'images', label: 'Images', badge: study.files.length > 0 ? <span className="study-detail__tab-count">{study.files.length}</span> : undefined },
          { key: 'report', label: 'Report', badge: report && report.status !== 'finalized' ? <span className="study-detail__tab-dot" /> : undefined },
          { key: 'history', label: 'History' },
        ]}
      />

      {activeTab === 'overview' && (
        <div className="study-detail__layout">
          <div className="study-detail__main">
            <Card>
              <h3 className="study-detail__card-title">Clinical history</h3>
              <p className="study-detail__clinical-history">
                {study.clinicalHistory || 'No clinical history was provided for this study.'}
              </p>
            </Card>
          </div>

          <aside className="study-detail__sidebar">
            <Card>
              <h3 className="study-detail__card-title">Patient</h3>
              {patient ? (
                <>
                  <dl className="study-detail__meta-list">
                    <div>
                      <dt>Name</dt>
                      <dd>{patient.name}</dd>
                    </div>
                    <div>
                      <dt>MRN</dt>
                      <dd>{patient.mrn}</dd>
                    </div>
                    {patient.dateOfBirth && (
                      <div>
                        <dt>Date of birth</dt>
                        <dd>{formatDate(patient.dateOfBirth)}</dd>
                      </div>
                    )}
                    {patient.sex && (
                      <div>
                        <dt>Sex</dt>
                        <dd>{patient.sex}</dd>
                      </div>
                    )}
                    {patient.contactPhone && (
                      <div>
                        <dt>Phone</dt>
                        <dd>{patient.contactPhone}</dd>
                      </div>
                    )}
                  </dl>
                  <Link className="study-detail__patient-link" to={`/patients/${study.patientId}`}>
                    View patient profile
                  </Link>
                </>
              ) : (
                <Loader size="sm" />
              )}
            </Card>

            <Card>
              <h3 className="study-detail__card-title">Study details</h3>
              <dl className="study-detail__meta-list">
                <div>
                  <dt>Modality</dt>
                  <dd>{MODALITY_LABELS[study.modality]}</dd>
                </div>
                <div>
                  <dt>Body part</dt>
                  <dd>{study.bodyPart}</dd>
                </div>
                <div>
                  <dt>Study date</dt>
                  <dd>{formatDate(study.studyDate)}</dd>
                </div>
                <div>
                  <dt>Status</dt>
                  <dd>
                    <StatusBadge label={statusMeta.label} tone={statusMeta.tone} />
                  </dd>
                </div>
                <div>
                  <dt>Files</dt>
                  <dd>{study.files.length}</dd>
                </div>
              </dl>
            </Card>
          </aside>
        </div>
      )}

      {activeTab === 'images' && (
        <div className="study-detail__layout">
          <div className="study-detail__main">
            <Card>
              <h3 className="study-detail__card-title">Files</h3>
              {study.files.length === 0 ? (
                <EmptyState icon={<FiFile />} title="No files uploaded yet" description="Upload the imaging file(s) for this study below." />
              ) : (
                <div className="study-detail__image-grid">
                  {study.files.map((file) => (
                    <button
                      type="button"
                      key={file.id}
                      className={`study-detail__image-tile ${selectedFile?.id === file.id ? 'study-detail__image-tile--active' : ''}`}
                      onClick={() => setSelectedFileId(file.id)}
                    >
                      {file.mimeType?.startsWith('image/') && file.signedUrl ? (
                        <img src={file.signedUrl} alt={file.fileName} />
                      ) : (
                        <FiFile size={22} />
                      )}
                      <span>{file.fileName}</span>
                    </button>
                  ))}
                </div>
              )}

              <div className="study-detail__upload">
                <FileDropzone file={pendingFile} onSelect={setPendingFile} />
                {pendingFile && (
                  <Button icon={<FiUploadCloud size={15} />} onClick={handleUpload} isLoading={isUploading}>
                    Upload file
                  </Button>
                )}
                {uploadError && <p className="study-detail__error-text">{uploadError}</p>}
              </div>
            </Card>
          </div>

          <aside className="study-detail__sidebar">
            <Card>
              <h3 className="study-detail__card-title">Preview</h3>
              {!selectedFile ? (
                <p className="study-detail__hint">Select a file to preview it here.</p>
              ) : selectedFile.mimeType?.startsWith('video/') && selectedFile.signedUrl ? (
                <video className="study-detail__preview-media" src={selectedFile.signedUrl} controls />
              ) : selectedFile.mimeType?.startsWith('image/') && selectedFile.signedUrl ? (
                <img className="study-detail__preview-media" src={selectedFile.signedUrl} alt={selectedFile.fileName} />
              ) : selectedFile.signedUrl ? (
                <a href={selectedFile.signedUrl} target="_blank" rel="noreferrer" className="study-detail__preview-download">
                  <FiDownload size={15} /> Download {selectedFile.fileName}
                </a>
              ) : (
                <FiImage size={28} />
              )}
              {selectedFile && (
                <p className="study-detail__hint">
                  {formatFileSize(selectedFile.sizeBytes)} · {formatDateTime(selectedFile.uploadedAt)}
                </p>
              )}
            </Card>
          </aside>
        </div>
      )}

      {activeTab === 'report' && (
        <div className="study-detail__layout">
          <div className="study-detail__main">
            {study.files.length === 0 ? (
              <Card>
                <EmptyState
                  icon={<FiFile />}
                  title="No imaging file yet"
                  description="Upload a scan in the Images tab before running AI analysis."
                  action={
                    <Button variant="outline" onClick={() => setActiveTab('images')}>
                      Go to Images
                    </Button>
                  }
                />
              </Card>
            ) : isReportLoading ? (
              <div className="study-detail__tab-loading">
                <Loader size="lg" />
              </div>
            ) : report ? (
              <>
                {report.status !== 'finalized' && (
                  <div className="study-detail__preliminary-banner">
                    <FiAlertTriangle size={16} />
                    <span>PRELIMINARY AI-ASSISTED REPORT — REQUIRES QUALIFIED MEDICAL REVIEW. Not a final diagnosis.</span>
                  </div>
                )}
                <ReportViewer report={report} selectedVersion={selectedVersion} onSelectVersion={setSelectedVersion} />
                {canManage && report.status !== 'finalized' && (
                  <RequestChangesPanel onSubmit={handleRequestChanges} disabled={isBusy} />
                )}
                {isApplyingChanges && (
                  <Card className="study-detail__applying">
                    <Loader size="sm" label="Applying requested changes…" />
                  </Card>
                )}
              </>
            ) : (
              <Card>
                <EmptyState icon={<FiCpu />} title="No report yet" description="Run AI analysis (from the panel on the right) to generate a preliminary report." />
              </Card>
            )}
          </div>

          <aside className="study-detail__sidebar">
            {canRunAnalysis && (
              <Card>
                <h3 className="study-detail__card-title">AI analysis</h3>
                <Button
                  icon={<FiCpu size={16} />}
                  onClick={handleRunAnalysis}
                  isLoading={isRunningAnalysis && !job}
                  disabled={isBusy || study.files.length === 0}
                  fullWidth
                >
                  {report ? 'Re-run AI analysis' : 'Run AI analysis'}
                </Button>

                {job && !jobIsTerminal && (
                  <div className="study-detail__job">
                    <div className="study-detail__job-steps">
                      {ANALYSIS_JOB_STAGES.map((stage, idx) => {
                        const state = idx < currentStageIndex ? 'done' : idx === currentStageIndex ? 'current' : 'pending';
                        return (
                          <div key={stage.status} className={`study-detail__job-step study-detail__job-step--${state}`}>
                            <span className="study-detail__job-step-dot" />
                            <span>{stage.label}</span>
                          </div>
                        );
                      })}
                    </div>
                    <div className="study-detail__job-loading">
                      <Loader size="sm" label={ANALYSIS_JOB_STATUS_META[job.status].label} />
                    </div>
                  </div>
                )}
              </Card>
            )}

            {report && (
              <Card>
                <h3 className="study-detail__card-title">Actions</h3>
                <div className="study-detail__report-actions">
                  {canManage && report.status !== 'finalized' && (
                    <>
                      <Button icon={<FiRefreshCw size={16} />} variant="outline" onClick={handleRegenerate} isLoading={isRegenerating} disabled={isBusy} fullWidth>
                        Regenerate
                      </Button>
                      <Button icon={<FiCheckCircle size={16} />} onClick={handleFinalize} isLoading={isFinalizing} disabled={isBusy} fullWidth>
                        Finalize report
                      </Button>
                    </>
                  )}
                  <Button variant="outline" icon={<FiDownload size={16} />} onClick={handleDownload} isLoading={isDownloading} fullWidth>
                    Download PDF
                  </Button>
                </div>
                {report.status === 'finalized' && (
                  <p className="study-detail__finalized-note">This report has been finalized and is now immutable.</p>
                )}
              </Card>
            )}

            {actionError && <p className="study-detail__error-text">{actionError}</p>}
            <p className="study-detail__disclaimer">
              AI-drafted findings are preliminary decision support only and require clinician review before they
              inform patient care.
            </p>
            {report && (
              <Card className="study-detail__references">
                <h3 className="study-detail__card-title">Reference sources</h3>
                <p className="study-detail__hint">Clinical resources for reviewing the report:</p>
                <ul className="study-detail__reference-list">
                  <li><a href="https://www.radiologyinfo.org/" target="_blank" rel="noreferrer">RadiologyInfo.org</a></li>
                  <li><a href="https://www.acr.org/Clinical-Resources/ACR-Appropriateness-Criteria" target="_blank" rel="noreferrer">ACR Appropriateness Criteria</a></li>
                  <li><a href="https://www.rsna.org/" target="_blank" rel="noreferrer">Radiological Society of North America</a></li>
                </ul>
              </Card>
            )}
          </aside>
        </div>
      )}

      {activeTab === 'history' && (
        <Card>
          <h3 className="study-detail__card-title">Analysis runs</h3>
          {jobHistory.length === 0 ? (
            <EmptyState icon={<FiClock />} title="No analysis runs yet" description="Runs will appear here once AI analysis is started." />
          ) : (
            <ul className="study-detail__history-list">
              {jobHistory.map((entry) => {
                const meta = ANALYSIS_JOB_STATUS_META[entry.status];
                return (
                  <li key={entry.id}>
                    <StatusBadge label={meta.label} tone={meta.tone} />
                    <span className="study-detail__history-time">{formatDateTime(entry.createdAt)}</span>
                    {entry.error && <span className="study-detail__history-note">{entry.error}</span>}
                  </li>
                );
              })}
            </ul>
          )}

          {report && report.versions.length > 0 && (
            <>
              <h3 className="study-detail__card-title study-detail__card-title--spaced">Report versions</h3>
              <ul className="study-detail__history-list">
                {[...report.versions].reverse().map((version) => (
                  <li key={version.versionNumber}>
                    <strong>v{version.versionNumber}</strong>
                    <span className="study-detail__history-time">
                      {version.author === 'ai' ? 'AI generated' : 'Doctor edit'} · {formatDateTime(version.generatedAt)}
                    </span>
                    {version.changeRequestNote && <span className="study-detail__history-note">"{version.changeRequestNote}"</span>}
                  </li>
                ))}
              </ul>
            </>
          )}
        </Card>
      )}
    </div>
  );
}
