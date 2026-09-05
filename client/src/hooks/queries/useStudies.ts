import { keepPreviousData, useQuery } from '@tanstack/react-query';
import { reportApi } from '../../api/report.api';
import { studyApi, StudyListParams } from '../../api/study.api';
import { Report } from '../../types';
import { queryKeys } from '../../lib/queryKeys';

// A study's status/files change while AI analysis is running, so its cache window is
// shorter than a patient's -- fresh enough that plain navigation (list -> a study -> back)
// still costs nothing, short enough that a doctor working through several studies in a row
// doesn't sit on a minutes-old status.
const STALE_TIME = 20_000;
const JOBS_STALE_TIME = 10_000;

export function useStudiesList(params: StudyListParams) {
  return useQuery({
    queryKey: queryKeys.studies.list(params),
    queryFn: () => studyApi.list(params),
    staleTime: STALE_TIME,
    placeholderData: keepPreviousData,
  });
}

export function useStudy(id: string | undefined) {
  return useQuery({
    queryKey: queryKeys.studies.detail(id ?? ''),
    queryFn: () => studyApi.getById(id!),
    enabled: Boolean(id),
    staleTime: STALE_TIME,
  });
}

export function useStudyJobs(id: string | undefined) {
  return useQuery({
    queryKey: queryKeys.studies.jobs(id ?? ''),
    queryFn: () => studyApi.getJobsForStudy(id!),
    enabled: Boolean(id),
    staleTime: JOBS_STALE_TIME,
  });
}

// KNOWN GAP (CONTRACTS.md §9): there is no GET /studies/{id}/report route, so this mirrors
// the client-side lookup StudyDetail/Dashboard have always done -- list reports by
// patientId and match the one whose studyId is this study, then fetch it in full. Kept as
// its own query (not folded into useStudy) so it can be invalidated/refetched on its own
// after an analysis run or report edit without re-fetching the study itself.
export function useStudyReport(studyId: string | undefined, patientId: string | undefined) {
  return useQuery({
    queryKey: queryKeys.studies.report(studyId ?? ''),
    queryFn: async (): Promise<Report | null> => {
      const { items } = await reportApi.list({ patientId, pageSize: 50 });
      const match = items.find((r) => r.studyId === studyId);
      return match ? reportApi.getById(match.id) : null;
    },
    enabled: Boolean(studyId && patientId),
    staleTime: STALE_TIME,
  });
}
