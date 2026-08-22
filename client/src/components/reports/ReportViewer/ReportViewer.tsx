import { CSSProperties } from 'react';
import { Report, ReportTemplate } from '../../../types';
import StatusBadge from '../../common/StatusBadge/StatusBadge';
import { REPORT_STATUS_META } from '../../../utils/statusMeta';
import { formatDateTime } from '../../../utils/formatDate';
import './ReportViewer.css';

interface ReportViewerProps {
  report: Report;
  selectedVersion: number;
  onSelectVersion: (version: number) => void;
}

/** Renders one version of a report using the organization's template — accent
 *  color, header, doctor-info toggles, and section order all come from there,
 *  so two organizations never see the same layout unless they choose to. */
export default function ReportViewer({ report, selectedVersion, onSelectVersion }: ReportViewerProps) {
  const template = typeof report.template === 'object' ? (report.template as ReportTemplate) : null;
  const version = report.versions.find((v) => v.versionNumber === selectedVersion) ?? report.versions[report.versions.length - 1];
  const meta = REPORT_STATUS_META[report.status];
  const accent = template?.accentColor || '#0E7C86';

  if (!version) return null;

  const orderedSections = template
    ? [...template.sections].filter((s) => s.enabled).sort((a, b) => a.order - b.order)
    : version.content.sections.map((s, i) => ({ key: s.key, title: s.title, order: i, enabled: true }));

  return (
    <article className="report-viewer" style={{ '--report-accent': accent } as CSSProperties}>
      <header className="report-viewer__header">
        <div>
          <p className="report-viewer__org">{template?.header.organizationName || 'Medical Imaging Report'}</p>
          {template?.header.tagline && <p className="report-viewer__tagline">{template.header.tagline}</p>}
        </div>
        <StatusBadge label={meta.label} tone={meta.tone} />
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

      <div className="report-viewer__document">
        {version.content.summary && (
          <section className="report-viewer__section report-viewer__section--summary">
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
      </div>

      <footer className="report-viewer__footer">
        <span>
          Generated {formatDateTime(version.generatedAt)}
          {version.aiModelUsed ? ` · ${version.aiModelUsed}` : ''}
        </span>
        <p>{template?.footer.disclaimer}</p>
      </footer>
    </article>
  );
}
