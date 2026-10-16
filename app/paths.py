"""Project-root path resolution. All artifacts stay under known folders."""

from __future__ import annotations

import os
import sys
from pathlib import Path

from core import app_env
from core.product_meta import DATA_FOLDER_NAME


def _resolve_root() -> Path:
    if getattr(sys, "frozen", False):
        # Writable/install root = directory containing MonographPDF.exe
        return Path(sys.executable).resolve().parent
    return Path(__file__).resolve().parents[1]


def _resolve_bundle_root() -> Path:
    """Resources bundled inside the frozen app (read-only extract)."""
    if getattr(sys, "frozen", False) and hasattr(sys, "_MEIPASS"):
        return Path(sys._MEIPASS)  # type: ignore[attr-defined]
    return _resolve_root()


# Install / project root (exe directory when frozen)
ROOT = _resolve_root()
# Bundled resources root (may equal ROOT in dev)
BUNDLE_ROOT = _resolve_bundle_root()


APP_DIR = ROOT / "app"
CORE_DIR = ROOT / "core"
ENGINES_DIR = ROOT / "engines"
UI_DIR = ROOT / "ui"
RESOURCES_DIR = BUNDLE_ROOT / "resources"
def _writable(folder: Path) -> bool:
    try:
        folder.mkdir(parents=True, exist_ok=True)
        probe = folder / ".write-test"
        probe.write_bytes(b"")
        probe.unlink()
        return True
    except OSError:
        return False


def _project_layout() -> bool:
    """True when running from the project / a portable folder (not an installed copy).

    An installed copy (Setup.exe leaves unins000.exe beside the app) always keeps its working
    files in the user's profile, so uninstall/upgrade never touches them; so does a copy in a
    folder it cannot write to.
    """
    frozen = getattr(sys, "frozen", False)
    if frozen and any(ROOT.glob("unins*.exe")):
        return False
    if app_env.get("RUNTIME_DIR"):
        # Working files go elsewhere (Setup's and the build's self-check): no probe of this folder
        return not frozen
    return _writable(ROOT / "runtime")


_PROJECT_LAYOUT = _project_layout()


def _resolve_runtime_dir() -> Path:
    r"""./runtime in the project / portable layout, %LOCALAPPDATA%\Monograph PDF\runtime when
    installed; MONOGRAPH_PDF_RUNTIME_DIR (or --runtime-dir) overrides both."""
    override = app_env.get("RUNTIME_DIR")
    if override:
        return Path(override)
    if _PROJECT_LAYOUT:
        return ROOT / "runtime"
    base = os.environ.get("LOCALAPPDATA") or str(Path.home() / ".local" / "share")
    return Path(base) / DATA_FOLDER_NAME / "runtime"


RUNTIME_DIR = _resolve_runtime_dir()
# True when the app runs from an installed location (Program Files or per-user Programs)
INSTALLED_READ_ONLY = not _PROJECT_LAYOUT
# Writable caches — never project root; clean abandoned artifacts from these trees
CACHE_DIR = RUNTIME_DIR / "cache"
TEMP_DIR = RUNTIME_DIR / "temp"
ORGANIZE_CACHE_DIR = CACHE_DIR / "organize"
ORGANIZE_TEMP_DIR = TEMP_DIR / "organize"

PACKAGES_DIR = ROOT / "packages"
MODELS_DIR = ROOT / "models"
THIRD_PARTY_DIR = ROOT / "third_party"
TOOLS_DIR = ROOT / "tools"
SCRIPTS_DIR = ROOT / "scripts"
TESTS_DIR = ROOT / "tests"
REPORTS_DIR = ROOT / "reports"
DOCS_DIR = ROOT / "docs"
LICENSES_DIR = ROOT / "licenses"
BUILD_DIR = ROOT / "build"
DIST_DIR = ROOT / "dist"
VERSION_FILE = BUNDLE_ROOT / "VERSION"
if not VERSION_FILE.is_file():
    VERSION_FILE = ROOT / "VERSION"


TEST_OUTPUTS = TESTS_DIR / "outputs" if not INSTALLED_READ_ONLY else RUNTIME_DIR / "logs"
TEST_LOGS = TEST_OUTPUTS / "logs"
TEST_SCREENSHOTS = TEST_OUTPUTS / "screenshots"
TEST_JUNIT = TEST_OUTPUTS / "junit"
TEST_COVERAGE = TEST_OUTPUTS / "coverage"
TEST_TEMP = TEST_OUTPUTS / "temp"
TEST_GENERATED = TEST_OUTPUTS / "generated"


def ensure_runtime_layout() -> None:
    """Create expected empty runtime folders if missing (idempotent).

    Developer folders beside the code (engines, models, packages) are only created in the
    project layout — an installed copy never writes into its install folder.
    """
    folders = [
        RUNTIME_DIR / "bin",
        RUNTIME_DIR / "lib",
        RUNTIME_DIR / "sessions",
        CACHE_DIR,
        TEMP_DIR,
        ORGANIZE_CACHE_DIR,
        ORGANIZE_TEMP_DIR,
    ]
    if not INSTALLED_READ_ONLY and not getattr(sys, "frozen", False):
        # Source checkout only: the built app never creates folders beside MonographPDF.exe
        folders += [ENGINES_DIR / "ocr", ENGINES_DIR / "qpdf", ENGINES_DIR / "mupdf", MODELS_DIR, PACKAGES_DIR / "wheels"]
    for path in folders:
        try:
            path.mkdir(parents=True, exist_ok=True)
        except OSError:
            pass  # read-only install folder — runtime data lives under %LOCALAPPDATA%
