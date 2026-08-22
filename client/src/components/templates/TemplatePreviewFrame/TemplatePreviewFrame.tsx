import { useState } from 'react';
import { FiDownload } from 'react-icons/fi';
import Button from '../../common/Button/Button';
import Loader from '../../common/Loader/Loader';
import { useTemplatePreviewPdf } from '../../../hooks/useTemplatePreviewPdf';
import { templateApi } from '../../../api/template.api';
import { apiErrorMessage } from '../../../api/axiosInstance';
import { ReportTemplate } from '../../../types';
import './TemplatePreviewFrame.css';

interface TemplatePreviewFrameProps {
  payload: Partial<ReportTemplate> | null;
  height?: number;
  debounceMs?: number;
}

/** Renders `payload` (a saved template or an unsaved draft's current values) as an
 *  embedded PDF -- a real preview of the report a doctor will eventually see, not a mocked
 *  approximation -- plus a "Download PDF" button. Shared by the template editor's live
 *  preview panel and NewStudyForm's "which template will this study use" preview. */
export default function TemplatePreviewFrame({ payload, height = 480, debounceMs = 0 }: TemplatePreviewFrameProps) {
  const { previewUrl, isLoading, error } = useTemplatePreviewPdf(payload, debounceMs);
  const [isDownloading, setIsDownloading] = useState(false);
  const [downloadError, setDownloadError] = useState('');

  async function handleDownload() {
    if (!payload) return;
    setDownloadError('');
    setIsDownloading(true);
    try {
      const blob = await templateApi.previewPdf(payload);
      const url = URL.createObjectURL(blob);
      const link = document.createElement('a');
      link.href = url;
      link.download = `${payload.name || 'report-template'}-preview.pdf`;
      document.body.appendChild(link);
      link.click();
      link.remove();
      URL.revokeObjectURL(url);
    } catch (err) {
      setDownloadError(apiErrorMessage(err));
    } finally {
      setIsDownloading(false);
    }
  }

  return (
    <div className="template-preview-frame">
      <div className="template-preview-frame__viewport" style={{ height }}>
        {isLoading && !previewUrl && (
          <div className="template-preview-frame__loading">
            <Loader size="md" label="Rendering preview…" />
          </div>
        )}
        {error && <p className="template-preview-frame__error">{error}</p>}
        {previewUrl && <iframe title="Report preview" src={previewUrl} className="template-preview-frame__iframe" />}
      </div>
      {downloadError && <p className="template-preview-frame__error">{downloadError}</p>}
      <Button
        type="button"
        variant="outline"
        size="sm"
        icon={<FiDownload size={14} />}
        onClick={handleDownload}
        isLoading={isDownloading}
        disabled={!payload}
        fullWidth
      >
        Download PDF
      </Button>
    </div>
  );
}
