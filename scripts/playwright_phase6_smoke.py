"""Phase 6 smoke test — drives the new admin/manager screens.

Walks: NEW CASE upload, approvals queue, dashboard, view-only canvas.
Requires backend at :8080.
"""

from __future__ import annotations

import asyncio
import sys
from pathlib import Path

from playwright.async_api import async_playwright

BASE = "http://localhost:8080"
SHOT_DIR = Path("/tmp/svi-demo-shots-phase6")
SHOT_DIR.mkdir(exist_ok=True)
for old in SHOT_DIR.glob("*.png"):
    old.unlink()

FIXTURE = "/Users/user/Documents/PROJECT/pf_with_files/svi-demo/fixtures/seed-cases/09-grand-indonesia-bundle.pdf"


async def shot(page, name: str):
    path = SHOT_DIR / f"{name}.png"
    await page.screenshot(path=str(path), full_page=False)
    print(f"  shot: {path.name}")


async def main():
    findings: list[str] = []

    async with async_playwright() as p:
        browser = await p.chromium.launch()
        context = await browser.new_context(viewport={"width": 1440, "height": 900})
        page = await context.new_page()
        page.on("pageerror", lambda exc: (print(f"  [pageerror] {exc}"), findings.append(f"JS error: {exc}")))
        page.on("console", lambda msg: print(f"  [{msg.type}] {msg.text}") if msg.type in ("error", "warning") else None)

        # ---- 1. Operator queue: sidebar nav present ----
        print("\n[1] queue + sidebar nav")
        await page.goto(f"{BASE}/ui/operator-queue.html")
        await page.wait_for_selector("tr[data-case-id]", timeout=8000)
        nav_links = await page.locator("nav a").count()
        print(f"  nav links: {nav_links}")
        if nav_links < 4:
            findings.append(f"sidebar should have ≥4 links, got {nav_links}")
        await shot(page, "01-queue-with-nav")

        # ---- 2. NEW CASE upload ----
        print("\n[2] NEW CASE upload")
        await page.set_input_files("#new-case-input", FIXTURE)
        # Wait for redirect to case-detail
        await page.wait_for_url(lambda u: "case-detail.html" in u, timeout=20000)
        await page.wait_for_selector(".field-row", timeout=8000)
        url = page.url
        case_id = url.split("id=")[-1]
        print(f"  uploaded → {case_id}")
        await shot(page, "02-after-new-case-upload")

        # ---- 3. Approvals queue ----
        print("\n[3] approvals queue")
        # Move a case to pending_approval_L1 by clicking approve once on the case we just uploaded
        await page.locator("#btn-approve").click()
        await page.wait_for_function(
            "document.getElementById('case-status-pill').textContent.includes('Awaiting Approval')",
            timeout=10000,
        )
        await page.goto(f"{BASE}/ui/approvals-queue.html")
        await page.wait_for_selector("tr[data-case-id], td:has-text('No cases')", timeout=8000)
        approval_rows = await page.locator("tr[data-case-id]").count()
        print(f"  approval rows: {approval_rows}")
        if approval_rows == 0:
            findings.append("approvals queue rendered 0 rows (expected ≥1)")
        await shot(page, "03-approvals-queue")

        # Switch filter to integration_error
        await page.locator("#state-filter").select_option("integration_error")
        await page.wait_for_timeout(400)
        await shot(page, "04-approvals-filter-error")
        await page.locator("#state-filter").select_option("pending_approval_L1")
        await page.wait_for_timeout(400)

        # ---- 4. Dashboard ----
        print("\n[4] dashboard")
        await page.goto(f"{BASE}/ui/dashboard.html")
        await page.wait_for_function(
            "document.getElementById('kpi-total').textContent !== '—'",
            timeout=8000,
        )
        kpi_total = await page.locator("#kpi-total").text_content()
        kpi_pending = await page.locator("#kpi-pending-approval").text_content()
        erp_mode = await page.locator("#erp-mode").text_content()
        print(f"  total cases: {kpi_total}, pending approval: {kpi_pending}, erp: {erp_mode}")
        if int(kpi_total or "0") == 0:
            findings.append("dashboard shows 0 cases despite seeded data")
        await shot(page, "05-dashboard")

        # Toggle ERP and re-screenshot
        await page.locator("#toggle-erp").click()
        await page.wait_for_timeout(400)
        new_mode = await page.locator("#erp-mode").text_content()
        print(f"  after toggle: erp={new_mode}")
        await shot(page, "06-dashboard-erp-toggled")
        # toggle back
        await page.locator("#toggle-erp").click()
        await page.wait_for_timeout(300)

        # ---- 5. Canvas (view-only) ----
        print("\n[5] canvas editor (view-only)")
        await page.goto(f"{BASE}/ui/canvas-editor.html")
        await page.wait_for_selector(".drawflow-node", timeout=10000)
        nodes = await page.locator(".drawflow-node").count()
        print(f"  nodes rendered: {nodes}")
        if nodes != 8:
            findings.append(f"canvas should render 8 nodes, got {nodes}")
        await shot(page, "07-canvas-overview")

        # Click an extract node and verify panel opens
        await page.locator(".drawflow-node.extract").first.click()
        await page.wait_for_timeout(500)
        panel_class = await page.locator("#props-panel").get_attribute("class") or ""
        panel_open = "translate-x-full" not in panel_class
        print(f"  props panel open after node click: {panel_open}")
        if not panel_open:
            findings.append("clicking a node did not open the props panel")
        # Verify panel body has rendered config content
        body_text = await page.locator("#props-body").text_content()
        has_schema_pinning = "schema_pinning" in body_text.lower() or "schema pinning" in body_text.lower()
        print(f"  panel mentions schema pinning: {has_schema_pinning}")
        if not has_schema_pinning:
            findings.append("extract node panel missing schema_pinning config")
        await shot(page, "08-canvas-node-selected")

        # Verify snap-back: programmatically move a node, expect it to revert
        before_pos = await page.evaluate("""
            () => { const n = editor.getNodeFromId(1); return { x: n.pos_x, y: n.pos_y }; }
        """)
        await page.evaluate("""
            () => {
                editor.dispatch('nodeMoved', 1);
                const n = editor.getNodeFromId(1);
                n.pos_x = 9999;
                n.pos_y = 9999;
                editor.dispatch('nodeMoved', 1);
            }
        """)
        await page.wait_for_timeout(200)
        after_pos = await page.evaluate("""
            () => { const n = editor.getNodeFromId(1); return { x: n.pos_x, y: n.pos_y }; }
        """)
        snapped_back = (after_pos["x"] == before_pos["x"] and after_pos["y"] == before_pos["y"])
        print(f"  node snapped back after forced move: {snapped_back} (before={before_pos}, after={after_pos})")
        if not snapped_back:
            findings.append("snap-back logic failed — node retained moved position")
        await shot(page, "09-canvas-after-snap-test")

        await browser.close()

    print("\n=== summary ===")
    print(f"screenshots: {SHOT_DIR}")
    if findings:
        print("findings:")
        for f in findings:
            print(f"  - {f}")
        sys.exit(1)
    else:
        print("all checks passed")


if __name__ == "__main__":
    asyncio.run(main())
