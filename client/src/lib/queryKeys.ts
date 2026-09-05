import { AuditLogListParams } from '../hooks/queries/useAuditLogs';
import { PatientListParams } from '../api/patient.api';
import { ReportListParams } from '../api/report.api';
import { StudyListParams } from '../api/study.api';

/** One key-factory per domain, all in one place so a mutation anywhere in the app can
 * invalidate exactly the entries a write actually affects, without guessing a domain's
 * internal key shape. Convention: `domain.all` is the prefix every other key in that
 * domain nests under -- `queryClient.invalidateQueries({queryKey: queryKeys.X.all})`
 * matches every list/detail/sub-resource for that domain in one call, which is what
 * every mutation below actually does (simpler and safer than hand-picking the one exact
 * key a write touched, at the cost of a few extra background refetches). */
export const queryKeys = {
  dashboard: {
    all: ['dashboard'] as const,
    stats: () => [...queryKeys.dashboard.all, 'stats'] as const,
    recentReports: () => [...queryKeys.dashboard.all, 'recentReports'] as const,
  },
  patients: {
    all: ['patients'] as const,
    list: (params: PatientListParams) => [...queryKeys.patients.all, 'list', params] as const,
    detail: (id: string) => [...queryKeys.patients.all, 'detail', id] as const,
    studies: (id: string) => [...queryKeys.patients.all, 'detail', id, 'studies'] as const,
  },
  studies: {
    all: ['studies'] as const,
    list: (params: StudyListParams) => [...queryKeys.studies.all, 'list', params] as const,
    detail: (id: string) => [...queryKeys.studies.all, 'detail', id] as const,
    jobs: (id: string) => [...queryKeys.studies.all, 'detail', id, 'jobs'] as const,
    report: (id: string) => [...queryKeys.studies.all, 'detail', id, 'report'] as const,
  },
  reports: {
    all: ['reports'] as const,
    list: (params: ReportListParams) => [...queryKeys.reports.all, 'list', params] as const,
    detail: (id: string) => [...queryKeys.reports.all, 'detail', id] as const,
  },
  templates: {
    all: ['templates'] as const,
    list: () => [...queryKeys.templates.all, 'list'] as const,
  },
  users: {
    all: ['users'] as const,
    list: (params: { page: number; pageSize: number }) => [...queryKeys.users.all, 'list', params] as const,
  },
  organization: {
    all: ['organization'] as const,
    mine: () => [...queryKeys.organization.all, 'mine'] as const,
  },
  billing: {
    all: ['billing'] as const,
    status: () => [...queryKeys.billing.all, 'status'] as const,
  },
  auditLogs: {
    all: ['auditLogs'] as const,
    list: (params: AuditLogListParams) => [...queryKeys.auditLogs.all, 'list', params] as const,
  },
  platform: {
    all: ['platform'] as const,
    organizations: (params: { page: number; pageSize: number; search?: string }) =>
      [...queryKeys.platform.all, 'organizations', 'list', params] as const,
    organization: (id: string) => [...queryKeys.platform.all, 'organizations', 'detail', id] as const,
    systemAdmins: () => [...queryKeys.platform.all, 'systemAdmins'] as const,
  },
};
