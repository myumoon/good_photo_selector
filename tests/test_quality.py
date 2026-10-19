import json
import sys
import types
import urllib.request
from pathlib import Path

import numpy as np
import pytest

import quality


def _contract():
    path = Path(__file__).resolve().parents[1] / "contracts" / "yunet.contract.json"
    return json.loads(path.read_text(encoding="utf-8"))


def _face(x, y, width, height, score):
    return [x, y, width, height, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, score]


@pytest.fixture(autouse=True)
def reset_warning_state(monkeypatch):
    monkeypatch.setattr(quality, "_WARNED", False, raising=False)


def _install_cv(monkeypatch, tmp_path, faces, images=None, download_error=None, create_error=None,
                detect_error=None):
    probe = next(item for item in _contract()["probes"] if item["id"] == "yunet.download.2022mar")
    expected_size = probe["response"]["bytes"]
    model_path = tmp_path / "models" / "face_detection_yunet_2022mar.onnx"
    monkeypatch.setattr(quality, "_MODEL_PATH", model_path, raising=False)
    calls = {"downloads": [], "sizes": [], "laplacian_shapes": [], "writes": []}
    detector_calls = {"index": 0}

    def urlretrieve(url, destination):
        calls["downloads"].append(url)
        calls["destination"] = Path(destination)
        if download_error:
            raise download_error
        Path(destination).write_bytes(b"x" * expected_size)

    monkeypatch.setattr(urllib.request, "urlretrieve", urlretrieve)

    class Detector:
        def setInputSize(self, size):
            self.input_size = size
            calls["sizes"].append(size)

        def detect(self, image):
            assert self.input_size == (image.shape[1], image.shape[0])
            if detect_error:
                raise detect_error
            index = detector_calls["index"]
            detector_calls["index"] += 1
            found = faces[index] if index < len(faces) else None
            return (0, None) if found is None else (len(found), np.asarray(found, dtype=np.float32))

    def create(*args, **kwargs):
        calls["create"] = (args, kwargs)
        if create_error:
            raise create_error
        return Detector()

    fake_cv = types.ModuleType("cv2")
    fake_cv.IMREAD_COLOR = 1
    fake_cv.COLOR_BGR2GRAY = 6
    fake_cv.CV_64F = 6
    fake_cv.INTER_AREA = 3
    fake_cv.FaceDetectorYN = types.SimpleNamespace(create=create)
    fake_cv.imread = lambda path, _flag: (images or {}).get(str(path))
    fake_cv.cvtColor = lambda image, _code: image[:, :, 0]

    def laplacian(gray, _depth):
        calls["laplacian_shapes"].append(gray.shape)
        return gray

    fake_cv.Laplacian = laplacian
    fake_cv.resize = lambda image, size, **_kwargs: np.zeros(
        (size[1], size[0], image.shape[2]), dtype=image.dtype,
    )

    def imwrite(path, image):
        calls["writes"].append((Path(path), image.shape))
        return True

    fake_cv.imwrite = imwrite
    monkeypatch.setitem(sys.modules, "cv2", fake_cv)
    return calls


def test_hints_use_largest_face_and_mark_images_without_faces(monkeypatch, tmp_path):
    checker = (np.indices((8, 10)).sum(axis=0) % 2 * 255).astype(np.uint8)
    images = {
        str(tmp_path / "one.jpg"): np.repeat(checker[:, :, None], 3, axis=2),
        str(tmp_path / "two.jpg"): np.zeros((8, 10, 3), dtype=np.uint8),
    }
    calls = _install_cv(
        monkeypatch,
        tmp_path,
        [[_face(0, 0, 2, 2, 0.95), _face(2, 1, 4, 5, 0.7)], None],
        images,
    )

    previews = [Path(tmp_path / "one.jpg"), Path(tmp_path / "two.jpg")]
    result = quality.hints(previews)

    assert "sharpness 100% of best, faces 2" == result[previews[0]]
    assert "sharpness 0% of best, faces 0, no face detected" == result[previews[1]]
    assert calls["laplacian_shapes"] == [(5, 4), (8, 10)]
    assert calls["sizes"] == [(10, 8), (10, 8)]


