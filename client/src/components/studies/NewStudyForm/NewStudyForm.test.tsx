import { act, fireEvent, render, screen } from '@testing-library/react';
import { afterEach, describe, expect, it, vi } from 'vitest';

const intake = vi.fn();
vi.mock('../../../api/study.api', () => ({
  MAX_STUDY_FILE_BYTES: 1024 * 1024 * 1024,
  studyApi: { intake: (...args: unknown[]) => intake(...args) },
}));
const NO_TEMPLATES = { data: [] };
const NO_PATIENTS = { data: { items: [] } };
const NO_PATIENT = { data: undefined };
const videoTooLongMessage = vi.fn().mockResolvedValue(null);
vi.mock('../../../utils/videoLimits', () => ({ videoTooLongMessage: (file: File) => videoTooLongMessage(file) }));
vi.mock('../../../hooks/queries/useTemplates', () => ({ useTemplatesList: () => NO_TEMPLATES }));
vi.mock('../../../hooks/queries/usePatients', () => ({
  usePatientsList: () => NO_PATIENTS,
  usePatient: () => NO_PATIENT,
}));

import NewStudyForm from './NewStudyForm';

function fileOfSize(bytes: number) {
  const file = new File(['x'], 'brain.mp4', { type: 'video/mp4' });
  Object.defineProperty(file, 'size', { value: bytes });
  return file;
}

function fillAndSubmit(file: File) {
  const { container } = render(<NewStudyForm onComplete={vi.fn()} />);
  fireEvent.click(screen.getByRole('button', { name: /new patient/i }));
  fireEvent.change(screen.getByLabelText('Full name'), { target: { value: 'Mri Video' } });
  fireEvent.change(screen.getByLabelText('Date of birth'), { target: { value: '1975-03-03' } });
  fireEvent.change(screen.getByLabelText('Body part'), { target: { value: 'Brain' } });
  fireEvent.change(container.querySelector('input[type="file"]')!, { target: { files: [file] } });
  fireEvent.submit(container.querySelector('form')!);
}

describe('NewStudyForm large uploads', () => {
  // Reset AFTER each test, not before: a mock still holding the fake 1GB File in its call
  // history makes Vitest's teardown hang (it tries to read the "1GB" of bytes).
  afterEach(() => intake.mockReset());

  it('rejects a file over 1GB without sending anything', async () => {
    fillAndSubmit(fileOfSize(1024 * 1024 * 1024 + 1));

    expect(await screen.findByText('This file is larger than the 1GB upload limit.')).toBeInTheDocument();
    expect(intake).not.toHaveBeenCalled();
  });

  it('rejects a video over 2 minutes before uploading anything', async () => {
    videoTooLongMessage.mockResolvedValueOnce('This video is 3:05 long; the limit is 2:00. Trim it and upload it again.');

    fillAndSubmit(fileOfSize(10));

    expect(await screen.findByText(/This video is 3:05 long/)).toBeInTheDocument();
    expect(intake).not.toHaveBeenCalled();
  });

  it('accepts a file of exactly 1GB and shows upload progress, then the analyzing state', async () => {
    let reportProgress: (percent: number) => void = () => {};
    let finish: (value: unknown) => void = () => {};
    intake.mockImplementation((_payload, _file, onProgress) => {
      reportProgress = onProgress;
      return new Promise((resolve) => (finish = resolve));
    });

    fillAndSubmit(fileOfSize(1024 * 1024 * 1024));

    expect(await screen.findByText('Uploading file… 0%')).toBeInTheDocument();
    expect(intake).toHaveBeenCalledTimes(1);
    act(() => reportProgress(42));
    expect(screen.getByText('Uploading file… 42%')).toBeInTheDocument();
    act(() => reportProgress(100));
    expect(screen.getByText(/Upload complete — preparing the scan for the AI/)).toBeInTheDocument();

    await act(async () => finish({ study: {}, report: null, analysisJobId: null }));
    expect(screen.queryByText(/Upload complete/)).not.toBeInTheDocument();
  });

  it('clears the progress text and shows the error when the request fails', async () => {
    intake.mockRejectedValue(new Error('boom'));

    fillAndSubmit(fileOfSize(10));

    expect(await screen.findByText('Something went wrong')).toBeInTheDocument();
    expect(screen.queryByText(/Uploading file/)).not.toBeInTheDocument();
  });
});
