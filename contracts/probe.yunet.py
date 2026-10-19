#!/usr/bin/env python3
"""OpenCV 内蔵 YuNet(cv2.FaceDetectorYN)の契約を OpenCV 4.6 で実測する。

    python3 probe.yunet.py <output-contract.json> <model_dir> <nef_path>

Surfaces:
  - モデル取得 URL(opencv_zoo。2023mar は OpenCV 4.8+ 専用、4.6 では 2022mar をコミット固定で取る)
  - cv2.FaceDetectorYN.create(model, "", (w, h), score, nms, topk).detect(img) の返り値の形
  - 入力サイズと setInputSize の不一致の挙動
"""

import json
import os
import sys
import urllib.request
from datetime import datetime, timezone
from pathlib import Path

import cv2
import numpy as np

URL_2022 = "https://github.com/opencv/opencv_zoo/raw/c97242ce7f/models/face_detection_yunet/face_detection_yunet_2022mar.onnx"
URL_2023 = "https://github.com/opencv/opencv_zoo/raw/main/models/face_detection_yunet/face_detection_yunet_2023mar.onnx"


def _utc_now():
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def fetch(url, dest):
    if not dest.exists():
        urllib.request.urlretrieve(url, dest)
    return {"bytes": dest.stat().st_size, "head8": dest.read_bytes()[:8].hex()}


def load_preview(nef):
    sys.path.insert(0, "H:/prog/0_myprogram/linestamp_creator/tools")
    from linestamp.imaging.raw_preview import extract_embedded_jpeg
    buf = np.frombuffer(extract_embedded_jpeg(Path(nef)), np.uint8)
    return cv2.imdecode(buf, cv2.IMREAD_COLOR)


def detect(model, img, size, score=0.6, nms=0.3, topk=5000):
    try:
        det = cv2.FaceDetectorYN.create(str(model), "", size, score, nms, topk)
        n, faces = det.detect(img)
    except cv2.error as e:
        return {"error": str(e).splitlines()[-1][:160]}
    rows = [] if faces is None else faces.tolist()
    return {"input_shape": list(img.shape), "set_input_size": list(size), "count": len(rows),
            "row_len": None if not rows else len(rows[0]),
            "faces": [[round(v, 1) for v in r] for r in rows[:3]],
            "row_layout": "x, y, w, h, re_x, re_y, le_x, le_y, nose_x, nose_y, rm_x, rm_y, lm_x, lm_y, score"}


def main(argv):
    out_path, model_dir, nef = argv[1], Path(argv[2]), argv[3]
    model_dir.mkdir(parents=True, exist_ok=True)
    m22, m23 = model_dir / "face_detection_yunet_2022mar.onnx", model_dir / "face_detection_yunet_2023mar.onnx"
    probes, silent = [], []
    probes.append({"id": "yunet.download.2022mar", "surface": "YuNet model download", "arguments_exercised": True,
                   "request": {"url": URL_2022}, "response": fetch(URL_2022, m22)})
    probes.append({"id": "yunet.download.2023mar", "surface": "YuNet model download", "arguments_exercised": True,
                   "request": {"url": URL_2023}, "response": fetch(URL_2023, m23)})

    src = load_preview(nef)
    h0, w0 = src.shape[:2]
    s = 1024 / max(h0, w0)
    img = cv2.resize(src, (int(w0 * s), int(h0 * s)))
    size = (img.shape[1], img.shape[0])
    r22 = detect(m22, img, size)
    r23 = detect(m23, img, size)
    probes.append({"id": "yunet.detect.2022mar", "surface": "cv2.FaceDetectorYN.detect", "arguments_exercised": True,
                   "request": {"model": m22.name, "cv2": cv2.__version__, "nef": Path(nef).name, "long_edge": 1024},
                   "response": r22})
    probes.append({"id": "yunet.detect.2023mar", "surface": "cv2.FaceDetectorYN.detect", "arguments_exercised": True,
                   "request": {"model": m23.name, "cv2": cv2.__version__, "nef": Path(nef).name, "long_edge": 1024},
                   "response": r23})
    silent.append({"id": "yunet.model.2023mar-on-cv46", "surface": "YuNet model download",
                   "correct_request": {"url": URL_2022}, "wrong_request": {"url": URL_2023},
                   "responses_identical": ("error" in r22) == ("error" in r23) and r22.get("count") == r23.get("count"),
                   "impact": "2023mar は OpenCV 4.8+ 専用で 4.6(Windows テスト環境・Ubuntu 24.04 apt)では create/detect が例外になる",
                   "guard": "4.6 互換の 2022mar をコミット固定 URL で取得する。create 失敗は例外で分かるので黙殺はされない"})

    # trap: setInputSize と実画像サイズの不一致
    wrong_size = (640, 640)
    r_mismatch = detect(m22, img, wrong_size)
    probes.append({"id": "yunet.detect.size-mismatch", "surface": "cv2.FaceDetectorYN.detect", "arguments_exercised": True,
                   "request": {"model": m22.name, "image_shape": list(img.shape), "set_input_size": list(wrong_size)},
                   "response": r_mismatch})
    silent.append({"id": "yunet.detect.input-size-mismatch", "surface": "cv2.FaceDetectorYN.detect",
                   "correct_request": {"set_input_size": list(size), "image_shape": list(img.shape)},
                   "wrong_request": {"set_input_size": list(wrong_size), "image_shape": list(img.shape)},
                   "responses_identical": r_mismatch.get("count") == r22.get("count") and "error" not in r_mismatch,
                   "impact": "create()/setInputSize の (w,h) が渡す画像と違っても例外にならず、検出 0 件や座標ずれが黙って返る",
                   "guard": "detect 直前に必ず setInputSize((img.shape[1], img.shape[0])) を呼ぶ。テストで size 不一致時の count を assert する"})

    out = {"schema_version": 1, "name": "yunet", "captured_at": _utc_now(),
           "target": {"kind": "file", "identity": f"cv2 {cv2.__version__} (Windows, Anaconda py3.9) + opencv_zoo YuNet", "base": None},
           "probes": probes, "silent_ignore": silent}
    Path(out_path).write_text(json.dumps(out, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({"status": "DONE", "r22": {k: r22.get(k) for k in ("count", "error")},
                      "r23": {k: r23.get(k) for k in ("count", "error")},
                      "mismatch": {k: r_mismatch.get(k) for k in ("count", "error", "faces")}}, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
