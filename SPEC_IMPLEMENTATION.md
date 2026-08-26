# Request Center — Spec Implementation Map

This file lists every specification section that was implemented in `apps/request_center`.

For each section:

- **Business logic** — the rule the system follows
- **Where it happens** — files and main functions
- **What was changed** — what was built
- **What is missing** — gaps, data setup, or leftover legacy

Base path: `apps/request_center/request_center/`

---

## How to read statuses

| Status | Meaning |
| --- | --- |
| Done | Implemented in code and migrated |
| Partial | Works, with a listed gap |
| Data | Code is ready; site data or ERPNext setup is still needed |

---

## 1. Module Overview

**Status:** Done

**Business logic**
Request Center is the single module to create, configure, approve, track, and manage employee requests. Employees open the module and see Request Types. Each type can have its own category, department, dynamic fields, mandatory fields, approval levels, approvers, and sequence. Status, approval progress, and pending actions stay visible.

**Where it happens**
- `hooks.py` — app title, description, Apps screen route `/app/request-center-home`
- `request_center/page/request_center_home/` — main page
- `request_center/doctype/request_type/` — type configuration
- `request_center/doctype/requests/` — request form tracker
- `workspace_sidebar/request_center.json` — sidebar

**What was changed**
Module description, dashboard overview line, pending-actions banner, My Requests (status / level / approver / result), Request Type labels for category, dynamic fields, and approval sequence.

**What is missing**
None in code. Users must hard-refresh Desk after deploys. Some Request Types on the site still have empty Execution Mode (`Budget Request`, `H Request`).

---

## 2. Request Center Main Page (Card Dashboard)

**Status:** Partial (layout done; mockup art not bundled)

**Business logic**
The first screen is a card dashboard, not the Requests list. Each active Request Type is one card: icon, name, New Request, To Review counter.

**Where it happens**
- `request_center/page/request_center_home/request_center_home.js`
- `request_center/page/request_center_home/request_center_home.css`
- `request_center/page/request_center_home/request_center_home.json`
- `api/requests.py` — `get_portal_data()`
- `public/js/request_center.js` — workspace opens the portal
- `request_center/doctype/requests/requests_list.js` — list primary action returns to the dashboard

**What was changed**
Card grid matching the mockup (left icon, name, plum New Request, grey `To Review: N`). Clicking New Request opens a request with that type. Clicking To Review opens waiting requests for that type.

**What is missing**
The mockup’s 3D illustrations are not in the app. Cards use the **Request Type Icon** field (Frappe icon). Set an icon on each type. Inactive types do not appear.

---

## 3–10. Request Type, Form, and Request Fields

These were the earlier configuration/form sections. They are in the same Request Type + Requests documents.

**Status:** Done

**Business logic**
- Type name is unique.
- Category is one of: Service Request, Material Request, Disbursement Request, Other Requests.
- Department comes from the type onto the request.
- Extra form fields are defined on the type (name, type, mandatory) and copied onto the request when the type is selected.
- Mandatory extra fields are required before Submit (Draft can be incomplete).
- Requested By = current employee (User linked to Employee).
- Request Date = now, then locked.
- Status is read-only on the form; only workflow actions change it.

**Where it happens**
- `request_center/doctype/request_type/request_type.json` / `.py` / `.js`
- `request_center/doctype/request_type_requirement/`
- `request_center/doctype/request_requirement_value/`
- `request_center/doctype/requests/requests.json` / `.py` / `.js`
- `api/requests.py` — `create_request`, `update_request`, protected fields

**What is missing**
Requested By fails if the logged-in user has no Employee record (Administrator is allowed). Dynamic field types are Frappe-like (Data, Date, Number, Select, Link, …), not a separate form builder.

---

## 11. Configurable Approval Levels on Request Type

**Status:** Done

**Business logic**
Approval is configured on the Request Type as a child table. Each row: Level (sequence), Approver (Employee), Required. Level 1 runs first. Different types can have different flows. An active type must have at least one level.

**Where it happens**
- `request_center/doctype/request_type_approval_level/`
- `request_center/doctype/request_type/request_type.py` — `_validate_approval_levels`, `_normalize_approval_levels`
- `api/requests.py` — `_get_approval_level_rows`, `approve_request`

**What is missing**
Legacy DocType **Approval Matrix** still exists but is hidden (`in_create`). Approval is not configured there anymore. Old matrices can still be copied onto a type if the type has no levels.

---

## 12–17. Approval Execution, Visibility, Tracking

