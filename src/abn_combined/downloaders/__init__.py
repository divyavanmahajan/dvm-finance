"""Download workers for ABN AMRO and PayPal — both attach to the user's real
Chrome over CDP (see `browser.py`).

Each downloader runs in a worker thread; Playwright's sync API must not execute
on the asyncio event loop.
"""
