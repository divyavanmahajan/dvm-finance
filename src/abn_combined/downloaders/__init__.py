"""Download workers for ABN AMRO (Playwright) and PayPal (CDP).

Each downloader runs in a worker thread; Playwright's sync API must not execute
on the asyncio event loop.
"""
