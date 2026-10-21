"""Local test server: ``python -m services.report_gateway`` (plain HTTP on 127.0.0.1 only).

Production deployments run :func:`gateway.from_environment` under a WSGI server behind HTTPS.
"""

from __future__ import annotations

import logging
import os
from wsgiref.simple_server import make_server

from services.report_gateway.gateway import from_environment

if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
    port = int(os.environ.get("PORT", "8765"))
    with make_server("127.0.0.1", port, from_environment()) as httpd:
        print(f"report gateway (test) on http://127.0.0.1:{port}/v1/reports")
        httpd.serve_forever()
