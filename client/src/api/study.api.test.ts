import { beforeEach, describe, expect, it, vi } from 'vitest';

const post = vi.fn();
vi.mock('./axiosInstance', () => ({ api: { post: (...args: unknown[]) => post(...args) } }));

import { MAX_STUDY_FILE_BYTES, studyApi } from './study.api';

type UploadConfig = { timeout: number; onUploadProgress?: (event: { loaded: number; total?: number }) => void };

const intakePayload = {
  newPatient: { name: 'Mri Video', age: 51, sex: 'female' as const },
  modality: 'mri' as const,
  bodyPart: 'Brain',
  studyDate: '2026-09-01',
  runAnalysis: true,
};

function lastConfig(): UploadConfig {
  return post.mock.calls[post.mock.calls.length - 1][2] as UploadConfig;
}

describe('study file uploads', () => {
  beforeEach(() => {
    post.mockReset();
    post.mockResolvedValue({ data: { data: {} } });
  });

  it('caps study files at 1GB, matching the server default', () => {
    expect(MAX_STUDY_FILE_BYTES).toBe(1024 * 1024 * 1024);
  });

  it('intake disables the 120s client timeout so large videos + analysis can finish', async () => {
    await studyApi.intake(intakePayload, new File(['x'], 'brain.mp4', { type: 'video/mp4' }));

    expect(post.mock.calls[0][0]).toBe('/studies/intake');
    expect(lastConfig().timeout).toBe(0);
  });

  it('intake reports upload progress as a whole-number percent', async () => {
    const onProgress = vi.fn();
    await studyApi.intake(intakePayload, new File(['x'], 'brain.mp4', { type: 'video/mp4' }), onProgress);

    const { onUploadProgress } = lastConfig();
    onUploadProgress!({ loaded: 1, total: 3 });
    onUploadProgress!({ loaded: 3, total: 3 });
    onUploadProgress!({ loaded: 5 }); // unknown total -> ignored
    expect(onProgress.mock.calls).toEqual([[33], [100]]);
  });

  it('uploadFile also disables the timeout and forwards progress', async () => {
    const onProgress = vi.fn();
    await studyApi.uploadFile('study1', new File(['x'], 'clip.mp4', { type: 'video/mp4' }), onProgress);

    expect(post.mock.calls[0][0]).toBe('/uploads/studies/study1/files');
    expect(lastConfig().timeout).toBe(0);
    lastConfig().onUploadProgress!({ loaded: 50, total: 100 });
    expect(onProgress).toHaveBeenCalledWith(50);
  });

  it('omits the progress handler when no callback is given', async () => {
    await studyApi.uploadFile('study1', new File(['x'], 'clip.mp4', { type: 'video/mp4' }));
    expect(lastConfig().onUploadProgress).toBeUndefined();
  });
});
