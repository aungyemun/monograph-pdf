"""Local Tesseract subprocess engine — no network, project tessdata only."""

from __future__ import annotations

import os
import subprocess
import tempfile
from dataclasses import dataclass
from pathlib import Path

from core.ocr.paths import (
    language_files_present,
    ocr_ready,
    tessdata_dir,
    tesseract_exe,
)


class OcrUnavailableError(RuntimeError):
    pass


# Run tesseract.exe without flashing a console window in the windowed app
_NO_WINDOW = getattr(subprocess, "CREATE_NO_WINDOW", 0)


@dataclass
class RawOcrToken:
    text: str
    conf: float  # 0-100
    left: int
    top: int
    width: int
    height: int
    line_num: int = 0
    block_num: int = 0


class OcrEngine:
    """Thin wrapper around vendored tesseract.exe + models/tessdata."""

    def __init__(self, exe: Path | None = None, tessdata: Path | None = None) -> None:
        self.exe = exe or tesseract_exe()
        self.tessdata = tessdata or tessdata_dir()
        if self.exe is None or not self.exe.is_file():
            raise OcrUnavailableError(ocr_ready()[1])
        langs = language_files_present()
        missing = [k for k, ok in langs.items() if not ok and k != "osd"]
        if missing:
            raise OcrUnavailableError(f"Missing language data: {', '.join(missing)}")

    @property
    def available_languages(self) -> list[str]:
        return [k for k, ok in language_files_present().items() if ok]

    def run_tsv(
        self,
        image_path: Path,
        *,
        lang: str = "eng+jpn",
        psm: int = 3,
        oem: int = 1,
        extra_args: list[str] | None = None,
    ) -> list[RawOcrToken]:
        """OCR an image file; returns word-level tokens with confidence."""
        env = os.environ.copy()
        # Tesseract expects TESSDATA_PREFIX to be the folder that *contains* tessdata/
        # or the folder of *.traineddata — we ship files directly in models/tessdata.
        env["TESSDATA_PREFIX"] = str(self.tessdata.resolve())
        # Avoid accidental network/proxy lookups (fully offline)
        env.pop("http_proxy", None)
        env.pop("https_proxy", None)
        env.pop("HTTP_PROXY", None)
        env.pop("HTTPS_PROXY", None)
        env.pop("ALL_PROXY", None)

        with tempfile.TemporaryDirectory(prefix="monographpdf_ocr_") as tmp:
            out_base = Path(tmp) / "out"
            cmd = [
                str(self.exe),
                str(image_path),
                str(out_base),
                "-l",
                lang,
                "--psm",
                str(psm),
                "--oem",
                str(oem),
                "-c",
                "tessedit_create_tsv=1",
                "tsv",
            ]
            if extra_args:
                cmd[1:1] = []  # keep simple; append after
                cmd.extend(extra_args)
            try:
                proc = subprocess.run(
                    cmd,
                    capture_output=True,
                    text=True,
                    env=env,
                    timeout=180,
                    check=False,
                    cwd=str(self.tessdata.parent),
                    creationflags=_NO_WINDOW,
                )
            except FileNotFoundError as exc:
                raise OcrUnavailableError(str(exc)) from exc
            except subprocess.TimeoutExpired as exc:
                raise OcrUnavailableError("OCR timed out") from exc

            tsv_path = Path(str(out_base) + ".tsv")
            if not tsv_path.is_file():
                err = (proc.stderr or proc.stdout or "no TSV output").strip()
                raise OcrUnavailableError(f"Tesseract failed: {err[:400]}")
            return _parse_tsv(tsv_path.read_text(encoding="utf-8", errors="replace"))

    def detect_orientation(self, image_path: Path) -> dict[str, float | int | str]:
        """Use OSD when osd.traineddata is present; else return upright defaults."""
        if not (self.tessdata / "osd.traineddata").is_file():
            return {"rotate": 0, "orientation_confidence": 0.0, "script": "Unknown"}
        env = os.environ.copy()
        env["TESSDATA_PREFIX"] = str(self.tessdata.resolve())
        with tempfile.TemporaryDirectory(prefix="monographpdf_osd_") as tmp:
            out_base = Path(tmp) / "osd"
            cmd = [
                str(self.exe),
                str(image_path),
                str(out_base),
                "--psm",
                "0",
                "-l",
                "osd",
            ]
            try:
                proc = subprocess.run(
                    cmd,
                    capture_output=True,
                    text=True,
                    env=env,
                    timeout=60,
                    check=False,
                    creationflags=_NO_WINDOW,
                )
            except (OSError, subprocess.TimeoutExpired):
                return {"rotate": 0, "orientation_confidence": 0.0, "script": "Unknown"}
            # OSD writes to stdout typically
            text = (proc.stdout or "") + "\n" + (out_base.with_suffix(".osd").read_text(encoding="utf-8", errors="replace") if out_base.with_suffix(".osd").is_file() else "")
            rotate = 0
            conf = 0.0
            script = "Unknown"
            for line in text.splitlines():
                low = line.lower()
                if "rotate:" in low:
                    try:
                        rotate = int(line.split(":")[-1].strip())
                    except ValueError:
                        pass
                if "orientation confidence" in low:
                    try:
                        conf = float(line.split(":")[-1].strip())
                    except ValueError:
                        pass
                if "script:" in low and "confidence" not in low:
                    script = line.split(":")[-1].strip() or script
            return {"rotate": rotate, "orientation_confidence": conf, "script": script}


def _parse_tsv(text: str) -> list[RawOcrToken]:
    lines = text.splitlines()
    if not lines:
        return []
    header = lines[0].split("\t")
    idx = {name: i for i, name in enumerate(header)}
    required = ("level", "text", "conf", "left", "top", "width", "height")
    if not all(k in idx for k in required):
        return []
    tokens: list[RawOcrToken] = []
    for line in lines[1:]:
        parts = line.split("\t")
        if len(parts) <= max(idx.values()):
            continue
        try:
            level = int(parts[idx["level"]])
        except ValueError:
            continue
        if level != 5:  # word
            continue
        word = parts[idx["text"]].strip()
        if not word:
            continue
        try:
            conf = float(parts[idx["conf"]])
        except ValueError:
            conf = -1.0
        if conf < 0:
            continue
        tokens.append(
            RawOcrToken(
                text=word,
                conf=conf,
                left=int(float(parts[idx["left"]])),
                top=int(float(parts[idx["top"]])),
                width=int(float(parts[idx["width"]])),
                height=int(float(parts[idx["height"]])),
                line_num=int(float(parts[idx.get("line_num", idx["level"])])) if "line_num" in idx else 0,
                block_num=int(float(parts[idx["block_num"]])) if "block_num" in idx else 0,
            )
        )
    return tokens


_ENGINE: OcrEngine | None = None


def get_ocr_engine(*, force_reload: bool = False) -> OcrEngine:
    global _ENGINE
    if _ENGINE is None or force_reload:
        _ENGINE = OcrEngine()
    return _ENGINE
