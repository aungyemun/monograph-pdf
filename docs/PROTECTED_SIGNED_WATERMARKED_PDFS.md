# Protected, signed and watermarked PDFs

How Monograph PDF (from 0.5.0) treats password-protected, digitally signed and watermarked PDFs when
they are saved, copied, converted, printed or combined. The rules are implemented in one place,
`core/security/protection.py`, and covered by `tests/integration/test_protection_outputs.py` and
`tests/ui/test_protected_ui.py`.

## Password protection

A PDF can have two passwords:

- the **open password** (user password), needed to open it, and
- the **permissions password** (owner password), which protects the *permissions* — what someone who
  opened the PDF may do with it (print, copy its content, change it, assemble pages, comment, fill in
  forms).

A PDF may have only a permissions password: it opens without a password but keeps its restrictions.

### Protection is kept

Every PDF written from a protected PDF keeps the same open password, permissions password,
permissions and encryption (AES-256, AES-128 or RC4 as in the original):

| Output | Protection |
| :--- | :--- |
| Save, Save As | kept |
| Save a Copy: Whole Document, Selected Pages, Flattened PDF, Copy with Metadata | kept |
| Remove Document Information (metadata) | kept |
| Watermark, Header & Footer, Background, Remove page design | kept |
| Redact (apply) | kept |
| Extract Pages | kept |
| Compress PDF | kept |
| Make Searchable (OCR) | kept |
| Protect with Password | replaced by the new settings (needs the permissions password of a protected PDF) |
| Unlock PDF (Remove Password) | removed (needs the permissions password when the PDF restricts anything) |
| Merge PDFs, Split PDF | not protected — the inputs may have different passwords; protect the result with Protect with Password |

Before 0.5.0 several of these commands wrote an **unprotected** copy (and some lost bookmarks and
attachments). That was a security defect and is corrected.

### Permissions are honoured

With the open password alone, Monograph PDF does only what the PDF allows. Otherwise it asks for the
permissions password; once entered it applies until the document is closed (it is checked against the
file on this computer and is not stored).

| Action | Needs |
| :--- | :--- |
| PDF to Word, PowerPoint, Excel, text or pictures; Extract Images; Copy Page as Picture; OCR text export and Scanned PDF to Word | copying content |
| Print | printing |
| Saving changes; Watermark, Header & Footer, Background; Remove Document Information; Flattened PDF; Compress | changes |
| Extract Pages, Selected Pages as PDF, Split PDF, combining with Merge PDFs | page assembly (or changes) |
| Protect with Password on a protected PDF | the permissions password |
| Unlock PDF when the PDF restricts anything | the permissions password |

Batch Convert skips a file whose permissions do not allow the conversion and says why. When a
restricted PDF is opened, the status bar names the actions that need the permissions password;
**Protect ▸ View Permissions** lists the permissions and these rules.

## Digital signatures

Certificate-based digital signatures protect the exact bytes of a file. Monograph PDF does not create
them (its signatures are visual), but it keeps existing ones valid where possible:

- **Save As without changes** copies the file byte for byte: the signatures stay valid. **Save**
  without changes does nothing.
- **Saving changes** rewrites the file and the existing signatures become invalid. **Save** over a
  signed PDF asks first; keep the signed original and save the changes under a new name.
- **Word, PowerPoint and picture exports** show how a signature looks. No exported file is digitally
  signed; the PDF to Word and PDF to PowerPoint dialogs say so.
- Empty signature fields (waiting to be signed) are not signatures and do not trigger these messages.

## Watermarks, headers, footers and backgrounds

These are part of the pages and stay in every output.

- Marks added with **Insert ▸ Watermark / Header & Footer / Background** are recognisable and, while
  not locked, can be removed (**Insert ▸ Remove Header, Footer, Watermark or Background…**) or left out
  of a Word or PowerPoint export (a check box in those dialogs).
- A watermark **locked** with Protect with Password becomes ordinary page content: it is not a
  removable layer, it stays in every output, and with a permissions password that forbids changes it
  cannot be changed in Monograph PDF.
- Watermarks made by other programs (watermark annotations or content marked as a watermark) are
  kept; the export dialogs mention them.

## Related

[Security and privacy](SECURITY_AND_PRIVACY.md) · [Save As and export](SAVE_AS_AND_EXPORT.md) ·
[PDF to Office conversion](PDF_TO_OFFICE_CONVERSION.md) · [User Guide](USER_GUIDE.md#password-protected-pdfs)