**Status:** Done

**Business logic**
- Only the current-level approver (or Administrator) can Approve / Reject.
- After a required level is approved, the next level becomes current.
- After the last required level, status becomes Approved.
- Requester always sees current level, current approver, and a tracking table (Pending / Need Approval / Approved / Rejected).

**Where it happens**
- `api/requests.py` — `approve_request`, `reject_request`, `sync_approval_tracking`, `apply_approval_progress_to_doc`, `apply_workflow`
- `request_center/doctype/request_approval_tracking/`
- `request_center/doctype/requests/requests.js` — Approve/Reject buttons, tracker, View Approvers
- `fixtures/workflow.json` — workflow states Draft → Need Approval → Approved / Rejected → In Progress → Completed

**What is missing**
Workflow still contains old state names (`Pending Approval`, `Pending Manager`, `Pending Department`) for compatibility. The live status used for new work is **Need Approval**.

---

## 18. Notifications

**Status:** Partial (desk + email from Python; standard Notification is off)

**Business logic**
Notify the requester when status or approval stage changes. Notify the current approver when their approval is required.

**Where it happens**
- `notifications.py` — `notify_request_change`, `_notify_requester`, `_notify_current_approver`, `_email_user`
- `request_center/doctype/requests/requests.py` — `on_update`
- `request_center/notification/requests_notification/` — standard Notification, **enabled: 0** so it does not double-send

**What is missing**
Email only works if site mail is configured. If SMTP is not set, desk Notification Log still works. The standard Notification document is intentionally disabled.

---

## 19. Tender

**Status:** Done

**Business logic**
After supplier selection, a Tender is created and stays linked to the original request and the ERPNext Material Request. RFQs and POs attach to that Tender.

**Where it happens**
- `request_center/doctype/tender/` plus child tables (`tender_item`, `tender_supplier`, `tender_offer`, `tender_rfq`, `tender_purchase_order`)
- `tender.py` — `ensure_tender_for_request`, `attach_document_to_tender`, `record_tender_award`
- `material_workflow.py` — Tender stage
- `setup/purchase_links.py` — custom field `request_center_tender`

**What is missing**
Tender numbering/UI is functional; there is no separate public Tender portal. Purchasing users work from the request / Tender form.

---

## 20. Supplier Comparison (Price + Delivery Time)

**Status:** Done

**Business logic**
Comparison always shows Price and Delivery Time. Method comes from Request Type: Manual Comparison, Weighted Score, or Ranked Criteria. Weights must sum to 100. Purchasing must select a supplier; the system does not auto-pick cheapest. Only submitted Supplier Quotations are compared.

**Where it happens**
- `supplier_comparison.py` — `build_comparison_rows`, `get_supplier_comparison`, scoring
- `request_center/doctype/request_supplier_comparison/`
- Request Type fields: `comparison_method`, `price_weight`, `delivery_weight`, `rank_primary`
- `material_workflow.py` — Supplier Comparison / Price + Delivery stages
- `request_center/doctype/requests/requests.js` — comparison dialog

**What is missing**
None in logic. Offers must be **submitted** Supplier Quotations against the RFQ, or comparison has nothing to rank.

---

## 21. RFQ

**Status:** Done

**Business logic**
After Tender, create and send an ERPNext Request for Quotation to Tender suppliers. Email when contact email and supplier portal exist. Draft Supplier Quotations are created per supplier. Comparison uses submitted quotes only.

**Where it happens**
- `rfq.py` — `create_and_send_rfq`, `create_and_send_rfq_for_request`
- `material_workflow.py` — `_advance_rfq`
- Requests field `rfq`; Tender button Create and Send RFQ

**What is missing**
Email send depends on supplier contact email and portal. If those are missing, RFQ is still created; the message lists who was not emailed.

---

## 22. Purchase Order

**Status:** Done

**Business logic**
After comparison/award, create a draft Purchase Order for the awarded supplier. Stamp: original request (Purchase Requisition), Tender, Material Request, supplier. Idempotent if a PO already exists. PO stays draft until Delivery.

**Where it happens**
- `purchase_order.py` — `create_purchase_order_for_request`
- `setup/purchase_links.py` — `request_center_request`, `request_center_tender`, `request_center_material_request`
- `material_workflow.py` — `_advance_po`, `_advance_delivery`

**What is missing**
PO is ERPNext Purchase Order. Delivery records receipt and then the request can Complete.

---

## 23. Final Request Type Configuration (single page)

**Status:** Done

