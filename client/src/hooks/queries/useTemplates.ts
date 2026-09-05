import { useQuery } from '@tanstack/react-query';
import { templateApi } from '../../api/template.api';
import { queryKeys } from '../../lib/queryKeys';

// An organization's report templates are a configure-once-in-a-while thing (branding,
// sections) -- cache them longer than the clinical-data domains above. Shared verbatim
// between the Templates settings page and NewStudyForm's template picker, so opening the
// upload flow after visiting Templates (or vice versa) never re-fetches.
const STALE_TIME = 60_000;

export function useTemplatesList() {
  return useQuery({
    queryKey: queryKeys.templates.list(),
    queryFn: () => templateApi.list(),
    staleTime: STALE_TIME,
  });
}
