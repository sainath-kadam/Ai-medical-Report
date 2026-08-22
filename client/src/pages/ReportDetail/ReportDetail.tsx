import { useEffect, useState } from 'react';
import { Navigate, useParams } from 'react-router-dom';
import { reportApi } from '../../api/report.api';
import { apiErrorMessage } from '../../api/axiosInstance';
import Card from '../../components/common/Card/Card';
import Button from '../../components/common/Button/Button';
import Loader from '../../components/common/Loader/Loader';
import './ReportDetail.css';

/** `/reports/:id` isn't its own page anymore -- the Report tab of `pages/Studies/
 *  StudyDetail.tsx` is the one place a report is viewed/edited/finalized (patient/study
 *  metadata used to be duplicated between this page and StudyDetail; now there's exactly
 *  one workspace). This just resolves the report's studyId and redirects there, so every
 *  existing `/reports/{id}` link (ReportCard, ReportsList, notifications) keeps working. */
export default function ReportDetail() {
  const { id } = useParams<{ id: string }>();
  const [studyId, setStudyId] = useState<string | null>(null);
  const [error, setError] = useState('');

  useEffect(() => {
    if (!id) return;
    reportApi
      .getById(id)
      .then((report) => setStudyId(report.studyId))
      .catch((err) => setError(apiErrorMessage(err)));
  }, [id]);

  if (error) {
    return (
      <Card>
        <p>{error}</p>
        <Button variant="outline" onClick={() => window.history.back()}>
          Go back
        </Button>
      </Card>
    );
  }

  if (!studyId) {
    return (
      <div className="report-detail__loading">
        <Loader size="lg" label="Loading report…" />
      </div>
    );
  }

  return <Navigate to={`/studies/${studyId}?tab=report`} replace />;
}
