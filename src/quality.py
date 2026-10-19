"""Optional OpenCV quality hints and face crops for review previews."""

from __future__ import annotations

import configparser
import math
import sys
import urllib.request
from pathlib import Path


_ROOT = Path(__file__).resolve().parent.parent
_MODEL_PATH = _ROOT / "models" / "face_detection_yunet_2022mar.onnx"
_MODEL_URL = "https://github.com/opencv/opencv_zoo/raw/c97242ce7f/models/face_detection_yunet/face_detection_yunet_2022mar.onnx"
_MODEL_BYTES = 345478
_DEFAULT_CROP_PX = 384
_WARNED = False
_RUNTIME = None
_UNAVAILABLE = None


def _warn_unavailable(exc: Exception) -> None:
    global _WARNED
    if not _WARNED:
        detail = str(exc).replace("\r", " ").replace("\n", " ")
        print(f"warning: OpenCV quality features unavailable: {detail}", file=sys.stderr)
        _WARNED = True


def _ensure_model() -> Path:
    if _MODEL_PATH.is_file():
        if _MODEL_PATH.stat().st_size == _MODEL_BYTES:
            return _MODEL_PATH
        _MODEL_PATH.unlink()
        raise ValueError("cached YuNet model has an unexpected size")

    _MODEL_PATH.parent.mkdir(parents=True, exist_ok=True)
    try:
        with urllib.request.urlopen(_MODEL_URL, timeout=30) as response:
            _MODEL_PATH.write_bytes(response.read())
        if _MODEL_PATH.stat().st_size != _MODEL_BYTES:
            raise ValueError("downloaded YuNet model has an unexpected size")
    except Exception:
        try:
            _MODEL_PATH.unlink()
        except OSError:
            pass
        raise
    return _MODEL_PATH


def _runtime():
    global _RUNTIME, _UNAVAILABLE
    if _UNAVAILABLE is not None:
        raise RuntimeError(_UNAVAILABLE)
    if _RUNTIME is not None:
        return _RUNTIME

    try:
        import cv2
        import numpy as np

        model_path = _ensure_model()
        detector = cv2.FaceDetectorYN.create(str(model_path), "", (320, 320), 0.6, 0.3, 5000)
        _RUNTIME = cv2, np, detector
        return _RUNTIME
    except Exception as exc:
        _UNAVAILABLE = str(exc)
        raise


def _read_and_detect(cv2, np, detector, preview: Path):
    image = cv2.imread(str(preview), cv2.IMREAD_COLOR)
    if image is None or len(image.shape) < 2:
        raise OSError(f"could not read preview: {preview}")
    height, width = image.shape[:2]
    if width <= 0 or height <= 0:
        raise ValueError(f"empty preview: {preview}")
    detector.setInputSize((width, height))
    _count, faces = detector.detect(image)
    if faces is None:
        return image, []
    rows = np.asarray(faces)
    if rows.size == 0:
        return image, []
    if rows.ndim != 2 or rows.shape[1] < 15:
        raise ValueError("YuNet returned an invalid face array")
    return image, rows


def _sharpness(cv2, image, faces) -> float:
    height, width = image.shape[:2]
    gray = cv2.cvtColor(image, cv2.COLOR_BGR2GRAY)
    if len(faces):
        face = max(faces, key=lambda row: float(row[2]) * float(row[3]))
        x, y, face_width, face_height = (float(value) for value in face[:4])
        left = max(0, math.floor(x))
        top = max(0, math.floor(y))
        right = min(width, math.ceil(x + face_width))
        bottom = min(height, math.ceil(y + face_height))
        if right > left and bottom > top:
            gray = gray[top:bottom, left:right]
    return float(cv2.Laplacian(gray, cv2.CV_64F).var())


def hints(previews: list[Path]) -> dict[Path, str]:
    """Return relative Laplacian sharpness and face counts for previews."""
    if not previews:
        return {}
    try:
        cv2, np, detector = _runtime()
        measurements = []
        for preview in previews:
            image, faces = _read_and_detect(cv2, np, detector, preview)
            measurements.append((preview, _sharpness(cv2, image, faces), len(faces)))
        best = max(score for _preview, score, _face_count in measurements)
        result = {}
        for preview, score, face_count in measurements:
            relative = int(round(score * 100 / best)) if best > 0 else 0
            hint = f"sharpness {relative}% of best, faces {face_count}"
            if face_count == 0:
                hint += ", no face detected"
            result[preview] = hint
        return result
    except Exception as exc:
        _warn_unavailable(exc)
        return {}


def _crop_px() -> int:
    for ini_path in sorted((_ROOT / "settings").glob("*.ini")):
        parser = configparser.ConfigParser()
        try:
            parser.read(ini_path, encoding="utf-8")
            value = parser.getint("face", "crop_px")
            if value > 0:
                return value
        except (OSError, ValueError, configparser.Error):
            continue
    return _DEFAULT_CROP_PX


def face_crops(preview: Path, out_dir: Path) -> list[Path]:
    """Save up to three padded, resized face crops for second-stage review."""
    written = []
    try:
        cv2, np, detector = _runtime()
        image, faces = _read_and_detect(cv2, np, detector, preview)
        candidates = [face for face in faces if float(face[14]) >= 0.6]
        candidates.sort(key=lambda row: float(row[2]) * float(row[3]), reverse=True)
        if not candidates:
            return []

        height, width = image.shape[:2]
        crop_px = _crop_px()
        out_dir.mkdir(parents=True, exist_ok=True)
        for index, face in enumerate(candidates[:3], 1):
            x, y, face_width, face_height = (float(value) for value in face[:4])
            center_x = x + face_width / 2
            center_y = y + face_height / 2
            left = max(0, math.floor(center_x - face_width * 0.8))
            top = max(0, math.floor(center_y - face_height * 0.8))
            right = min(width, math.ceil(center_x + face_width * 0.8))
            bottom = min(height, math.ceil(center_y + face_height * 0.8))
            if right <= left or bottom <= top:
                continue
            crop = image[top:bottom, left:right]
            crop_height, crop_width = crop.shape[:2]
            scale = crop_px / float(max(crop_width, crop_height))
            size = (max(1, int(round(crop_width * scale))), max(1, int(round(crop_height * scale))))
            crop = cv2.resize(crop, size, interpolation=cv2.INTER_AREA)
            crop_path = Path(out_dir) / f"face-{index:02d}.jpg"
            if not cv2.imwrite(str(crop_path), crop):
                raise OSError(f"could not write face crop: {crop_path}")
            written.append(crop_path)
        return written
    except Exception as exc:
        for path in written:
            try:
                path.unlink()
            except OSError:
                pass
        _warn_unavailable(exc)
        return []
