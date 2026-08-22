import { Link } from 'react-router-dom';
import { FiImage } from 'react-icons/fi';
import StatusBadge from '../../common/StatusBadge/StatusBadge';
import { Report } from '../../../types';
import { REPORT_STATUS_META } from '../../../utils/statusMeta';
import { MODALITY_LABELS } from '../../../utils/studyMeta';
import { formatRelative } from '../../../utils/formatDate';
import './ReportCard.css';

interface ReportCardProps {
  report: Report;
}

export default function ReportCard({ report }: ReportCardProps) {
  const study = report.study;
  const meta = REPORT_STATUS_META[report.status];
  const latest = report.versions.find((v) => v.versionNumber === report.currentVersion) ?? report.versions[report.versions.length - 1];
  const thumbFile = study?.files.find((f) => f.mimeType?.startsWith('image/') && f.signedUrl);

  return (
    <Link to={`/reports/${report.id}`} className="report-card">
      <div className="report-card__thumb">
        {thumbFile ? <img src={thumbFile.signedUrl} alt="" /> : <FiImage size={22} />}
      </div>
      <div className="report-card__body">
        <div className="report-card__top">
          <strong>{study ? `${MODALITY_LABELS[study.modality]} — ${study.bodyPart}` : 'Study report'}</strong>
          <StatusBadge label={meta.label} tone={meta.tone} />
        </div>
        <p className="report-card__summary">{latest?.content.summary || 'No summary available yet.'}</p>
        <div className="report-card__footer">
          <span>{study?.patient ? `Patient ${study.patient.name}` : ''}</span>
          <span>{formatRelative(report.createdAt)}</span>
        </div>
      </div>
    </Link>
  );
}
