"""User-facing wording for update checks and downloads (no Qt).

Each failure has a short reason code (the ``kind`` of a NetworkError, the ``code`` of a ManifestError
or UpdateError). The text says what happened and what the user can do, without technical detail an
attacker could use. Whatever the reason, nothing untrusted is downloaded or run, and retrying runs
the complete verification again.
"""

from __future__ import annotations

NOTHING_INSTALLED = "Nothing was downloaded or installed."

# reason -> (title, explanation)
CHECK_REASONS: dict[str, tuple[str, str]] = {
    # could not reach or use the release source
    "offline": ("No internet connection",
                "Monograph PDF could not connect to the internet. Check the connection and try again."),
    "timeout": ("GitHub is not responding",
                "The official releases page did not respond in time. Try again later."),
    "http": ("GitHub is temporarily unavailable",
             "The official releases page could not be reached. Try again later."),
    "rate_limited": ("GitHub is temporarily unavailable",
                     "GitHub is limiting requests from this network for a while. Try again in an hour."),
    "tls": ("Secure connection could not be verified",
            "The secure connection to GitHub could not be verified. A firewall, proxy or an incorrect "
            "date and time on this computer can cause this."),
    "redirect": ("Unexpected download location",
                 "The connection was redirected to an address that is not an official Monograph PDF "
                 "location, so it was stopped."),
    "not_found": ("No compatible release found",
                  "No update information was found on the official releases page."),
    "too_large": ("Update information could not be verified",
                  "The update information received was not valid."),
    "network": ("Connection interrupted",
                "The connection to GitHub was interrupted. Try again."),
    # update information received but not trusted
    "signature": ("Invalid digital signature",
                  "The update information is not signed by Monograph PDF's signing key."),
    "expired": ("Update information has expired",
                "The update information on the releases page has expired. A newer release will renew it."),
    "clock": ("Update information has an invalid date",
              "The update information is dated in the future. Check that this computer's date and time "
              "are correct."),
    "timestamp": ("Update information has an invalid date",
                  "The dates in the update information are not valid."),
    "identity": ("Update is for a different product",
                 "The update information does not belong to Monograph PDF from its official repository."),
    "channel": ("Update information could not be verified",
                "The update information does not match the selected release channel."),
    "rollback": ("Outdated update information",
                 "The update information is older than information this computer has already seen."),
    "artifact": ("Update information could not be verified",
                 "The update information does not describe a valid installer for this computer."),
    "invalid": ("Update information could not be verified",
                "The update information is incomplete or damaged."),
}

DOWNLOAD_REASONS: dict[str, tuple[str, str]] = {
    "verify": ("Installer integrity verification failed",
               "The downloaded installer does not match the signed update information, so it was "
               "deleted and not run."),
    "cancelled": ("Update canceled", "The update was canceled. Nothing was installed."),
    "disk_space": ("Not enough disk space", "There is not enough free disk space for the update."),
    "not_permitted": ("Unsupported upgrade path",
                      "This version cannot be installed automatically over the installed version."),
    "network": ("Download interrupted", "The download was interrupted before it completed."),
    "offline": ("Download interrupted", "The internet connection was lost during the download."),
    "timeout": ("Download interrupted", "GitHub stopped responding during the download."),
    "too_large": ("Installer integrity verification failed",
                  "The installer on the server does not have the expected size, so it was not used."),
}


def check_text(reason: str) -> tuple[str, str]:
    """Title and explanation for a failed check (always ends by saying nothing was installed)."""
    title, text = CHECK_REASONS.get(reason, CHECK_REASONS["invalid"] if reason else ("Unable to check for updates",
                                                                                  "The update check did not complete."))
    return title, f"{text} {NOTHING_INSTALLED}"


def download_text(code: str, detail: str = "") -> tuple[str, str]:
    """Title and explanation for a failed Update Now (``detail``: the specific reason, e.g. for a
    refused upgrade path or a missing installation)."""
    if code in DOWNLOAD_REASONS:
        title, text = DOWNLOAD_REASONS[code]
        if code == "not_permitted" and detail:
            text = detail
        return title, text
    if code in CHECK_REASONS:  # network kinds and other failures reached during the download
        title, text = CHECK_REASONS[code]
        return title, text
    return "Update not installed", detail or "The update could not be completed."
