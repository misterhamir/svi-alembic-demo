"""Smoke test the extraction progress overlay end-to-end."""

import asyncio
from pathlib import Path
from playwright.async_api import async_playwright

BASE = "http://localhost:8080"
SHOT_DIR = Path("/tmp/svi-demo-shots-extract")
SHOT_DIR.mkdir(exist_ok=True)
for old in SHOT_DIR.glob("*.png"):
    old.unlink()

FIXTURE = "/Users/user/Documents/PROJECT/pf_with_files/svi-demo/fixtures/seed-cases/06-tdsi-invoice.pdf"


async def shot(page, name):
    p = SHOT_DIR / f"{name}.png"
    await page.screenshot(path=str(p), full_page=False)
    print(f"  shot: {p.name}")


async def main():
    async with async_playwright() as p:
        b = await p.chromium.launch()
        ctx = await b.new_context(viewport={"width": 1440, "height": 900})
        page = await ctx.new_page()
        page.on("pageerror", lambda exc: print(f"  [pageerror] {exc}"))

        await page.goto(f"{BASE}/ui/operator-queue.html")
        await page.wait_for_selector("tr[data-case-id]", timeout=8000)

        # Trigger upload
        await page.set_input_files("#new-case-input", FIXTURE)

        # Overlay should appear
        await page.wait_for_selector("#extract-overlay:not(.hidden)", timeout=4000)
        await shot(page, "01-overlay-stage-1")

        # Wait until at least 2 stages have a checkmark (i.e. status="done" → emerald icon)
        await page.wait_for_function(
            """() => document.querySelectorAll('#extract-stages .bg-emerald-500').length >= 2""",
            timeout=15000,
        )
        await shot(page, "02-overlay-mid-progress")

        # Wait for the "Extraction complete" success block
        await page.wait_for_selector("#extract-result:not(.hidden)", timeout=20000)
        detail = await page.locator("#extract-result-detail").text_content()
        print(f"  result detail: {detail!r}")
        await shot(page, "03-overlay-complete")

        # Then it should redirect to case-detail
        await page.wait_for_url(lambda u: "case-detail.html" in u, timeout=8000)
        await page.wait_for_selector(".field-row", timeout=10000)
        await shot(page, "04-redirected-to-case-detail")

        await b.close()
    print("done")


if __name__ == "__main__":
    asyncio.run(main())
