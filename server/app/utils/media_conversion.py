"""Converts non-image study files (raw DICOM, video) into plain images so they can go
through the same `StudyContext.images` path every AI provider already knows how to read —
see `analysis_service.load_study_images`. Both functions fail soft (return `None`/`[]`
rather than raising) so one unreadable file degrades to "unanalyzable", never a 500.
"""

from __future__ import annotations

import io
import os
import tempfile

from app.core.logging import get_logger

logger = get_logger(__name__)


def dicom_to_png_bytes(data: bytes) -> bytes | None:
    """Decodes a DICOM file's pixel data into a windowed 8-bit PNG (the same "apply
    window/level, normalize to grayscale" step a PACS viewer does). Multi-frame series use
    the middle frame as representative. Returns None if the file has no pixel data or uses
    a compressed transfer syntax this install can't decode (no pylibjpeg/gdcm plugin) —
    the caller treats that the same as any other unreadable file."""
    try:
        import numpy as np
        import pydicom
        from PIL import Image
    except ImportError:
        logger.warning("DICOM conversion skipped: pydicom/numpy/pillow not installed")
        return None

    try:
        dataset = pydicom.dcmread(io.BytesIO(data), force=True)
        array = dataset.pixel_array.astype("float64")
    except Exception:
        logger.warning("Failed to decode DICOM pixel data", exc_info=True)
        return None

    if array.ndim == 3 and int(getattr(dataset, "NumberOfFrames", 1) or 1) > 1:
        array = array[array.shape[0] // 2]

    slope = float(getattr(dataset, "RescaleSlope", 1) or 1)
    intercept = float(getattr(dataset, "RescaleIntercept", 0) or 0)
    array = array * slope + intercept

    center = getattr(dataset, "WindowCenter", None)
    width = getattr(dataset, "WindowWidth", None)
    if center is not None and width is not None:
        center = float(center[0] if hasattr(center, "__getitem__") and not isinstance(center, str) else center)
        width = float(width[0] if hasattr(width, "__getitem__") and not isinstance(width, str) else width)
    else:
        center = float((array.max() + array.min()) / 2)
        width = float(array.max() - array.min()) or 1.0
    width = width or 1.0

    low, high = center - width / 2, center + width / 2
    array = np.clip(array, low, high)
    array = ((array - low) / (high - low) * 255.0).astype("uint8")

    if str(getattr(dataset, "PhotometricInterpretation", "")) == "MONOCHROME1":
        array = 255 - array

    buffer = io.BytesIO()
    Image.fromarray(array).save(buffer, format="PNG")
    return buffer.getvalue()


# --- Video ---------------------------------------------------------------------------
# Frames for the AI are cut by code (OpenCV), not by the AI: evenly spaced from start to
# end, at full resolution, from the ORIGINAL upload — before any compression — so the
# stored, compressed reference copy can never cost the analysis any detail.
VIDEO_MIN_FRAMES = 8
VIDEO_MAX_FRAMES = 16
VIDEO_SECONDS_PER_FRAME = 4
# JPEG quality for the frames sent to the AI (and kept for re-analysis). 95 is visually
# lossless; OpenCV's default is also 95, made explicit here because it matters.
_FRAME_JPEG_QUALITY = 95


def video_frame_count(duration_seconds: float | None) -> int:
    """How many frames to cut from a video of this length: 8 for clips up to 30s, then one
    per 4 seconds, capped at 16 (enough coverage without making every report slower and
    costlier). Unknown duration -> the minimum."""
    if not duration_seconds or duration_seconds <= 0:
        return VIDEO_MIN_FRAMES
    return max(VIDEO_MIN_FRAMES, min(VIDEO_MAX_FRAMES, round(duration_seconds / VIDEO_SECONDS_PER_FRAME)))


def probe_video(path: str) -> tuple[int, float | None]:
    """(frame_count, duration_seconds) via OpenCV; (0, None) if it can't be opened."""
    try:
        import cv2
    except ImportError:
        return 0, None
    capture = cv2.VideoCapture(path)
    try:
        frames = int(capture.get(cv2.CAP_PROP_FRAME_COUNT) or 0)
        fps = float(capture.get(cv2.CAP_PROP_FPS) or 0)
        return max(frames, 0), (frames / fps if frames > 0 and fps > 0 else None)
    finally:
        capture.release()


def extract_video_frames_from_path(path: str, max_frames: int) -> list[bytes]:
    """Samples up to `max_frames` evenly-spaced frames from the video at `path` as JPEG
    bytes, in playback order, at the video's full resolution. Reads from disk frame by
    frame, so a 1GB upload never has to be held in memory. Returns [] (never raises) if
    the codec can't be decoded or the file has no frames."""
    if max_frames <= 0:
        return []
    try:
        import cv2
    except ImportError:
        logger.warning("Video conversion skipped: opencv-python-headless not installed")
        return []

    capture = None
    try:
        capture = cv2.VideoCapture(path)
        total_frames = int(capture.get(cv2.CAP_PROP_FRAME_COUNT))
        if total_frames <= 0:
            return []

        count = min(max_frames, total_frames)
        indices = [round(i * (total_frames - 1) / max(count - 1, 1)) for i in range(count)]

        frames: list[bytes] = []
        for index in indices:
            capture.set(cv2.CAP_PROP_POS_FRAMES, index)
            ok, frame = capture.read()
            if not ok:
                continue
            ok, encoded = cv2.imencode(".jpg", frame, [cv2.IMWRITE_JPEG_QUALITY, _FRAME_JPEG_QUALITY])
            if ok:
                frames.append(encoded.tobytes())
        return frames
    except Exception:
        logger.warning("Failed to extract video frames", exc_info=True)
        return []
    finally:
        if capture is not None:
            capture.release()


def extract_video_frames(data: bytes, max_frames: int) -> list[bytes]:
    """`extract_video_frames_from_path` for a video already in memory (videos stored before
    frames were saved at upload time). OpenCV needs a real file path, so the bytes are
    spilled to a temp file for the duration of the read."""
    if max_frames <= 0:
        return []
    fd, tmp_path = tempfile.mkstemp(suffix=".mp4")
    try:
        with os.fdopen(fd, "wb") as tmp:
            tmp.write(data)
        return extract_video_frames_from_path(tmp_path, max_frames)
    finally:
        os.unlink(tmp_path)


def _ffmpeg_exe() -> str:
    import imageio_ffmpeg

    return imageio_ffmpeg.get_ffmpeg_exe()


def compression_bitrate_kbps(duration_seconds: float | None, max_mb: int) -> int:
    """Video bitrate cap that keeps a clip of this length under `max_mb` (with 10% headroom
    for container overhead): long videos get a lower bitrate, short ones never above
    4 Mbps (plenty for grayscale imaging at <=1280px). Clamped to >=150 kbps."""
    if not duration_seconds or duration_seconds <= 0:
        return 2000
    budget_kbps = (max_mb * 8 * 1024 * 0.9) / duration_seconds
    return int(max(150, min(4000, budget_kbps)))


async def compress_video(src_path: str, dst_path: str, *, duration_seconds: float | None, max_mb: int) -> None:
    """Re-encodes the video at `src_path` to a browser-playable H.264 MP4 at `dst_path` for
    storage as the doctor's reference copy: no audio, at most 1280px wide, quality-based
    (CRF 26) but capped so the result fits `max_mb`. Runs ffmpeg as a subprocess, so it
    never blocks the event loop. Raises RuntimeError if ffmpeg fails."""
    import asyncio

    kbps = compression_bitrate_kbps(duration_seconds, max_mb)
    process = await asyncio.create_subprocess_exec(
        _ffmpeg_exe(), "-hide_banner", "-loglevel", "error", "-y",
        "-i", src_path,
        "-an",
        "-vf", "scale='trunc(min(1280,iw)/2)*2':-2",
        "-c:v", "libx264", "-preset", "veryfast", "-crf", "26",
        "-maxrate", f"{kbps}k", "-bufsize", f"{kbps * 2}k",
        "-pix_fmt", "yuv420p", "-movflags", "+faststart",
        dst_path,
        stdout=asyncio.subprocess.DEVNULL,
        stderr=asyncio.subprocess.PIPE,
    )
    _, stderr = await process.communicate()
    if process.returncode != 0:
        raise RuntimeError(f"ffmpeg exited {process.returncode}: {stderr.decode(errors='replace')[-500:]}")
