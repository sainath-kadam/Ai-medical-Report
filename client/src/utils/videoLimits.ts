// Longest accepted video -- mirrors the server's VIDEO_MAX_SECONDS (default 120). Checked
// here before uploading so nobody waits through a large upload only to be rejected; the
// server checks again either way.
export const MAX_VIDEO_SECONDS = 120;
// Matches the server's tolerance: container durations are often a fraction of a second off.
const TOLERANCE_SECONDS = 1;

function formatDuration(seconds: number) {
  const whole = Math.round(seconds);
  return `${Math.floor(whole / 60)}:${String(whole % 60).padStart(2, '0')}`;
}

/** The video's duration in seconds, read from its metadata by the browser (no upload).
 *  Resolves null if it can't be read (unsupported codec, not a video, or no answer within
 *  `timeoutMs`) -- the server then decides. */
export function readVideoDuration(file: File, timeoutMs = 10_000): Promise<number | null> {
  return new Promise((resolve) => {
    const url = URL.createObjectURL(file);
    const video = document.createElement('video');
    let timer: ReturnType<typeof setTimeout> | undefined;
    const finish = (value: number | null) => {
      clearTimeout(timer);
      video.removeAttribute('src');
      URL.revokeObjectURL(url);
      resolve(value);
    };
    timer = setTimeout(() => finish(null), timeoutMs);
    video.preload = 'metadata';
    video.onloadedmetadata = () => finish(Number.isFinite(video.duration) ? video.duration : null);
    video.onerror = () => finish(null);
    video.src = url;
  });
}

/** An error message if `file` is a video longer than MAX_VIDEO_SECONDS, else null. */
export async function videoTooLongMessage(file: File): Promise<string | null> {
  if (!file.type.startsWith('video/')) return null;
  const duration = await readVideoDuration(file);
  if (duration === null || duration <= MAX_VIDEO_SECONDS + TOLERANCE_SECONDS) return null;
  return `This video is ${formatDuration(duration)} long; the limit is ${formatDuration(MAX_VIDEO_SECONDS)}. Trim it and upload it again.`;
}