**Business logic**
All type configuration lives on Request Type: Basic Information, Form Fields, Approval Levels. No separate pages for those. Purchasing Policy shows only for Material Request. Execution Mode shows for non-material types (uses existing Execution Mode records).

**Where it happens**
- `request_center/doctype/request_type/request_type.json` / `.js` / `.py`

**What is missing**
Execution Mode and Document Mapping DocTypes still exist (you already have Execution Mode data). They are not required as a second “form fields / approvals” page. Document Mapping is optional field mapping onto an ERPNext DocType.

---

## 24. Key Business Rules (28 rules)

**Status:** Done, with the notes below

| # | Rule | Logic | Where | Missing |
| --- | --- | --- | --- | --- |
| 1 | Type name unique | Unique field + validate | `request_type.json`, `request_type.py` | — |
| 2 | Inactive types not on new requests | Link filter `is_active=1`; server block on new/type change | `requests.js`, `requests.py` `_validate_request_type_active` | — |
| 3 | Inactive types not on dashboard | `get_portal_data` filters `is_active=1` | `api/requests.py`, home page JS | — |
| 4 / 28 | Existing requests stay if type deactivated | Same type can still be saved; list not filtered by is_active; cannot delete type with requests | `requests.py`, `request_type.py` `on_trash` | — |
| 5 | Department from type | Fetch + server copy | `requests.json`, `requests.py` `_sync_department_from_request_type` | — |
| 6 | Requested By = current employee | Session user must have Employee | `requests.py` `_session_requested_by` | Users without Employee cannot create (except Administrator) |
| 7 | Request Date auto | Now, then locked | `requests.py` `_lock_identity_fields` | — |
| 8 | Status read-only for requester | Field read-only; API strips status; only workflow/approve/reject/fulfillment change it | `requests.py` `_validate_status_change`, `api/requests.py` `PROTECTED_REQUEST_FIELDS` | Direct Submit Draft→Need Approval is allowed |
| 9 | Dynamic fields from type | Rebuild requirements from type | `requests.py` `_sync_requirements_from_request_type` | — |
| 10 | Mandatory before submit | Enforced when status is not Draft | `requests.py` `_validate_mandatory_values`, `requests.js` | Draft save can be incomplete |
| 11 | Levels on Request Type | Child table only | `request_type.json` | Matrix fallback removed from runtime |
| 12 | Approver is Employee | Link Employee, must have user_id | `request_type_approval_level.json`, `request_type.py` | — |
| 13 | Sequence | Sorted by level | `approve_request` | — |
| 14 | Different flows per type | Levels stored per type | `_get_approval_level_rows` | — |
| 15–16 | See current level and approver | Fields + summary | `requests.json`, `apply_approval_progress_to_doc` | — |
| 17 | Track completed/pending | `approval_tracking` | `sync_approval_tracking` | — |
| 18–19 | Notifications | Desk + email | `notifications.py` | Needs mail settings for email |
| 20 | Material uses Material Request category | Items only allowed on that category | `requests.py` `_validate_material_items` | — |
| 21 | Approvals before Inventory Check | Check only if Approved or In Progress | `material_workflow.py` `run_inventory_check` | — |
| 22 | Always Inventory Check after approvals | Final approve calls `try_start_material_fulfillment`; on failure stage stays Inventory Check | `approve_request`, `try_start_material_fulfillment` | If stock/company/items fail, check is pending until Execution Team retries |
| 23 | Available → Transfer | Issue/Transfer Material Requests | `run_inventory_check` | ERPNext required |
| 24 | Unavailable → Purchase | Purchase Material Request + purchase stages | same | ERPNext required |
| 25 | Tender, RFQ, Comparison, PO | Purchase process stages | `tender.py`, `rfq.py`, `supplier_comparison.py`, `purchase_order.py` | — |
| 26 | Compare Price + Delivery | Policy + table | `supplier_comparison.py` | Submitted quotes required |
| 27 | Linked docs | Custom fields + `linked_documents` | `setup/purchase_links.py`, `material_workflow._link_document` | — |

---

## 25. Final User Experience

**Status:** Done

**Business logic**
Employee: Dashboard → New Request → complete form → Submit.  
Approver: Dashboard → To Review → open request → Approve / Reject.  
Requester tracks: Status, Current Approval Level, Current Approver, Final Result.  
Material stepper: Approval → Inventory Check → Transfer or Purchase → Tender → RFQ → Price + Delivery Comparison → PO → Delivery → Completed.

