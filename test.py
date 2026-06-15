#!/usr/bin/env python3
"""Sonde manuelle optionnelle, desactivee par defaut pour proteger Similarweb."""

import os
import time

import similar


def main() -> None:
    if os.environ.get("SIMILARWEB_ALLOW_LIVE_TEST") != "1":
        print("Sonde live desactivee. Exportez SIMILARWEB_ALLOW_LIVE_TEST=1 pour l'executer volontairement.")
        return

    while True:
        print(similar.similarGet("http://google.com", retry_count=1))
        time.sleep(60)


if __name__ == "__main__":
    main()
