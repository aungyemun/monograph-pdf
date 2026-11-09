# Privacy and secrets check before pushing or releasing

Monograph PDF · © 2026 Aung Ye Mun

A checklist for maintainers. It keeps credentials and personal information out of the public
repository and out of the release files (`Setup.exe`, `Installer.zip`, `Source.zip`, the update
manifest) and the screenshots. It complements the automatic checks in the release scripts. Those
checks reject secret-shaped strings and private folder paths in the packaged files, but they do not
know your personal details.

Everything described here runs locally and is read-only, except the hook installation step.

## What must never be published

| Kind | Examples |
| :--- | :--- |
| Credentials | GitHub tokens, API keys, passwords, `.git-credentials`, URLs with a user name and password |
| Signing material | the update-signing private key, its passphrase, code-signing certificates (`.pfx`, `.pem`, `.key`) |
| Personal details | a private e-mail address, your Windows user folder (`C:\Users\<name>`), your computer's name, home or work addresses |
| Private documents | real PDFs used for testing, and also their **file names, titles and document numbers** in test comments, logs or reports |
| Local evidence | build logs, JUnit files and test reports that contain local folder paths |
| AI attribution | co-author trailers or "Generated with" lines in commit messages, pull requests or release notes (project policy) |

Test files may contain deliberately fake secrets (for example to test that problem reports
redact keys). Assemble them at run time or keep them obviously fake, and mention them in the test.

## One-time setup in your clone

1. Install the pre-push guard. It lives only in your clone and is never pushed:

   ```text
   env\Scripts\python.exe scripts\git-hooks\install_hooks.py
   ```

2. Open `.git\info\private-patterns.txt` (created by the step above) and add one line for each
   piece of text that must never be pushed: your private e-mail address, your user folder,
   your computer's name, the folder that holds your signing key, and the numbers or titles of
   private documents you test with. Matching ignores case. Because this file is inside `.git`, it
   is never committed.

3. Use the GitHub no-reply address for commits in this repository:

   ```text
   git config user.email "<id>+<user>@users.noreply.github.com"
   ```

   On GitHub, **Settings ▸ Emails**: turn on *Keep my email addresses private* and
   *Block command line pushes that expose my email*. In the repository's security settings, check
   that secret scanning and push protection are on.

## Before every push

The guard runs automatically on `git push` and checks only the commits that are not on GitHub
yet. It blocks the push and names the commit when it finds:

* text from `private-patterns.txt` in added lines;
* a secret-shaped string (token, private-key block, URL with a password);
* AI attribution in a commit message;
* an author or committer e-mail that is not a GitHub no-reply address;
* a push of a local `backup/…` branch.

Fix the commit before pushing. Use `git push --no-verify` only after you have checked that a
finding is a false alarm.

## Before every release

1. **Scan the history and the release files**, after the release build and before anything is
   uploaded (PowerShell, from the project folder):

   ```text
   env\Scripts\python.exe scripts\audit\privacy_scan.py --git . --path installer --path dist --out "$env:TEMP\monograph_privacy_scan.json"
   ```

   Add `--path <folder>` for anything else you plan to share, such as a test package. The
   summary never prints a secret or a personal pattern. Secrets are masked, and personal matches
   are shown by their line number in `private-patterns.txt`. The JSON report is for you only, so
   keep it out of the repository.

2. **Review every finding.** For each flagged Git object, the scan says whether a remote branch or
   a tag already contains it, which means it is probably public.

   | Finding | Not pushed yet | Already public |
   | :--- | :--- | :--- |
   | Real secret | Remove it, rewrite the unpushed commits, revoke and replace the secret anyway | **Revoke and replace the secret immediately**; removing it from history comes second |
   | Personal text | Remove it and rewrite the unpushed commits (keep a backup bundle first) | Decide deliberately; rewriting published history needs a force-push and breaks existing clones and tags |
   | In a built file | Fix the source, rebuild, re-test; mark the old build as superseded | Publish a corrected release |

3. **Check the release text**: release notes, `CHANGELOG.md`, `CITATION.cff` and the pull request
   description. They must contain no local paths, no machine names and no AI attribution.

4. **Screenshots** must show synthetic documents only (`scripts/make_showcase_screenshots.py`
   creates fictional sample files). They must not show recent-file lists, folder paths or the
   user name. Look at each image before committing it.

5. **Test packages** given to other people: remove generated metadata files that record temporary
   folders (they contain the Windows user name), or replace those paths with `%TEMP%`.

## If something was published by mistake

1. A credential or signing key: revoke or rotate it first (GitHub token settings; for the
   update-signing key, follow *Compromised key* in
   [Secure updates ▸ Key rotation](SECURE_UPDATES.md#key-rotation)). Then remove it from the
   repository.
2. Personal information: remove it in a new commit and replace affected release assets if
   needed. Rewriting the public history is a separate decision with consequences for every clone,
   fork and tag. Contact GitHub Support to purge cached views if necessary.
3. Record what happened and what was done in a private note; do not repeat the leaked value in it.

Related: [Release checklist](RELEASE_CHECKLIST.md) ·
[Release provenance](RELEASE_PROVENANCE.md) · [Privacy policy](PRIVACY_POLICY.md) ·
[Security policy](../SECURITY.md)