def test_face_crops_filters_sorts_limits_and_resizes(monkeypatch, tmp_path):
    preview = tmp_path / "preview.jpg"
    monkeypatch.setattr(quality, "_ROOT", tmp_path, raising=False)
    settings = tmp_path / "settings"
    settings.mkdir()
    (settings / "config.ini").write_text("[face]\ncrop_px = 40\n", encoding="utf-8")
    images = {str(preview): np.zeros((100, 100, 3), dtype=np.uint8)}
    faces = [[
        _face(20, 20, 8, 8, 0.9),
        _face(30, 30, 7, 7, 0.6),
        _face(40, 40, 6, 6, 0.7),
        _face(50, 50, 5, 5, 0.59),
        _face(60, 60, 4, 4, 0.8),
        _face(70, 70, 3, 3, 0.9),
    ]]
    calls = _install_cv(monkeypatch, tmp_path, faces, images)
    out_dir = tmp_path / "faces"

    result = quality.face_crops(preview, out_dir)

    assert [path.name for path in result] == ["face-01.jpg", "face-02.jpg", "face-03.jpg"]
    assert [shape[:2] for _path, shape in calls["writes"]] == [(40, 40), (40, 40), (40, 40)]
    assert calls["sizes"] == [(100, 100)]


def test_face_crops_returns_empty_when_no_faces(monkeypatch, tmp_path):
    preview = tmp_path / "preview.jpg"
    image = np.zeros((32, 48, 3), dtype=np.uint8)
    calls = _install_cv(monkeypatch, tmp_path, [None], {str(preview): image})

    assert quality.face_crops(preview, tmp_path / "faces") == []
    assert calls["sizes"] == [(48, 32)]


def test_download_uses_contract_url_and_exact_size(monkeypatch, tmp_path):
    contract = _contract()
    probe = next(item for item in contract["probes"] if item["id"] == "yunet.download.2022mar")
    preview = tmp_path / "preview.jpg"
    image = np.zeros((8, 10, 3), dtype=np.uint8)
    calls = _install_cv(monkeypatch, tmp_path, [None], {str(preview): image})

    assert quality.hints([preview])

    assert calls["downloads"] == [probe["request"]["url"]]
    assert calls["destination"].stat().st_size == probe["response"]["bytes"]


def test_opencv_missing_skips_both_quality_features_and_warns_once(monkeypatch, capsys, tmp_path):
    monkeypatch.setitem(sys.modules, "cv2", None)
    preview = tmp_path / "preview.jpg"

    assert quality.hints([preview]) == {}
    assert quality.face_crops(preview, tmp_path / "faces") == []
    assert len(capsys.readouterr().err.splitlines()) == 1


def test_model_download_failure_returns_empty_results_and_warns_once(monkeypatch, capsys, tmp_path):
    preview = tmp_path / "preview.jpg"
    image = np.zeros((8, 10, 3), dtype=np.uint8)
    _install_cv(monkeypatch, tmp_path, [None], {str(preview): image}, OSError("offline"))

    assert quality.hints([preview]) == {}
    assert quality.face_crops(preview, tmp_path / "faces") == []
    assert len(capsys.readouterr().err.splitlines()) == 1


def test_wrong_model_size_is_deleted_and_not_used(monkeypatch, tmp_path):
    preview = tmp_path / "preview.jpg"
    model_path = tmp_path / "models" / "face_detection_yunet_2022mar.onnx"
    image = np.zeros((8, 10, 3), dtype=np.uint8)
    calls = _install_cv(monkeypatch, tmp_path, [None], {str(preview): image})
    monkeypatch.setattr(urllib.request, "urlretrieve", lambda _url, path: Path(path).write_bytes(b"bad"))

    assert quality.hints([preview]) == {}
    assert calls["downloads"]
    assert not model_path.exists()
    assert "create" not in calls


def test_yunet_initialization_and_detection_errors_fail_open(monkeypatch, tmp_path):
    preview = tmp_path / "preview.jpg"
    image = np.zeros((8, 10, 3), dtype=np.uint8)
    calls = _install_cv(
        monkeypatch,
        tmp_path,
        [None],
        {str(preview): image},
        create_error=RuntimeError("unsupported YuNet model"),
    )

    assert quality.hints([preview]) == {}
    assert calls["create"]
