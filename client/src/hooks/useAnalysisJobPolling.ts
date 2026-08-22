import { useCallback, useEffect, useRef, useState } from 'react';
import { studyApi } from '../api/study.api';
import { apiErrorMessage } from '../api/axiosInstance';
import { AnalysisJob } from '../types';
import { TERMINAL_JOB_STATUSES } from '../utils/studyMeta';

/** Polls `GET /analysis/jobs/{jobId}` every 2s until it reaches a terminal status, then
 *  calls `onTerminal` once. Shared by every place that starts or resumes watching an
 *  analysis job (running AI analysis, requesting AI changes to a report) so the same
 *  setTimeout-polling loop isn't reimplemented per page. `onTerminal` is read from a ref so
 *  callers don't need to memoize it. */
export function useAnalysisJobPolling(onTerminal: (job: AnalysisJob) => void) {
  const [job, setJob] = useState<AnalysisJob | null>(null);
  const [isPolling, setIsPolling] = useState(false);
  const [error, setError] = useState('');
  const timerRef = useRef<ReturnType<typeof setTimeout> | null>(null);
  const onTerminalRef = useRef(onTerminal);
  onTerminalRef.current = onTerminal;

  const stop = useCallback(() => {
    if (timerRef.current) {
      clearTimeout(timerRef.current);
      timerRef.current = null;
    }
  }, []);

  useEffect(() => stop, [stop]);

  const tick = useCallback(
    (jobId: string) => {
      studyApi
        .getJob(jobId)
        .then((data) => {
          setJob(data);
          if (TERMINAL_JOB_STATUSES.includes(data.status)) {
            setIsPolling(false);
            onTerminalRef.current(data);
            return;
          }
          timerRef.current = setTimeout(() => tick(jobId), 2000);
        })
        .catch((err) => {
          setIsPolling(false);
          setError(apiErrorMessage(err));
        });
    },
    // eslint-disable-next-line react-hooks/exhaustive-deps
    []
  );

  const poll = useCallback(
    (jobId: string) => {
      stop();
      setError('');
      setIsPolling(true);
      tick(jobId);
    },
    [stop, tick]
  );

  const reset = useCallback(() => {
    stop();
    setJob(null);
    setIsPolling(false);
    setError('');
  }, [stop]);

  return { job, isPolling, error, poll, reset };
}
