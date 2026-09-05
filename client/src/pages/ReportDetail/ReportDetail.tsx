import { Navigate, useParams } from 'react-router-dom';
import { apiErrorMessage } from '../../api/axiosInstance';
import { useReport } from '../../hooks/queries/useReports';
import Card from '../../components/common/Card/Card';
import Button from '../../components/common/Button/Button';
import Loader from '../../components/common/Loader/Loader';
import './ReportDetail.css';

/** `/reports/:id` isn't its own page anymore -- the Report tab of `pages/Studies/
 *  StudyDetail.tsx` is the one place a report is viewed/edited/finalized (patient/study
 *  metadata used to be duplicated between this page and StudyDetail; now there's exactly
 *  one workspace). This just resolves the report's studyId and redirects there, so every
 *  existing `/reports/{id}` link (ReportCard, ReportsList, notifications) keeps working.
 *  Reads the same cached `queryKeys.reports.detail(id)` entry StudyDetail/Dashboard
 *  populate, so a report already seen elsewhere this session resolves instantly. */
export default function ReportDetail() {
  const { id } = useParams<{ id: string }>();
  const { data: report, isError, error } = useReport(id);

  if (isError) {
    return (
      <Card>
        <p>{apiErrorMessage(error)}</p>
        <Button variant="outline" onClick={() => window.history.back()}>
          Go back
        </Button>
      </Card>
    );
  }

  if (!report) {
    return (
      <div className="report-detail__loading">
        <Loader size="lg" label="Loading report…" />
      </div>
    );
  }

  return <Navigate to={`/studies/${report.studyId}?tab=report`} replace />;
}
