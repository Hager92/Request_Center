# Changes — Requests form freeze (25 Aug 2026)

This file lists only the code changed to stop the Requests form from staying grey after save or open.

Example: `REQ-2026-00094` (HR, Draft) showed a washed-out form while Desk waited.

Paths are under `apps/request_center/request_center/` unless noted.

---

## Why it was slow

Desk freezes the form (grey overlay) until pending AJAX finishes.

Every Requests form had Purchase and Inventory connections:

| Group | DocType | Link field |
| --- | --- | --- |
| Purchase | Tender | `request` |
| Purchase | Material Request | `request_center_request` |
| Purchase | Request for Quotation | `request_center_request` |
| Purchase | Supplier Quotation | `request_center_request` |
| Purchase | Purchase Order | `request_center_request` |
| Purchase | Purchase Receipt | `request_center_request` |
| Inventory | Stock Entry | `request_center_request` |

After save, Frappe called `frappe.desk.notifications.get_open_count` and counted those ERPNext tables for this request name. That ran even for an HR Draft with no purchasing documents. The overlay stayed until those counts returned or timed out.

Those links still live in `request_center/doctype/requests/requests.json` lines 437–472. They are not removed. They are only skipped on the form when they are not needed.

---

## Change 1 — Skip connection counts unless Material Request is in fulfillment

**File:** `request_center/doctype/requests/requests.js`

### Call site

| Lines | Symbol | What changed |
| --- | --- | --- |
| 75 | `refresh` | Calls `setup_request_connections(frm)` after the other form helpers |

### New function

| Lines | Symbol | What it does |
| --- | --- | --- |
| 251–266 | `setup_request_connections` | If the request is not a Material Request in Approved / In Progress / Completed: set `frm.dashboard._fetched_counts = true` so `get_open_count` is skipped, and hide the Connections (Purchase / Inventory) block |

**Business logic**

- HR, Service, Other, Draft, Need Approval, Rejected: no Purchase/Inventory count, no overlay wait.
- Material Request after approval: Connections stay, counts still run.

---

## Change 2 — Index the ERPNext link fields (material path)

**File:** `setup/purchase_links.py`

| Lines | Field | What changed |
| --- | --- | --- |
| 43 | `request_center_request` | `"search_index": 1` |
| 60 | `request_center_tender` | `"search_index": 1` |
| 78 | `request_center_material_request` | `"search_index": 1` |

**Business logic**

When a Material Request in fulfillment does count Purchase Order / Stock Entry / RFQ, MySQL can use an index instead of scanning the whole table.

This takes effect after `bench --site mysite.local migrate`.

---

## Files not changed

- `requests.json` connection list — still the source of Purchase / Inventory buttons for material fulfillment
- Approval, notifications, workflow — not part of this freeze

---

## How to see it

1. Hard-refresh Desk (Ctrl+Shift+R) so `requests.js` reloads.
2. Open the HR Draft again. Overlay should clear immediately. Purchase / Inventory buttons should not appear on that draft.
3. Optional: `bench --site mysite.local migrate` then `clear-cache` for the new indexes.

---

## Related docs

- Full spec map: `SPEC_IMPLEMENTATION.md`
- Canvas: spec-implementation-map (sections + line ranges for the rest of the app)
