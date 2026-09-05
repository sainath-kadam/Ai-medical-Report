import { CSSProperties, useEffect, useRef, useState } from 'react';
import { FiEdit2, FiLock, FiMinus, FiPlus, FiSave, FiX } from 'react-icons/fi';
import { GeneratedReportContent, Report, ReportTemplate } from '../../../types';
import StatusBadge from '../../common/StatusBadge/StatusBadge';
import Button from '../../common/Button/Button';
import { useAuth } from '../../../hooks/useAuth';
import { REPORT_STATUS_META } from '../../../utils/statusMeta';
import { MODALITY_LABELS } from '../../../utils/studyMeta';
import { formatDate } from '../../../utils/formatDate';
import './ReportViewer.css';

interface ReportViewerProps {
  report: Report;
  selectedVersion: number;
  onSelectVersion: (version: number) => void;
  // Direct-edit affordance (as opposed to RequestChangesPanel's AI-mediated "message the
  // AI to make changes" flow) — both are offered side by side on the report workspace.
  // Omitted/false hides the Edit button entirely.
  editable?: boolean;
  onSave?: (content: GeneratedReportContent) => Promise<void>;
  isSaving?: boolean;
}

const ZOOM_STEPS = [70, 85, 100, 115, 130, 150, 175, 200];
const DEFAULT_ZOOM_INDEX = 2; // 100%

function calculateAge(dob?: string): number | null {
  if (!dob) return null;
  const born = new Date(dob);
  if (Number.isNaN(born.getTime())) return null;
  const today = new Date();
  let age = today.getFullYear() - born.getFullYear();
  const beforeBirthday =
    today.getMonth() < born.getMonth() || (today.getMonth() === born.getMonth() && today.getDate() < born.getDate());
  if (beforeBirthday) age -= 1;
  return age;
}

/** An auto-growing, borderless text field styled to look identical to the static <p> it
 *  replaces in edit mode — editing a report should feel like writing directly on the
 *  document itself, not filling out a separate form. */
function DocField({
  value,
  onChange,
  disabled,
  minRows = 2,
  className = '',
}: {
  value: string;
  onChange: (value: string) => void;
  disabled?: boolean;
  minRows?: number;
  className?: string;
}) {
  const ref = useRef<HTMLTextAreaElement>(null);

  useEffect(() => {
    const el = ref.current;
    if (!el) return;
    el.style.height = 'auto';
    el.style.height = `${el.scrollHeight}px`;
  }, [value]);

  return (
    <textarea
      ref={ref}
      className={`report-viewer__field ${className}`}
      value={value}
      onChange={(e) => onChange(e.target.value)}
      disabled={disabled}
      rows={minRows}
    />
  );
}

/** Renders one version of a report the way it will actually look once printed/downloaded
 *  (mirrors server/app/services/pdf_service.py's layout: facility header -> patient/study
 *  identification block -> exam title -> narrative sections -> signature block -> footer)
 *  using the organization's template — accent color, header, doctor-info toggles, style,
 *  and section order all come from there, so two organizations never see the same layout
 *  unless they choose to. Supports zooming the page and, when `editable`, writing directly
 *  onto it in place.
 *
 *  The document itself renders identically regardless of report status — no AI/draft/
 *  finalized wording anywhere in it, matching the PDF export. Status is only ever shown
 *  in the toolbar above (`StatusBadge`), never inside the page. */
