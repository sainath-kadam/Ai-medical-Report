import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { MAX_VIDEO_SECONDS, readVideoDuration, videoTooLongMessage } from './videoLimits';

// jsdom can't decode media, so stand in for <video> and fire its metadata events by hand.
let behaviour: { duration?: number; error?: boolean; silent?: boolean } = {};

class FakeVideo {
  duration = NaN;
  preload = '';
  onloadedmetadata: (() => void) | null = null;
  onerror: (() => void) | null = null;
  removeAttribute() {}
  set src(_url: string) {
    if (behaviour.silent) return;
    setTimeout(() => {
      if (behaviour.error) return this.onerror?.();
      this.duration = behaviour.duration ?? NaN;
      this.onloadedmetadata?.();
    });
  }
}

const video = (name = 'clip.mp4', type = 'video/mp4') => new File(['x'], name, { type });

describe('video length limit', () => {
  const realCreateElement = document.createElement.bind(document);

  beforeEach(() => {
    behaviour = {};
    URL.createObjectURL = vi.fn(() => 'blob:fake');
    URL.revokeObjectURL = vi.fn();
    vi.spyOn(document, 'createElement').mockImplementation((tag: string) =>
      tag === 'video' ? (new FakeVideo() as unknown as HTMLElement) : realCreateElement(tag)
    );
  });
  afterEach(() => vi.restoreAllMocks());

  it('is 2 minutes', () => {
    expect(MAX_VIDEO_SECONDS).toBe(120);
  });

  it('accepts a video up to 2 minutes (with a 1s tolerance)', async () => {
    behaviour = { duration: 120.6 };
    expect(await videoTooLongMessage(video())).toBeNull();
  });

  it('rejects a longer video with its length in the message', async () => {
    behaviour = { duration: 185 };
    expect(await videoTooLongMessage(video())).toBe(
      'This video is 3:05 long; the limit is 2:00. Trim it and upload it again.'
    );
  });

  it('never checks images', async () => {
    behaviour = { duration: 999 };
    expect(await videoTooLongMessage(video('scan.png', 'image/png'))).toBeNull();
    expect(document.createElement).not.toHaveBeenCalledWith('video');
  });

  it('lets the server decide when the browser cannot read the duration', async () => {
    behaviour = { error: true };
    expect(await videoTooLongMessage(video('scan.avi', 'video/x-msvideo'))).toBeNull();
  });

  it('gives up after the timeout instead of blocking the upload', async () => {
    vi.useFakeTimers();
    behaviour = { silent: true };
    const pending = readVideoDuration(video(), 5000);
    vi.advanceTimersByTime(5000);
    expect(await pending).toBeNull();
    expect(URL.revokeObjectURL).toHaveBeenCalledWith('blob:fake');
    vi.useRealTimers();
  });
});
