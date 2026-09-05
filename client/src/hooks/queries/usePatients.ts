import { keepPreviousData, useQuery } from '@tanstack/react-query';
import { patientApi, PatientListParams } from '../../api/patient.api';
import { queryKeys } from '../../lib/queryKeys';

// A patient record changes rarely once created -- 30s of "still fresh, don't refetch" is
// plenty to make the common back-and-forth (list -> a patient -> back to the list, or
// list -> a patient -> one of their studies -> back) cost zero network requests.
const STALE_TIME = 30_000;

export function usePatientsList(params: PatientListParams) {
  return useQuery({
    queryKey: queryKeys.patients.list(params),
    queryFn: () => patientApi.list(params),
    staleTime: STALE_TIME,
    // Keep showing the previous page's rows (marked `isPlaceholderData`) while a new
    // page/search loads, instead of flashing the whole table out for a spinner.
    placeholderData: keepPreviousData,
  });
}

export function usePatient(id: string | undefined) {
  return useQuery({
    queryKey: queryKeys.patients.detail(id ?? ''),
    queryFn: () => patientApi.getById(id!),
    enabled: Boolean(id),
    staleTime: STALE_TIME,
  });
}

// Same cache entry StudyDetail's patient-fallback lookup reads (see useStudies.ts) --
// visiting a patient's own page and a study of theirs share one cached record.
export function usePatientStudies(id: string | undefined) {
  return useQuery({
    queryKey: queryKeys.patients.studies(id ?? ''),
    queryFn: () => patientApi.getStudies(id!),
    enabled: Boolean(id),
    staleTime: STALE_TIME,
  });
}
