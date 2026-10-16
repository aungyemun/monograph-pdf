"""Write machine-readable AcroForm/XFA/font diagnostics under tests/outputs/."""

from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))


def main(argv: list[str] | None = None) -> int:
    import fitz

    from app.paths import TEST_GENERATED, TEST_LOGS, TEST_SCREENSHOTS
    from core.forms.capabilities import inspect_pdf_capabilities, write_capabilities_report
    from core.forms.display import looks_like_internal_field_id, sanitize_field_value, visible_field_content
    from core.forms.fields import FormField, FieldType
    from core.editing.font_inventory import build_font_inventory, strip_subset_prefix
    from core.editing.geometry import Rect

    args = list(argv or sys.argv[1:])
    samples = ROOT / "tests" / "samples"
    default_names = (
        "sample_invitation_form.pdf",
        "sample_jp_admin_form.pdf",
        "sample_hybrid_xfa_itinerary.pdf",
    )
    paths = [Path(p) for p in args] if args else [samples / n for n in default_names]
    if not any(p.is_file() for p in paths):
        from tests.fixtures.make_form_samples import main as make_forms

        make_forms()
        paths = [samples / n for n in default_names]

    TEST_LOGS.mkdir(parents=True, exist_ok=True)
    TEST_GENERATED.mkdir(parents=True, exist_ok=True)
    TEST_SCREENSHOTS.mkdir(parents=True, exist_ok=True)

    summary: list[dict] = []
    for pdf_path in paths:
        if not pdf_path.is_file():
            continue
        doc = fitz.open(pdf_path)
        try:
            caps = inspect_pdf_capabilities(doc, path=pdf_path)
            report_path = TEST_LOGS / f"form_caps_{pdf_path.stem}.json"
            write_capabilities_report(caps, report_path)

            inv = build_font_inventory(doc)
            inv_path = TEST_GENERATED / f"font_inventory_{pdf_path.stem}.json"
            inv_path.write_text(json.dumps(inv.to_dict(), indent=2, ensure_ascii=False) + "\n", encoding="utf-8")

            # Render page 0 for visual regression artifacts
            page = doc.load_page(0)
            pix = page.get_pixmap(matrix=fitz.Matrix(1.5, 1.5), alpha=False)
            shot = TEST_SCREENSHOTS / f"{pdf_path.stem}_page0.png"
            pix.save(shot.as_posix())

            # Prove internal names are not treated as visible content
            leak_examples: list[str] = []
            for w in page.widgets() or []:
                name = str(getattr(w, "field_name", "") or "")
                value = str(getattr(w, "field_value", "") or "")
                cleaned = sanitize_field_value(name, value)
                fake = FormField(
                    page_index=0,
                    rect=Rect(0, 0, 10, 10),
                    field_type=FieldType.TEXT,
                    name=name,
                    value=cleaned,
                    is_acroform=True,
                )
                vis = visible_field_content(fake)
                if looks_like_internal_field_id(name) and (name in vis or "topmostSubform" in vis):
                    leak_examples.append(name)

            summary.append(
                {
                    "file": pdf_path.name,
                    "caps_report": str(report_path.relative_to(ROOT)),
                    "screenshot": str(shot.relative_to(ROOT)),
                    "acroform": caps.acroform,
                    "xfa": caps.xfa.value,
                    "widgets": caps.widget_count,
                    "som_like_names": caps.som_like_name_count,
                    "embedded_fonts": caps.embedded_font_count,
                    "name_leak_failures": leak_examples,
                    "subset_examples": [strip_subset_prefix(f) for f in caps.embedded_fonts[:5]],
                }
            )
        finally:
            doc.close()

    out = TEST_LOGS / "form_diagnostics_summary.json"
    out.write_text(json.dumps(summary, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    print(json.dumps(summary, indent=2, ensure_ascii=False))
    print(f"Wrote {out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
