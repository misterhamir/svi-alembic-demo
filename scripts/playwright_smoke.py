"""End-to-end smoke test for svi-demo via Playwright.

Walks the heart-of-pitch flow with screenshots at every key moment so we
can verify the UI without a human in the loop. Backend must be running
on :8080 with EXTRACTION_BACKEND=stub.

Run:
    source .venv/bin/activate
    python scripts/playwright_smoke.py
"""

from __future__ import annotations

import asyncio
import json
import os
import sys
from pathlib import Path
from urllib import request

from playwright.async_api import async_playwright, expect

BASE = "http://localhost:8080"
SHOT_DIR = Path("/tmp/svi-demo-shots")
SHOT_DIR.mkdir(exist_ok=True)

# clear old shots
for old in SHOT_DIR.glob("*.png"):
    old.unlink()


def api_get(path: str) -> dict:
    with request.urlopen(f"{BASE}{path}") as r:
        return json.loads(r.read())


def api_post(path: str, body: dict | None = None) -> dict:
    data = json.dumps(body or {}).encode()
    req = request.Request(
        f"{BASE}{path}",
        data=data,
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    with request.urlopen(req) as r:
        return json.loads(r.read())


def upload_fixture(filename: str) -> str:
    """Use curl since urllib multipart is painful."""
    import subprocess
    res = subprocess.run(
        ["curl", "-s", "-X", "POST", "-F", f"file=@fixtures/seed-cases/{filename}",
         f"{BASE}/api/cases/upload"],
        capture_output=True, text=True, check=True,
    )
    return json.loads(res.stdout)["case_id"]


async def shot(page, name: str, full: bool = True):
    path = SHOT_DIR / f"{name}.png"
    await page.screenshot(path=str(path), full_page=full)
    print(f"  shot: {path.name}")


async def main():
    findings: list[str] = []

    # Make sure ERP is in 201 mode
    api_post("/api/mock-erp/toggle", {"mode": "201"})

    # Upload a fresh fixture for this run so we have a known clean case
    test_case_id = upload_fixture("07-tangcity-listrik-invoice.pdf")
    print(f"uploaded test case: {test_case_id}")

    async with async_playwright() as p:
        browser = await p.chromium.launch()
        context = await browser.new_context(viewport={"width": 1440, "height": 900})
        page = await context.new_page()

        page.on("console", lambda msg: print(f"  [console.{msg.type}] {msg.text}") if msg.type in ("error", "warning") else None)
        page.on("pageerror", lambda exc: (print(f"  [pageerror] {exc}"), findings.append(f"JS error: {exc}")))

        # ---- 1. Queue ----
        print("\n[1] queue")
        await page.goto(f"{BASE}/ui/operator-queue.html")
        await page.wait_for_selector("tr[data-case-id]", timeout=8000)
        rows = await page.locator("tr[data-case-id]").count()
        print(f"  rows visible: {rows}")
        if rows == 0:
            findings.append("queue rendered 0 rows")
        await shot(page, "01-queue")

        # Filter test
        await page.locator("#state-filter").select_option("integration_error")
        await page.wait_for_timeout(500)
        ie_rows = await page.locator("tr[data-case-id]").count()
        print(f"  integration_error rows: {ie_rows}")
        await shot(page, "02-queue-filter-integration-error")
        await page.locator("#state-filter").select_option("")
        await page.wait_for_timeout(300)

        # ---- 2. Click into the test case ----
        print(f"\n[2] open case {test_case_id}")
        await page.goto(f"{BASE}/ui/case-detail.html?id={test_case_id}")
        # Wait for at least one PDF canvas to appear
        await page.wait_for_selector("#pdf-pages canvas", timeout=15000)
        # Wait for fields to render
        await page.wait_for_selector(".field-row", timeout=8000)
        n_fields = await page.locator(".field-row").count()
        n_canvases = await page.locator("#pdf-pages canvas").count()
        print(f"  field rows: {n_fields}, canvases: {n_canvases}")
        if n_canvases == 0:
            findings.append("PDF canvas did not render")
        await shot(page, "03-case-loaded")

        # ---- 3. Click a field — expect bbox highlight ----
        print("\n[3] click field row → expect bbox highlight")
        # Find the field with the lowest confidence (most likely to be amber/red)
        field_data = await page.evaluate("""
            () => Array.from(document.querySelectorAll('.field-row')).map((tr, i) => ({
                idx: i,
                docIdx: parseInt(tr.dataset.docIndex, 10),
                fieldName: tr.dataset.fieldName,
            }))
        """)
        target_idx = field_data[0]["idx"]
        # Try to pick an amber-tinted row if any
        amber_row_idx = await page.evaluate("""
            () => {
                const rows = Array.from(document.querySelectorAll('.field-row'));
                const amber = rows.findIndex(r => r.classList.contains('bg-amber-50/50'));
                return amber;
            }
        """)
        if amber_row_idx >= 0:
            target_idx = amber_row_idx
            print(f"  picked amber-banded row at idx {target_idx}")
        await page.locator(".field-row").nth(target_idx).click()
        await page.wait_for_timeout(800)
        n_overlays = await page.locator(".bbox-highlight").count()
        print(f"  bbox-highlight elements: {n_overlays}")
        if n_overlays == 0:
            findings.append("clicking field produced no bbox-highlight overlay")
        await shot(page, "04-field-highlighted")

        # ---- 4. Inline correction ----
        print("\n[4] inline edit")
        target_row = page.locator(".field-row").nth(target_idx)
        await target_row.locator("[data-edit]").click()
        await page.wait_for_selector(".field-row input", timeout=3000)
        input_el = target_row.locator("input")
        await input_el.fill("TEST OVERRIDE")
        await input_el.press("Enter")
        await page.wait_for_timeout(1500)
        # Look for the human badge on this row
        new_value = await target_row.locator("[data-value-cell]").text_content()
        has_human = await target_row.locator("text=human").count() > 0
        print(f"  new value: {new_value!r}, has 'human' badge: {has_human}")
        if not has_human:
            findings.append("provenance badge did not flip to 'human' after edit")
        await shot(page, "05-after-edit")

        # ---- 5. Approve twice → complete ----
        print("\n[5] approve x2 → complete")
        await page.locator("#btn-approve").click()
        await page.wait_for_function(
            "document.getElementById('case-status-pill').textContent.includes('Awaiting Approval')",
            timeout=8000,
        )
        await shot(page, "06-after-approve-1")

        await page.locator("#btn-approve").click()
        await page.wait_for_function(
            "document.getElementById('case-status-pill').textContent.includes('Complete')",
            timeout=10000,
        )
        await shot(page, "07-after-approve-2-complete")
        complete_pill = await page.locator("#case-status-pill").text_content()
        print(f"  status pill: {complete_pill!r}")

        # ---- 6. History tab ----
        print("\n[6] history tab")
        await page.locator("button[data-tab='history']").click()
        await page.wait_for_timeout(400)
        await shot(page, "08-history")

        # ---- 7. Integration error path ----
        print("\n[7] integration_error path")
        api_post("/api/mock-erp/toggle", {"mode": "503"})
        bad_case = upload_fixture("08-tangcity-faktur-pajak.pdf")
        print(f"  fresh case: {bad_case}")
        await page.goto(f"{BASE}/ui/case-detail.html?id={bad_case}")
        await page.wait_for_selector(".field-row", timeout=8000)
        await page.locator("#btn-approve").click()
        await page.wait_for_function(
            "document.getElementById('case-status-pill').textContent.includes('Awaiting Approval')",
            timeout=8000,
        )
        await page.locator("#btn-approve").click()
        await page.wait_for_function(
            "document.getElementById('case-status-pill').textContent.includes('ERP Error')",
            timeout=10000,
        )
        await page.wait_for_selector("#error-banner:not(.hidden)", timeout=4000)
        await shot(page, "09-integration-error")

        # Retry after toggling back to 201
        api_post("/api/mock-erp/toggle", {"mode": "201"})
        await page.locator("#btn-retry").click()
        await page.wait_for_function(
            "document.getElementById('case-status-pill').textContent.includes('Complete')",
            timeout=10000,
        )
        await shot(page, "10-after-retry-complete")

        await browser.close()

    print("\n=== summary ===")
    print(f"screenshots: {SHOT_DIR}")
    if findings:
        print("findings:")
        for f in findings:
            print(f"  - {f}")
        sys.exit(1)
    else:
        print("no issues detected")


if __name__ == "__main__":
    asyncio.run(main())