**Where it happens**
- Portal page JS/CSS
- `requests.js` — `render_request_experience`, `architecture_pipeline_html`
- List view does not start the module

**What is missing**
All Requests remains in the sidebar for history. That is intentional, not the landing page.

---

## 26. Overall Architecture

**Status:** Done

**Business logic**

```
Request Center
  → Request Type Dashboard
  → New Request / To Review
  → Request Form
  → Dynamic Form Fields
  → Submit
  → Approval Levels
  → Approved
  → Service / Other Process     OR     Material Request
         │                                    │
         │                                    Inventory Check
         │                                    ├ Available → Transfer
         │                                    └ Not Available → Purchase
         │                                         → Tender → RFQ
         │                                         → Price + Delivery Comparison
         │                                         → PO → Delivery
         └────────────────────────────────────────→ Completed
```

Service / Other uses the **existing Execution Mode** on the Request Type (HR, Internal Service, IT, Inventory, Purchase, External). Material Request ignores Execution Mode and uses the inventory-then-purchase path.

**Where it happens**
- `api/requests.py` — `approve_request`, `execute_request`, `_resolve_execution_mode`, `try_start_service_process`
- `material_workflow.py` — inventory and purchase engine
- Portal + request form steppers

**What is missing**
If Execution Mode `erp_output` is not a real DocType (for example `Leave/HR Doc`, `API`, `None`), the request still goes **In Progress** without creating an ERPNext document. Optional Document Mapping can still map fields when `target_doctype` is a real DocType.

---

## File index (where most logic lives)

| Area | Files |
| --- | --- |
| Dashboard | `request_center/page/request_center_home/*`, `public/js/request_center.js`, `public/css/request_center.css` |
| Request Type | `request_center/doctype/request_type/*`, `request_type_requirement`, `request_type_approval_level` |
| Request | `request_center/doctype/requests/*`, `api/requests.py` |
| Approval | `api/requests.py`, `request_approval_tracking`, `fixtures/workflow.json` |
| Notifications | `notifications.py` |
| Material / purchase | `material_workflow.py`, `material_fulfillment.py`, `tender.py`, `rfq.py`, `supplier_comparison.py`, `purchase_order.py`, `setup/purchase_links.py` |
| Permissions | `permissions.py`, `hooks.py` |
| Workspace | `workspace_sidebar/request_center.json`, `request_center/workspace/request_center/request_center.json`, `fixtures/workspace.json` |

---

## Cross-cutting leftovers (not a spec section)

1. **Approval Matrix** DocType — hidden leftover; do not use for new config.
2. **Document Mapping** — optional; Service/Other no longer fails if it is missing.
3. **Junk Execution Mode rows** on the site (`ddu5a6m5eh`, `eklkk48ghc`, …) — data, not code. Real modes: HR, Internal Service, IT, Inventory, Purchase, External.
4. **Standard Notification “Requests Notification”** — disabled on purpose; Python sends alerts.
5. **3D card artwork** from the mockup — not shipped; set Request Type Icon instead.
6. **Mail server** — required for email copies of notifications.
7. **Employee master** — required for Requested By and for Approver users.

---

## Form freeze on open / save (25 Aug 2026)

**Why it looked stuck:** Desk freezes the form (grey overlay) until pending AJAX finishes. Every Requests form listed Purchase and Inventory connections (Tender, Material Request, RFQ, Supplier Quotation, Purchase Order, Purchase Receipt, Stock Entry). After save, Frappe counted those ERPNext tables for `request_center_request = this request`. That ran even on an HR Draft with no purchasing docs, so the overlay stayed until the counts returned (or timed out).

**What changed**
- `doctype/requests/requests.js` — `setup_request_connections` (called from `refresh`). Purchase / Inventory connections and `get_open_count` run only for Material Request in Approved / In Progress / Completed. HR, Service, Draft, and Need Approval skip the count.
- `setup/purchase_links.py` — `search_index: 1` on `request_center_request`, `request_center_tender`, and `request_center_material_request` so material counts stay fast.

Reload Desk after migrate. Open REQ-2026-00094 again; the overlay should clear immediately.

---

## Quick path after Desk reload

1. Open **Request Center** (card dashboard).
2. Configure types under **Request Type** (fields + approval levels + icon + Execution Mode for non-material).
3. Employee: **New Request** → fill → **Submit**.
4. Approver: **To Review** → **Approve** / **Reject**.
5. Material: Inventory Check then Transfer or Purchase chain.
6. Service/Other: existing Execution Mode after the last approval.
