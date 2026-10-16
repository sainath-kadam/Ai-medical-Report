import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { act, fireEvent, render, screen } from '@testing-library/react';
import { MemoryRouter } from 'react-router-dom';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';

// The analysis now runs in the background: intake returns a job id with no report, and
// the dashboard polls the job, showing progress, then opens the report (or the failure).

const getJob = vi.fn();
const runAnalysis = vi.fn();
vi.mock('../../api/study.api', () => ({
  studyApi: { getJob: (id: string) => getJob(id), runAnalysis: (id: string) => runAnalysis(id) },
}));
const listReports = vi.fn();
const getReport = vi.fn();
vi.mock('../../api/report.api', () => ({
  reportApi: { list: (p: unknown) => listReports(p), getById: (id: string) => getReport(id) },
}));
vi.mock('../../hooks/queries/useDashboard', () => ({
  useDashboardStats: () => ({ data: undefined, isLoading: false }),
  useDashboardRecentReports: () => ({ data: [], isLoading: false }),
}));
vi.mock('../../hooks/useAuth', () => ({ useAuth: () => ({ user: { name: 'Dr. Test', role: 'doctor' } }) }));

const study = { id: 'study1', patientId: 'p1' };
// Stand-in for the real form: "submits" and hands the dashboard an intake result.
vi.mock('../../components/studies/NewStudyForm/NewStudyForm', () => ({
  default: ({ onComplete }: { onComplete: (r: unknown) => void }) => (
    <button onClick={() => onComplete({ study, report: null, analysisJobId: 'job1' })}>submit intake</button>
  ),
}));
vi.mock('../../components/reports/ReportWorkspace/ReportWorkspace', () => ({
  default: ({ report }: { report: { id: string } }) => <div>report workspace {report.id}</div>,
}));

import Dashboard from './Dashboard';

const job = (status: string, extra = {}) => ({ id: 'job1', status, error: null, errorCode: null, ...extra });

function renderDashboard() {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <QueryClientProvider client={client}>
      <MemoryRouter initialEntries={['/dashboard?startUpload=1']}>
        <Dashboard />
      </MemoryRouter>
    </QueryClientProvider>
  );
}

async function flush() {
  await act(async () => {
    await Promise.resolve();
  });
}

describe('Dashboard background analysis', () => {
  beforeEach(() => vi.useFakeTimers({ shouldAdvanceTime: true }));
  afterEach(() => {
    vi.useRealTimers();
    vi.clearAllMocks();
  });

  it('shows progress while the AI runs, then opens the finished report by itself', async () => {
    getJob
      .mockResolvedValueOnce(job('analyzing'))
      .mockResolvedValueOnce(job('generating_report'))
      .mockResolvedValueOnce(job('completed'));
    listReports.mockResolvedValue({ items: [{ id: 'r1', studyId: 'study1' }] });
    getReport.mockResolvedValue({ id: 'r1', studyId: 'study1', currentVersion: 1, versions: [] });

    renderDashboard();
    fireEvent.click(screen.getByText('submit intake'));

    expect(await screen.findByRole('heading', { name: 'Generating report' })).toBeInTheDocument();
    expect(await screen.findByText('Analyzing imaging…')).toBeInTheDocument();

    await act(async () => {
      vi.advanceTimersByTime(2000);
    });
    expect(await screen.findByText('Generating report…')).toBeInTheDocument();

    await act(async () => {
      vi.advanceTimersByTime(2000);
    });
    expect(await screen.findByText('report workspace r1')).toBeInTheDocument();
    expect(getJob).toHaveBeenCalledTimes(3);
  });

  it('shows the failure with a retry, and retrying watches the new job', async () => {
    getJob.mockResolvedValueOnce(job('failed', { error: 'Gemini 503', errorCode: 'AI_TEMPORARILY_UNAVAILABLE' }));
    runAnalysis.mockResolvedValue({ jobId: 'job2', report: null });

    renderDashboard();
    fireEvent.click(screen.getByText('submit intake'));

    expect(await screen.findByText(/the AI analysis failed/)).toBeInTheDocument();

    getJob.mockResolvedValueOnce(job('queued'));
    fireEvent.click(screen.getByText('Retry AI analysis'));
    await flush();

    expect(runAnalysis).toHaveBeenCalledWith('study1');
    expect(await screen.findByRole('heading', { name: 'Generating report' })).toBeInTheDocument();
    expect(getJob).toHaveBeenLastCalledWith('job2');
  });
});
