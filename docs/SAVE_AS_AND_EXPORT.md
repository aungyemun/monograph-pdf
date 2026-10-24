# Save, Save As, Save a Copy and export

| Command | Writes | Then works on | Unsaved state |
|---|---|---|---|
| **File ▸ Save** (Ctrl+S) | the open file | the saved file (reloaded; overlays are now part of the pages) | clean |
| **File ▸ Save As…** (Ctrl+Shift+S) | a file you choose | the new file | clean |
| **File ▸ Save a Copy ▸ Whole Document (Keep Working on This One)…** | a file you choose | the same open document | unchanged; undo history kept |
| **Save a Copy ▸ Selected Pages as PDF… / Flattened PDF… / Copy with Metadata…** | a file you choose | the same open document | unchanged |
| Convert ▸ …, File ▸ Compress PDF… | a file you choose | the same open document | asks Save / Save As… / Cancel first when there are unsaved changes |

## Save As cases

| Case | Behaviour |
|---|---|
| A. Replace the current PDF | Allowed. Same as Save: the open file is released before replacing (Windows cannot replace an open file); retries for a few seconds if another program holds it, then reports it and keeps your edits. |
| B. Different name, same folder | New file; the original is not changed or deleted. |
| C. Same name, different folder | New file in that folder; if one exists there, the Windows dialog asks before replacing it. |
| D. Different name and folder | As B and C. |
| E. Unchanged PDF as a separate copy | Save As or Save a Copy ▸ Whole Document copies the file byte for byte (from 0.5.0), so digital signatures stay valid and the protection is unchanged. Save without changes does nothing. |
| F. Modified PDF as a separate copy | Save a Copy ▸ Whole Document: the copy contains every unsaved change; the open document keeps them unsaved, with its undo history. |

Choosing the open file in **Save a Copy** is refused; use Save to replace it.

## Protected, signed and watermarked PDFs

Every PDF written from a password-protected PDF keeps its open password, permissions password and
permissions; saving changes to a PDF whose permissions forbid changes needs its permissions password;
Save over a digitally signed PDF with changes asks first, because the signatures become invalid.
Details: [Protected, signed and watermarked PDFs](PROTECTED_SIGNED_WATERMARKED_PDFS.md).

## Writing files safely

- **Replacing an existing file.** The new content goes to a temporary file in the same folder, which is then swapped in. If writing fails (disk full, permission denied, file locked), the existing file is unchanged and the temporary file is removed.
- **Writing a new file.** The file is removed again if writing fails, so no partial or corrupted file is left.
- **Password protection.** Save and Save As keep the protection.
- **Original files.** They are never deleted after Save As.
