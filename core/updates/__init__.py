"""Secure software updates (signed release manifests, verified downloads, in-place upgrade handoff).

Only :mod:`core.updates.net` opens network connections, and only for a user-initiated check, an
automatic check the user switched on, or a download the user approved with Update Now.
"""
