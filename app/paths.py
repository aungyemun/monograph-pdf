"""Project-root path resolution. All artifacts stay under known folders."""

from __future__ import annotations

import sys
from pathlib import Path

from core import app_env
from core.platform_paths import is_macos_app_bundle, user_local_base

# Re-export for tests that monkeypatch the app.paths binding.
__all__ = ["is_macos_app_bundle", "user_local_base"]


def _resolve_root() -> Path:
    if getattr(sys, "frozen", False):
        # Directory containing the frozen executable (Windows beside MonographPDF.exe;
        # macOS .app: Contents/MacOS).
        return Path(sys.executable).resolve().parent
    return Path(__file__).resolve().parents[1]


def _resolve_bundle_root() -> Path:
    """Resources bundled inside the frozen app (read-only extract)."""
    if getattr(sys, "frozen", False) and hasattr(sys, "_MEIPASS"):
        return Path(sys._MEIPASS)  # type: ignore[attr-defined]
    if is_macos_app_bundle():
        resources = Path(sys.executable).resolve().parent.parent / "Resources"
        if resources.is_dir():
            return resources
    return _resolve_root()


# Install / project root (exe / MacOS directory when frozen)
ROOT = _resolve_root()
# Bundled resources root (may equal ROOT in dev)
BUNDLE_ROOT = _resolve_bundle_root()


APP_DIR = ROOT / "app"
CORE_DIR = ROOT / "core"
# Engines may live beside the binary or inside the bundle (macOS .app Resources)
if (ROOT / "engines").is_dir():
    ENGINES_DIR = ROOT / "engines"
elif (BUNDLE_ROOT / "engines").is_dir():
    ENGINES_DIR = BUNDLE_ROOT / "engines"
else:
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

    An installed Windows copy (Setup leaves unins000.exe beside the app) and a macOS
    .app bundle always keep working files in the user's profile.
    """
    frozen = getattr(sys, "frozen", False)
    if frozen and (any(ROOT.glob("unins*.exe")) or is_macos_app_bundle()):
        return False
    if app_env.get("RUNTIME_DIR"):
        # Working files go elsewhere (self-check): no probe of this folder
        return not frozen
    return _writable(ROOT / "runtime")


_PROJECT_LAYOUT = _project_layout()


def _resolve_runtime_dir() -> Path:
    """``./runtime`` in the project / portable layout; user Application Support / AppData
    when installed; ``MONOGRAPH_PDF_RUNTIME_DIR`` (or ``--runtime-dir``) overrides both."""
    override = app_env.get("RUNTIME_DIR")
    if override:
        return Path(override)
    if _PROJECT_LAYOUT:
        return ROOT / "runtime"
    return user_local_base() / "runtime"


RUNTIME_DIR = _resolve_runtime_dir()
# True when the app runs from an installed location (Program Files, per-user Programs, or .app)
INSTALLED_READ_ONLY = not _PROJECT_LAYOUT
# Writable caches — never project root; clean abandoned artifacts from these trees
CACHE_DIR = RUNTIME_DIR / "cache"
TEMP_DIR = RUNTIME_DIR / "temp"
ORGANIZE_CACHE_DIR = CACHE_DIR / "organize"
ORGANIZE_TEMP_DIR = TEMP_DIR / "organize"

PACKAGES_DIR = ROOT / "packages"
MODELS_DIR = ROOT / "models" if (ROOT / "models").is_dir() else BUNDLE_ROOT / "models"
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
# Installed copies already keep these under RUNTIME_DIR / "logs" (no second "logs" folder)
TEST_LOGS = TEST_OUTPUTS / "logs" if not INSTALLED_READ_ONLY else TEST_OUTPUTS
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
        # Source checkout only: the built app never creates folders beside the binary
        folders += [ENGINES_DIR / "ocr", ENGINES_DIR / "qpdf", ENGINES_DIR / "mupdf", MODELS_DIR, PACKAGES_DIR / "wheels"]
    for path in folders:
        try:
            path.mkdir(parents=True, exist_ok=True)
        except OSError:
            pass  # read-only install folder — runtime data lives under the user profile
