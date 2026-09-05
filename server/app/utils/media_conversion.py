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


def extract_video_frames(data: bytes, max_frames: int) -> list[bytes]:
    """Samples up to `max_frames` evenly-spaced frames from a video (e.g. an ultrasound
    clip) as JPEG bytes, in playback order. OpenCV needs a real file path to open a video,
    so the bytes are spilled to a temp file for the duration of the read. Returns []
    (never raises) if the codec can't be decoded or the file has no frames."""
    if max_frames <= 0:
        return []
    try:
        import cv2
    except ImportError:
        logger.warning("Video conversion skipped: opencv-python-headless not installed")
        return []

    tmp_path: str | None = None
    capture = None
    try:
        with tempfile.NamedTemporaryFile(suffix=".mp4", delete=False) as tmp:
            tmp.write(data)
            tmp_path = tmp.name

        capture = cv2.VideoCapture(tmp_path)
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
            ok, encoded = cv2.imencode(".jpg", frame)
            if ok:
                frames.append(encoded.tobytes())
        return frames
    except Exception:
        logger.warning("Failed to extract video frames", exc_info=True)
        return []
    finally:
        if capture is not None:
            capture.release()
        if tmp_path is not None:
            os.unlink(tmp_path)
