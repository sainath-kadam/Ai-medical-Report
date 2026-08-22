import { useEffect, useRef, useState } from 'react';
import { templateApi } from '../api/template.api';
import { apiErrorMessage } from '../api/axiosInstance';
import { ReportTemplate } from '../types';

/** Renders `payload` through `POST /templates/preview-pdf` and exposes the result as an
 *  object URL, re-fetching whenever `payload` changes (debounced by `debounceMs` -- pass 0
 *  for an immediate fetch, e.g. when `payload` only changes on discrete selection rather
 *  than continuous editing). Revokes the previous object URL before creating the next one
 *  and on unmount, so blob URLs never leak (same cleanup pattern as FileDropzone.tsx). */
export function useTemplatePreviewPdf(payload: Partial<ReportTemplate> | null, debounceMs = 0) {
  const [previewUrl, setPreviewUrl] = useState<string | null>(null);
  const [isLoading, setIsLoading] = useState(false);
  const [error, setError] = useState('');
  const urlRef = useRef<string | null>(null);

  useEffect(() => {
    if (!payload) return;
    let cancelled = false;
    const handle = setTimeout(() => {
      setIsLoading(true);
      setError('');
      templateApi
        .previewPdf(payload)
        .then((blob) => {
          if (cancelled) return;
          const url = URL.createObjectURL(blob);
          if (urlRef.current) URL.revokeObjectURL(urlRef.current);
          urlRef.current = url;
          setPreviewUrl(url);
        })
        .catch((err) => {
          if (!cancelled) setError(apiErrorMessage(err));
        })
        .finally(() => {
          if (!cancelled) setIsLoading(false);
        });
    }, debounceMs);
    return () => {
      cancelled = true;
      clearTimeout(handle);
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [JSON.stringify(payload), debounceMs]);

  useEffect(
    () => () => {
      if (urlRef.current) URL.revokeObjectURL(urlRef.current);
    },
    []
  );

  return { previewUrl, isLoading, error };
}
