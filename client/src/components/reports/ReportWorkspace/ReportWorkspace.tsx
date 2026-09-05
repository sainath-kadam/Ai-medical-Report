import { useState } from 'react';
import { FiCheckCircle, FiChevronDown, FiChevronUp, FiCpu, FiDownload, FiRefreshCw, FiUnlock } from 'react-icons/fi';
import { AnalysisJob, GeneratedReportContent, Report } from '../../../types';
import { ANALYSIS_JOB_STAGES, ANALYSIS_JOB_STATUS_META, MODALITY_LABELS } from '../../../utils/studyMeta';
import { getReferenceSources } from '../../../utils/referenceSources';
import Card from '../../common/Card/Card';
import Button from '../../common/Button/Button';
import Loader from '../../common/Loader/Loader';
import ReportViewer from '../ReportViewer/ReportViewer';
import RequestChangesPanel from '../RequestChangesPanel/RequestChangesPanel';
import './ReportWorkspace.css';

// Always show this many reference sources up front; the rest are one click away in a
// scrollable "show more" list instead of pushing the whole sidebar taller.
const VISIBLE_SOURCE_COUNT = 3;

interface RunAnalysisSlot {
  label: string;
  onRun: () => void;
  isRunning: boolean;
  disabled?: boolean;
  job?: AnalysisJob | null;
  jobIsTerminal?: boolean;
  currentStageIndex?: number;
}

interface ReportWorkspaceProps {
  report: Report;
  selectedVersion: number;
  onSelectVersion: (version: number) => void;

  canManage: boolean;
  isBusy: boolean;
  actionError?: string;

  onSaveEdit: (content: GeneratedReportContent) => Promise<void>;
  isSavingEdit: boolean;

  onRequestChanges: (note: string) => Promise<void>;
  isApplyingChanges: boolean;

  onRegenerate: () => void;
  isRegenerating: boolean;

  onFinalize: () => void;
  isFinalizing: boolean;

  onDownload: () => void;
  isDownloading: boolean;

  // Re-opens a finalized report for correction (POST /reports/{id}/amend). Optional: the
  // Dashboard's post-upload review never shows a finalized report (Finalize navigates away),
  // so only the study's Report tab wires this up.
  onAmend?: () => void;
  isAmending?: boolean;

  // Omitted on the Dashboard's post-upload review -- analysis already ran as part of
  // intake there, so there's nothing to (re-)run yet.
  runAnalysis?: RunAnalysisSlot;
}

/** The report-preview + all-of-its-controls workspace: the report itself (zoomable,
 *  editable in place) on the left, every action that can change it (write instructions
 *  for the AI, regenerate, finalize, download, or re-run analysis) grouped in a sidebar on
 *  the right. Used both by the study workspace's Report tab and the Dashboard's
 *  just-analyzed review screen, so both places look and behave identically. */
