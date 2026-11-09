# Privacy in plain words

**Your documents stay on your computer.** Monograph PDF opens, edits and saves files only on your
own computer. It never uploads documents.

## What Monograph PDF does not do

* No account or sign-in.
* No advertising.
* No usage statistics or tracking ("telemetry").
* No uploading of documents, file names or anything you type.

## The only times it connects to the internet

Monograph PDF connects to the internet only when you ask it to:

| When | What happens | What is sent |
| :--- | :--- | :--- |
| You choose **Help ▸ Check for Updates…**, or you switched on automatic checks (they are off at first) | Monograph PDF asks GitHub, where its releases are published, whether a newer version exists. **Update Now** downloads it. Only updates signed by the project are accepted. | The program's name and version. As with any connection, GitHub sees your IP address. |
| You click **Download and Install** for an extra text-recognition language | The language file is downloaded from the official Tesseract release on GitHub and checked before use. | The name of the requested file. GitHub sees your IP address. |

Nothing else is sent: no documents, no file names, no settings and nothing that identifies you or
your computer. Without an internet connection, everything except these two actions works as usual.

If something goes wrong, Monograph PDF may show a **problem report** with technical details only
(no documents, file names, folder paths or user names). Sending it is your choice. At present the
reporting service is not running, so sending is switched off.

## What is kept on your computer

Your settings and the list of recently opened files are stored in your user profile on your computer.
On Windows, uninstalling removes the program, the recent-files list and working files, and asks
whether to remove your settings too. Your documents are never removed.

## Removing private information from your files

PDF files can contain more than you see: the author's name, earlier versions, comments,
attachments or hidden text. **Protect ▸ Remove Hidden Information** finds these and saves a copy
without the ones you choose. (Text inside pictures is part of the page and is not removed this
way.) **Redaction** deletes marked text and areas from the file. A black box drawn over text does
not remove it, but redaction does.

## Other programs

Turning Word, Excel or PowerPoint files into PDFs uses the Microsoft Office or LibreOffice installed
on your computer. Those programs follow their own privacy settings.

## Open source

Anyone can read Monograph PDF's source code to check these statements:
<https://github.com/aungyemun/monograph-pdf>.

Full text: [privacy policy](../PRIVACY_POLICY.md) · [security and privacy details](../SECURITY_AND_PRIVACY.md)
· Report a security problem privately: [security policy](../../SECURITY.md)
