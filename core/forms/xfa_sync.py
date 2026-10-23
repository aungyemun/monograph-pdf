"""Keep the XFA layer of a hybrid AcroForm/XFA form in step with the values saved in its AcroForm fields.

A hybrid form (typical for forms made with Adobe LiveCycle Designer, e.g. many Japanese government
forms) holds every field twice: as ordinary PDF (AcroForm) widgets and as an XFA template whose values
live in the XFA ``datasets`` packet. Monograph PDF, PDFium (Edge, Chrome) and most viewers show the
AcroForm values; Adobe Acrobat and Reader show the XFA values. If only the AcroForm values change, the
saved file looks filled everywhere except in Acrobat, where every field is empty.

On save, :func:`sync_xfa` therefore

1. writes each changed value into the matching node of the XFA ``datasets`` packet, following the
   template's own structure (subforms with ``<bind match="none">`` hold no data node), and removes the
   ``form`` packet — a cached state of the filled form that Acrobat would otherwise prefer to the data;
2. when that is not safely possible — a field that is not in the template, explicit data bindings,
   check boxes whose on/off values cannot be determined, new fields added in Monograph PDF, a form that
   is flattened — removes the XFA layer instead, so that Acrobat shows the AcroForm fields (the same
   values every other viewer shows). That loses XFA-only scripts and validation, so it is reported to
   the user (:func:`take_notes`).

Only the XFA packets are touched; nothing is sent anywhere.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Iterable
from xml.dom import minidom

import fitz

from core.forms.fields import FieldType, FormField

_NOTES: list[str] = []

# XFA template container elements that take part in SOM names
_CONTAINERS = {"subform", "field", "exclGroup", "subformSet", "area"}


def take_notes() -> list[str]:
    """Messages for the user from the last save(s); clears them."""
    out = list(_NOTES)
    _NOTES.clear()
    return out


@dataclass
class SyncResult:
    action: str = "none"  # none | synced | removed
    synced: int = 0
    reason: str = ""
    unmapped: list[str] = field(default_factory=list)


# --------------------------------------------------------------------------------------------- PDF


def _acroform_xref(doc: fitz.Document) -> tuple[int, str] | None:
    """(object, key prefix) addressing the AcroForm dictionary — its own object or inline in the catalog."""
    try:
        cat = doc.pdf_catalog()
        kind, val = doc.xref_get_key(cat, "AcroForm")
    except Exception:  # noqa: BLE001
        return None
    if kind == "xref":
        return int(val.split()[0]), ""
    if kind == "dict":
        return cat, "AcroForm/"
    return None


def _xfa_packets(doc: fitz.Document, acro: tuple[int, str]) -> list[tuple[str, int]] | None:
    """[(packet name, stream xref)] of an /XFA array; None when there is no XFA; [] for one XDP stream."""
    kind, val = doc.xref_get_key(acro[0], acro[1] + "XFA")
    if kind == "null":
        return None
    if kind != "array":
        return []  # one stream holding the whole XDP — handled as "cannot sync" (rare)
    return [(m.group(1), int(m.group(2))) for m in re.finditer(r"\((.*?)\)\s*(\d+)\s+0\s+R", val)]


def has_xfa(doc: fitz.Document) -> bool:
    acro = _acroform_xref(doc)
    return bool(acro) and _xfa_packets(doc, acro) is not None


def remove_xfa(doc: fitz.Document) -> bool:
    """Remove the XFA layer: Acrobat then shows the AcroForm fields. True when something was removed."""
    acro = _acroform_xref(doc)
    if not acro or _xfa_packets(doc, acro) is None:
        return False
    doc.xref_set_key(acro[0], acro[1] + "XFA", "null")
    try:
        if doc.xref_get_key(doc.pdf_catalog(), "NeedsRendering")[0] != "null":
            doc.xref_set_key(doc.pdf_catalog(), "NeedsRendering", "null")
    except Exception:  # noqa: BLE001
        pass
    return True


# --------------------------------------------------------------------------------------- templates


def _som_segments(name: str) -> list[tuple[str, int]]:
    """'topmostSubform[0].Page1[0].fill_5[0]' -> [('topmostSubform', 0), ('Page1', 0), ('fill_5', 0)]."""
    out = []
    for part in name.split("."):
        m = re.fullmatch(r"(.*?)(?:\[(\d+)\])?", part)
        out.append((m.group(1), int(m.group(2) or 0)))
    return out


def _local(node) -> str:
    return (node.localName or node.nodeName or "").split(":")[-1]


def _named_children(node, name: str) -> list:
    """Containers called *name* below *node*; unnamed containers are transparent in SOM."""
    found = []
    for child in node.childNodes:
        if child.nodeType != child.ELEMENT_NODE or _local(child) not in _CONTAINERS:
            continue
        cname = child.getAttribute("name")
        if cname == name:
            found.append(child)
        elif not cname:
            found.extend(_named_children(child, name))
    return found


def _bind(node) -> tuple[str, str]:
    for child in node.childNodes:
        if child.nodeType == child.ELEMENT_NODE and _local(child) == "bind":
            return child.getAttribute("match") or "once", child.getAttribute("ref")
    return "once", ""


def _template_root(template_xml: str):
    dom = minidom.parseString(template_xml.encode("utf-8"))
    return dom.documentElement


def _data_path(template_root, som: str) -> tuple[list[tuple[str, int]], object] | None:
    """Data-node path of field *som* (names + indices), or None when it cannot be mapped safely."""
    node = template_root
    path: list[tuple[str, int]] = []
    segs = _som_segments(som)
    for i, (name, index) in enumerate(segs):
        matches = _named_children(node, name)
        if index >= len(matches):
            return None
        node = matches[index]
        match, ref = _bind(node)
        if match == "dataRef" or match == "global" or ref:
            return None  # explicit binding: the data node is not where the name says
        if match == "none":
            if i == len(segs) - 1:
                return None  # the field itself keeps no data
            continue
        path.append((name, index))
    return path, node


def _checkbox_values(field_node) -> tuple[str, str] | None:
    for child in field_node.childNodes:
        if child.nodeType == child.ELEMENT_NODE and _local(child) == "items":
            vals = [
                "".join(t.data for t in item.childNodes if t.nodeType == t.TEXT_NODE)
                for item in child.childNodes
                if item.nodeType == item.ELEMENT_NODE
            ]
            if vals:
                return vals[0], (vals[1] if len(vals) > 1 else "")
    return None


# -------------------------------------------------------------------------------------------- data


def _data_root(dom):
    for el in dom.getElementsByTagNameNS("*", "data"):
        if (el.namespaceURI or "").startswith("http://www.xfa.org/schema/xfa-data/"):
            return el
    return None


def _element_children(node, name: str) -> list:
    return [c for c in node.childNodes if c.nodeType == c.ELEMENT_NODE and _local(c) == name]


def _ensure_node(dom, root, path: list[tuple[str, int]]):
    node = root
    for name, index in path:
        kids = _element_children(node, name)
        while len(kids) <= index:
            new = dom.createElement(name)
            node.appendChild(new)
            kids.append(new)
        node = kids[index]
    return node


def _set_text(dom, node, value: str) -> None:
    for child in list(node.childNodes):
        node.removeChild(child)
    if value:
        node.appendChild(dom.createTextNode(value))


# --------------------------------------------------------------------------------------------- API


def sync_xfa(
    doc: fitz.Document,
    fields: Iterable[FormField],
    *,
    new_fields: bool = False,
    flattened: bool = False,
) -> SyncResult:
    """Bring the XFA layer in line with the saved AcroForm values (see module docstring)."""
    result = SyncResult()
    acro = _acroform_xref(doc)
    if not acro:
        return result
    packets = _xfa_packets(doc, acro)
    if packets is None:
        return result
    changed = [f for f in fields if f.is_acroform and not f.is_candidate and f.value_dirty]

    def fallback(reason: str) -> SyncResult:
        if remove_xfa(doc):
            result.action, result.reason = "removed", reason
            _NOTES.append(
                "This form also contained an Adobe XFA version of its fields. "
                f"{reason} So that Adobe Acrobat shows the same values as other PDF programs, "
                "the XFA version was removed from the saved file (scripts and checks that only "
                "existed in it no longer run). The original file is unchanged."
            )
        return result

    if flattened:
        return fallback("The form was flattened, and its XFA fields would have covered the flattened text.")
    if new_fields:
        return fallback("New form fields were added, which the XFA version does not know.")
    if not changed:
        return result

    names = dict(packets)
    if "template" not in names or "datasets" not in names:
        return fallback("Its XFA data could not be updated.")
    try:
        template = _template_root(doc.xref_stream(names["template"]).decode("utf-8"))
        ds_xml = doc.xref_stream(names["datasets"]).decode("utf-8")
        ds_dom = minidom.parseString(ds_xml.encode("utf-8"))
        data = _data_root(ds_dom)
    except Exception:  # noqa: BLE001
        return fallback("Its XFA data could not be read.")
    if data is None:
        return fallback("Its XFA data could not be read.")

    # Two fields whose data would land in the same place (e.g. "Name" on two pages under subforms
    # that keep no data) cannot be told apart in the XFA data: then the XFA copy is not updated.
    owners: dict[tuple, set[str]] = {}
    fields = [f for f in fields if f.is_acroform and not f.is_candidate and f.name]
    for f in fields:
        m = _data_path(template, f.name)
        if m is not None and m[0]:
            owners.setdefault(tuple(m[0]), set()).add(f.name)

    for f in changed:
        mapped = _data_path(template, f.name) if f.name else None
        if mapped is not None and len(owners.get(tuple(mapped[0]), ())) > 1:
            result.unmapped.append(f.name)
            continue
        if mapped is None or not mapped[0]:
            result.unmapped.append(f.name)
            continue
        path, field_node = mapped
        if f.field_type in (FieldType.CHECKBOX, FieldType.RADIO):
            values = _checkbox_values(field_node)
            if values is None or f.field_type == FieldType.RADIO:
                result.unmapped.append(f.name)
                continue
            value = values[0] if f.checked else values[1]
        elif f.field_type == FieldType.SIGNATURE:
            continue
        else:
            value = f.value or ""
        _set_text(ds_dom, _ensure_node(ds_dom, data, path), value)
        result.synced += 1

    if result.unmapped:
        return fallback("Some of the fields you filled could not be matched with it.")

    try:
        xml = ds_dom.documentElement.toxml()
        # The 'form' packet caches the merged form state (with a checksum); without it Acrobat merges
        # the template with the (now updated) data again. Removed first: if anything fails later,
        # the XFA copy is removed instead of keeping stale cached values.
        kept = [(n, x) for n, x in packets if n != "form"]
        if len(kept) != len(packets):
            arr = "[" + "".join(f"{fitz.get_pdf_str(n)}{x} 0 R" for n, x in kept) + "]"
            doc.xref_set_key(acro[0], acro[1] + "XFA", arr)
        doc.update_stream(names["datasets"], xml.encode("utf-8"))
    except Exception:  # noqa: BLE001
        return fallback("Its XFA data could not be updated.")
    result.action = "synced"
    return result