export default function ReportWorkspace({
  report,
  selectedVersion,
  onSelectVersion,
  canManage,
  isBusy,
  actionError,
  onSaveEdit,
  isSavingEdit,
  onRequestChanges,
  isApplyingChanges,
  onRegenerate,
  isRegenerating,
  onFinalize,
  isFinalizing,
  onDownload,
  isDownloading,
  onAmend,
  isAmending,
  runAnalysis,
}: ReportWorkspaceProps) {
  const isFinalized = report.status === 'finalized';
  const editable = canManage && !isFinalized && !isBusy;
  const canRequestChanges = canManage && !isFinalized;

  const [showAllSources, setShowAllSources] = useState(false);
  const referenceSources = getReferenceSources(report.study?.modality, report.study?.bodyPart);
  const visibleSources = referenceSources.slice(0, VISIBLE_SOURCE_COUNT);
  const extraSources = referenceSources.slice(VISIBLE_SOURCE_COUNT);

  return (
    <div className="report-workspace">
      <div className="report-workspace__main">
        <ReportViewer
          report={report}
          selectedVersion={selectedVersion}
          onSelectVersion={onSelectVersion}
          editable={editable}
          onSave={onSaveEdit}
          isSaving={isSavingEdit}
        />
        {isApplyingChanges && (
          <Card className="report-workspace__applying">
            <Loader size="sm" label="Applying requested changes…" />
          </Card>
        )}
      </div>

      <aside className="report-workspace__sidebar">
        {runAnalysis && (
          <Card>
            <h3 className="report-workspace__card-title">AI analysis</h3>
            <Button
              icon={<FiCpu size={16} />}
              onClick={runAnalysis.onRun}
              isLoading={runAnalysis.isRunning && !runAnalysis.job}
              disabled={runAnalysis.disabled}
              fullWidth
            >
              {runAnalysis.label}
            </Button>

            {runAnalysis.job && !runAnalysis.jobIsTerminal && (
              <div className="report-workspace__job">
                <div className="report-workspace__job-steps">
                  {ANALYSIS_JOB_STAGES.map((stage, idx) => {
                    const state =
                      idx < (runAnalysis.currentStageIndex ?? -1)
                        ? 'done'
                        : idx === runAnalysis.currentStageIndex
                          ? 'current'
                          : 'pending';
                    return (
                      <div key={stage.status} className={`report-workspace__job-step report-workspace__job-step--${state}`}>
                        <span className="report-workspace__job-step-dot" />
                        <span>{stage.label}</span>
                      </div>
                    );
                  })}
                </div>
                <div className="report-workspace__job-loading">
                  <Loader size="sm" label={ANALYSIS_JOB_STATUS_META[runAnalysis.job.status].label} />
                </div>
              </div>
            )}
          </Card>
        )}

        {canRequestChanges && <RequestChangesPanel onSubmit={onRequestChanges} disabled={isBusy} />}

        <Card>
          <h3 className="report-workspace__card-title">Actions</h3>
          <div className="report-workspace__report-actions">
            {canManage && !isFinalized && (
              <>
                <Button icon={<FiRefreshCw size={16} />} variant="outline" onClick={onRegenerate} isLoading={isRegenerating} disabled={isBusy} fullWidth>
                  Regenerate
                </Button>
                <Button icon={<FiCheckCircle size={16} />} onClick={onFinalize} isLoading={isFinalizing} disabled={isBusy} fullWidth>
                  Finalize report
                </Button>
              </>
            )}
            <Button variant="outline" icon={<FiDownload size={16} />} onClick={onDownload} isLoading={isDownloading} fullWidth>
              Download PDF
            </Button>
            {isFinalized && canManage && onAmend && (
              <Button variant="outline" icon={<FiUnlock size={16} />} onClick={onAmend} isLoading={isAmending} disabled={isBusy} fullWidth>
                Amend report
              </Button>
            )}
          </div>
          {isFinalized && (
            <p className="report-workspace__finalized-note">
              This report is finalized and locked.
              {canManage && onAmend
                ? ' To correct it, create an amendment — that re-opens editing and AI revision; the finalized version stays in the history, and you finalize again when done.'
                : ''}
            </p>
          )}
        </Card>

        {actionError && <p className="report-workspace__error-text">{actionError}</p>}

        <p className="report-workspace__disclaimer">
          AI-drafted findings are preliminary decision support only and require clinician review before they inform
          patient care.
        </p>

        <Card className="report-workspace__references">
          <h3 className="report-workspace__card-title">Reference sources</h3>
          <p className="report-workspace__hint">
            Curated clinical resources for this
            {report.study ? ` ${report.study.bodyPart} ${MODALITY_LABELS[report.study.modality]}` : ''} study
            {extraSources.length > 0 && !showAllSources ? ` (${referenceSources.length} total):` : ':'}
          </p>
          <ul className="report-workspace__reference-list">
            {visibleSources.map((source) => (
              <li key={source.url}>
                <a href={source.url} target="_blank" rel="noreferrer">
                  {source.label}
                </a>
              </li>
            ))}
          </ul>
          {showAllSources && extraSources.length > 0 && (
            <ul className="report-workspace__reference-list report-workspace__reference-list--scroll">
              {extraSources.map((source) => (
                <li key={source.url}>
                  <a href={source.url} target="_blank" rel="noreferrer">
                    {source.label}
                  </a>
                </li>
              ))}
            </ul>
          )}
          {extraSources.length > 0 && (
            <Button
              variant="ghost"
              size="sm"
              icon={showAllSources ? <FiChevronUp size={14} /> : <FiChevronDown size={14} />}
              onClick={() => setShowAllSources((prev) => !prev)}
              fullWidth
            >
              {showAllSources ? 'Show less' : `Show ${extraSources.length} more`}
            </Button>
          )}
        </Card>
      </aside>
    </div>
  );
}