export default function ReportViewer({ report, selectedVersion, onSelectVersion, editable, onSave, isSaving }: ReportViewerProps) {
  const { user } = useAuth();
  const template = typeof report.template === 'object' ? (report.template as ReportTemplate) : null;
  const study = report.study;
  const patient = study?.patient;
  const version = report.versions.find((v) => v.versionNumber === selectedVersion) ?? report.versions[report.versions.length - 1];
  const meta = REPORT_STATUS_META[report.status];
  const accent = template?.accentColor || '#0E7C86';
  const style = template?.style;
  const isFinalized = report.status === 'finalized';

  const [isEditing, setIsEditing] = useState(false);
  const [draft, setDraft] = useState<GeneratedReportContent | null>(null);
  const [saveError, setSaveError] = useState('');
  const [zoomIndex, setZoomIndex] = useState(DEFAULT_ZOOM_INDEX);

  if (!version) return null;

  // Editing always targets the current version's content — PATCH /reports/{id} (what
  // onSave calls) merges onto the report's current version regardless of which version is
  // selected in the UI, so only offer Edit while looking at that one to avoid the
  // confusing appearance of editing history.
  const isCurrentVersion = selectedVersion === report.currentVersion;

  const orderedSections = template
    ? [...template.sections].filter((s) => s.enabled).sort((a, b) => a.order - b.order)
    : version.content.sections.map((s, i) => ({ key: s.key, title: s.title, order: i, enabled: true }));

  const doctorInfo = template?.doctorInfo ?? { showDoctorName: true, showSignatureLine: true, showRegistrationNo: false };
  const doctorName = user?.name || '—';
  const age = calculateAge(patient?.dateOfBirth);
  const sexLabel = patient?.sex && patient.sex !== 'unspecified' ? patient.sex[0].toUpperCase() + patient.sex.slice(1) : '—';
  const ageSex = age !== null ? `${age} / ${sexLabel}` : sexLabel;
  const accession = `ACC-${report.id.slice(0, 10).toUpperCase()}`;
  const modalityLabel = study ? MODALITY_LABELS[study.modality] : '';
  const examTitle = study ? `${modalityLabel} ${study.bodyPart}`.trim().toUpperCase() : '';

  function handleStartEdit() {
    setDraft({
      summary: version.content.summary,
      sections: version.content.sections.map((s) => ({ ...s })),
      impression: version.content.impression,
      recommendations: version.content.recommendations,
    });
    setSaveError('');
    setIsEditing(true);
  }

  function handleCancelEdit() {
    setIsEditing(false);
    setDraft(null);
    setSaveError('');
  }

  function updateSectionDraft(key: string, content: string) {
    setDraft((prev) => (prev ? { ...prev, sections: prev.sections.map((s) => (s.key === key ? { ...s, content } : s)) } : prev));
  }

  async function handleSaveEdit() {
    if (!draft || !onSave) return;
    setSaveError('');
    try {
      await onSave(draft);
      setIsEditing(false);
      setDraft(null);
    } catch {
      setSaveError('Could not save your changes. Please try again.');
    }
  }

  function zoomOut() {
    setZoomIndex((i) => Math.max(0, i - 1));
  }
  function zoomIn() {
    setZoomIndex((i) => Math.min(ZOOM_STEPS.length - 1, i + 1));
  }
  function zoomReset() {
    setZoomIndex(DEFAULT_ZOOM_INDEX);
  }
  const zoomPercent = ZOOM_STEPS[zoomIndex];

  return (
    <div
      className={`report-viewer ${isEditing ? 'report-viewer--editing' : ''}`}
      style={
        {
          '--report-accent': accent,
          '--report-zoom': zoomPercent / 100,
          '--report-font-size': style?.fontSize ? `${style.fontSize / 10}rem` : undefined,
          '--report-text-color': style?.contentTextColor || undefined,
          '--report-header-text-color': style?.headerTextColor || undefined,
          '--report-bg-color': style?.backgroundColor || undefined,
        } as CSSProperties
      }
    >
      <div className="report-viewer__toolbar">
        <div className="report-viewer__zoom">
          <button type="button" onClick={zoomOut} disabled={zoomIndex === 0} aria-label="Zoom out">
            <FiMinus size={14} />
          </button>
          <button type="button" className="report-viewer__zoom-value" onClick={zoomReset} title="Reset zoom">
            {zoomPercent}%
          </button>
          <button type="button" onClick={zoomIn} disabled={zoomIndex === ZOOM_STEPS.length - 1} aria-label="Zoom in">
            <FiPlus size={14} />
          </button>
        </div>
        {/* Draft/finalized status lives here, in the surrounding app UI, only — never
            inside the report document itself (below) or its PDF export. */}
        <StatusBadge label={meta.label} tone={meta.tone} />
        {editable && isCurrentVersion && !isEditing && (
          <Button size="sm" className="report-viewer__cta" icon={<FiEdit2 size={14} />} onClick={handleStartEdit}>
            Edit report
          </Button>
        )}
        {isFinalized && !isEditing && (
          <span className="report-viewer__locked-hint">
            <FiLock size={13} /> Finalized — locked for editing. Use “Amend report” in the Actions panel to make changes.
          </span>
        )}
        {isEditing && (
          <div className="report-viewer__editing-controls">
            <span className="report-viewer__editing-hint">Editing — click into any section of the report to change its text</span>
            {saveError && <p className="report-viewer__save-error">{saveError}</p>}
            <Button size="sm" variant="outline" icon={<FiX size={14} />} onClick={handleCancelEdit} disabled={isSaving}>
              Cancel
            </Button>
            <Button size="sm" icon={<FiSave size={14} />} onClick={handleSaveEdit} isLoading={isSaving}>
              Save changes
            </Button>
          </div>
        )}
      </div>

      <div className="report-viewer__page-wrap">
        <article key={selectedVersion} className="report-viewer__page">
          <header className="report-viewer__header">
            <div>
              <p className="report-viewer__org">{template?.header.organizationName || 'Medical Imaging Report'}</p>
              {template?.header.tagline && <p className="report-viewer__tagline">{template.header.tagline}</p>}
              {template?.header.contactNumber && <p className="report-viewer__tagline">Tel: {template.header.contactNumber}</p>}
            </div>
          </header>

          {report.versions.length > 1 && (
            <div className="report-viewer__versions">
              <span>Version history:</span>
              {report.versions.map((v) => (
                <button
                  key={v.versionNumber}
                  type="button"
                  className={`report-viewer__version-pill ${v.versionNumber === selectedVersion ? 'report-viewer__version-pill--active' : ''}`}
                  onClick={() => onSelectVersion(v.versionNumber)}
                >
                  v{v.versionNumber}
                </button>
              ))}
            </div>
          )}

          {version.changeRequestNote && (
            <div className="report-viewer__change-note">
              <strong>Requested change for this version:</strong> {version.changeRequestNote}
            </div>
          )}

          {study && (
            // Flat dt/dd sequence (no wrapping <div> per pair) so the CSS grid in
            // ReportViewer.css can size the label columns once, shared across all three
            // rows -- see that file's comment on .report-viewer__idblock for why a
            // per-row flex layout (the previous markup) let a long label like "Referring
            // Physician :" push its value further right than a short one like "Patient
            // Name :", misaligning every row even though the printed PDF (a real table
            // with fixed column widths, server/app/services/pdf_service.py) never did.
            <dl className="report-viewer__idblock">
              <dt>Patient Name :</dt>
              <dd>{patient?.name || 'Unknown'}</dd>
              <dt>Patient ID :</dt>
              <dd>{patient?.mrn || '—'}</dd>
              <dt>Age / Sex :</dt>
              <dd>{ageSex}</dd>
              <dt>Date of Study :</dt>
              <dd>{formatDate(study.studyDate)}</dd>
              <dt>Referring Physician :</dt>
              <dd>{study.referringPhysician || '—'}</dd>
              <dt>Accession No. :</dt>
              <dd>{accession}</dd>
            </dl>
          )}

          {study && (
            <div className="report-viewer__exam">
              <p className="report-viewer__department">DEPARTMENT OF RADIOLOGY</p>
              <h2 className="report-viewer__exam-title">{examTitle}</h2>
            </div>
          )}

          <div className="report-viewer__document">
            {isEditing && draft ? (
              <>
                <section className="report-viewer__section report-viewer__section--summary">
                  <h3>Summary</h3>
                  <DocField value={draft.summary} onChange={(v) => setDraft({ ...draft, summary: v })} minRows={2} disabled={isSaving} />
                </section>

                {orderedSections.map((section) => {
                  const match = draft.sections.find((s) => s.key === section.key);
                  if (!match) return null;
                  return (
                    <section key={section.key} className="report-viewer__section">
                      <h3>{match.title || section.title}</h3>
                      <DocField
                        value={match.content}
                        onChange={(v) => updateSectionDraft(section.key, v)}
                        minRows={3}
                        disabled={isSaving}
                      />
                    </section>
                  );
                })}

                <section className="report-viewer__section">
                  <h3>Impression</h3>
                  <DocField value={draft.impression} onChange={(v) => setDraft({ ...draft, impression: v })} minRows={2} disabled={isSaving} />
                </section>

                <section className="report-viewer__section">
                  <h3>Recommendations</h3>
                  <DocField
                    value={draft.recommendations}
                    onChange={(v) => setDraft({ ...draft, recommendations: v })}
                    minRows={2}
                    disabled={isSaving}
                  />
                </section>
              </>
            ) : (
              <>
                {version.content.summary && (
                  <section className="report-viewer__section report-viewer__section--summary">
                    <h3>Summary</h3>
                    <p>{version.content.summary}</p>
                  </section>
                )}

                {orderedSections.map((section) => {
                  const match = version.content.sections.find((s) => s.key === section.key);
                  if (!match) return null;
                  return (
                    <section key={section.key} className="report-viewer__section">
                      <h3>{match.title || section.title}</h3>
                      <p>{match.content}</p>
                    </section>
                  );
                })}

                {version.content.impression && (
                  <section className="report-viewer__section">
                    <h3>Impression</h3>
                    <p>{version.content.impression}</p>
                  </section>
                )}

                {version.content.recommendations && (
                  <section className="report-viewer__section">
                    <h3>Recommendations</h3>
                    <p>{version.content.recommendations}</p>
                  </section>
                )}
              </>
            )}
          </div>

          <div className="report-viewer__signature">
            {doctorInfo.showDoctorName && (
              <div className="report-viewer__signature-block">
                <span className="report-viewer__signature-label">Reported by</span>
                <p>{doctorName}</p>
              </div>
            )}
            {doctorInfo.showSignatureLine && (
              <div className="report-viewer__signature-block report-viewer__signature-block--line">
                <span className="report-viewer__signature-rule" />
                <span className="report-viewer__signature-label">Signature</span>
              </div>
            )}
          </div>

          <footer className="report-viewer__footer">
            {template?.footer.disclaimer && <p>{template.footer.disclaimer}</p>}
            {template?.footer.text && <p>{template.footer.text}</p>}
          </footer>
        </article>
      </div>

    </div>
  );
}
