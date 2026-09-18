# VoltCraft — HDB Electrical Site Operations

## মূল অনুরোধ
আচ্ছা চলো একটা সম্পুর্ণ electrical company এর জন্য project management system বানাই। এটা সম্পর্কে আমি তোমাকে কিছু ধারণা দিচ্ছি সেটাকে তুমি আরো next level এ নিয়ে যাবে, আমি যে electrical company তে কাজ করছি তারা মূলত Singapore a HDB project এ electrical কাজ গুলো করে তো একটা HDB project এ অনেক গুলো Blocks থাকে একাকটা ব্লাক আবার অনেক তালা করে আবার একেকটা তালাতে অনেক গুলো করে unite থাকে ধরো Blk 35A level 1 unite number 450 প্রথম এ selape এ casting এর আগে PVC পাইপ বসানো এর কাজ করা হয় তারপর যখন ওই unite এর casting complete হয়ে যায় তখন unite এর মধ্যে power point, data,tv,light switch এর জন্য selape যে pvc পাইপ গুলো বসানো হয়েছিলো সেইগুলোর point hacking করে pvc এর point গুলো বের করা হয় তারপর সেই point গুলোতে wire ঢুকানো হয় ওই PVC পাইপ গুলোর মধ্যে তারপর GI/PVC পাইপ, gang boxs বসানো হয় তারপর ওই wall এর point এর যে recharge ponit গুলোই পাইপ gang boxs বসানো complete হয়ে যায় সেইগুলো RTO check করে approval দিলে সিমেন্ট দিয়ে ওই recharge গুলো plaster করে দেওয়া হয় পরে ওই point গুলোতে switch,socket,etch লাগানো হয়, তারপর, maga test করা হয় প্রতি টা pointe এ, মানে যে wire গুলোর insulation testing হয় তো এই হচ্ছে কাজ গুলো, এবার তুমি পুরো বিষয় গুলো ভালো করে ভেবে পুরো system টা কিভাবে বানানো যায়।

Follow-up: “Start the task now”, with five images of physical block progress boards/site schedule.

### ব্যবহারকারীর নিশ্চিত পছন্দ
- শ্রমিক, মালামাল ও খরচের হিসাব প্রথম সংস্করণেই অন্তর্ভুক্ত।
- ভাষা: বাংলা, English, Chinese (Simplified Chinese implemented)।
- ছবির Block 35A–36C কাঠামো ব্যবহার; অস্পষ্ট unit layout/অগ্রগতি সম্পাদনাযোগ্য নমুনা।
- Authentication, payments, AI, recurring jobs or uploads were NOT requested.

## ব্যবহারকারী
- Company/project manager: ব্লকের অগ্রগতি, বাজেট, রিসোর্স ও রিপোর্ট।
- Site supervisor/electrician: ইউনিটের কাজ আপডেট, হাজিরা ও স্টক ব্যবহার।
- Inspection coordinator: RTO আবেদন, অনুমোদন, সংশোধন ও পুনঃপরিদর্শনের রেকর্ড।
- Tester: পয়েন্টভিত্তিক insulation readings এবং পরীক্ষকের সিদ্ধান্ত।
- Storekeeper/accounts: মালামাল ও SGD expense ledger।

## মূল চাহিদা (স্থির)
1. Project → Block → Level → Unit hierarchy; create projects/blocks/units, editable metadata.
2. 9 sequential stages: Slab PVC → Casting confirmation → Hacking → Wiring → GI/PVC & gang boxes → RTO approval → Cement plastering → Accessories → Insulation testing.
3. Stage skips prevented; RTO approval gates plastering. Rework/resubmission supported.
4. Per-point test voltage and L–N/L–E/N–E in MΩ; manually recorded pass/fail; all latest point results must pass to complete a unit.
5. Workforce, dated attendance/hours, daily rates; inventory with stock movement; category/block expenses in SGD.
6. Overview, block-floor matrix/list, filters/search, CSV export, 3-language UI, responsive design.

## Architecture
- React 19 / React Router / Shadcn primitives / Lucide; Manrope+Outfit and Bengali/Chinese webfonts.
- FastAPI + Pydantic validation; Motor MongoDB. Actual persisted data; no mocked APIs.
- API URL only from `frontend/.env` REACT_APP_BACKEND_URL; DB only from existing `backend/.env` MONGO_URL and DB_NAME. Protected env unchanged.
- `/app/backend/server.py`: app/lifespan; `models.py`: input/response models; `routes.py`: projects/unit workflow/inspection/test/export; `operations.py`: workforce/materials/expense; `seed.py`: reference workspace.
- UUID/string IDs; MongoDB projections exclude `_id`; response models on document endpoints; timezone-aware timestamps.
- Collections: projects, blocks, units, workers, attendance, materials, movements, expenses, inspections, tests, activity.
- Unit `stage` is completed count 0–9. At 5 an RTO decision is required; approval sets6. Tests available only at8. Final advance8→9 verifies all latest results.
- Atomic stock decrement with balance predicate. Expected-stage predicate prevents stale transitions. Attendance unique worker/date.
- Sample reset validates real records/history before mutation, claims untouched sample version, deletes sample-only records. Real workflow writes clear sample flag.
- Single shared workspace, no identity verification or authorization. Project scoping is organization of data, NOT access control. Inspector names are recorded labels, not authenticated identities.
- No automatic electrical safety certification or automatic pass thresholds. On-screen disclaimer is explicit. Do not represent records as regulatory certificates.
- Estimated labour is daily_rate × hours /8, not statutory overtime/payroll computation; expenses are a separate manual ledger to avoid double counting.

## Implemented — 2026-09-18
- 11 routes: overview, projects, units, inspections, testing, workforce, materials, expenses, reports, references, settings.
- Rail Garden reference workspace with 6 blocks /465 units. Block schedule visually checked against original:
  - 35A:11 storeys/90 units;35B:11/122;35C:10/109;36A:9/64;36B:7/48;36C:5/32.
  - Project name Rail Garden visible in uploaded plan; location/company/budget/date, unit allocations, statuses and operational entries remain editable examples.
  - Residential layouts generated from level2; add-unit supports any floor1..block height. No claim that generated numbering/unit types replicate as-built drawings.
- Dashboard: totals, progress, RTO queue, daily attendance, 6 block cards, stage completion distribution, low-stock/inspection alerts, recent activity.
- Interactive color-coded matrix, all-block list, status/level filters, global unit/team/block search, drawer workflow/details/test/history.
- New projects and blocks auto-generate zero-progress units; editing project metadata and unit metadata.
- RTO schedule, approve/rework, resubmit, recorded inspector/findings.
- Add power/light/socket/switch/data/TV points; per-point numerical readings, fail/retest, latest-result gating.
- Workers add/edit/archive; Singapore dated attendance (present/absent/leave), 0–16 hours, rate snapshot, absence forced0.
- Inventory metadata, receive/issue, stock history, low-stock filter/alerts, inventory value; direct stock edits blocked.
- Expenses create/edit/delete; category/block/search, budget remaining and category breakdown; cents preserved.
- 7 CSV reports with UTF-8 BOM and spreadsheet-formula escaping: units/inspections/tests/workers/attendance/materials/expenses.
- Five user-provided site images locally stored, rotated upright, title mappings manually verified; modal and original-size image view.
- English/Bangla/Chinese UI with remembered selection; light/dark appearance; responsive sidebar and scrollable dense tables/matrix.
- Page title/favicon branding. Relevant visual HDB photo locally hosted.
- Shared UI controls include data-testid and success/error feedback.

## Verification — 2026-09-18
- Testing agent report: `/app/test_reports/iteration_1.json`.
- Functional pytest suite `/app/backend/tests/test_project_management_api.py`: 9/9 passed; public external API endpoint. Post-fix results `/app/test_reports/pytest/pytest_results_fixed.xml`.
- Full UI unit lifecycle verified: sequential stages, RTO reject/resubmit/approve, stage8 fail→retest pass, all-point completion.
- Workforce, inventory, expenses, exports, project scoping and persistence exercised.
- Responsive overflow tested by testing agent at1440/768/390px.
- Fixed sample reset data loss on rejected resets; corrected Bengali activeProject glyphs; corrected source-photo ordering/titles; all-block global search fixed.
- Main screenshots verified dashboard, matrix, drawer, Bangla/Chinese, reference image, dark theme. Global search `36B` returns48/465units.
- Final `yarn build` passed: `/app/test_reports/build-final.log`. Python syntax compilation passed.
- QA projects removed; affected demo inspection records restored. Final state6blocks/465units/12workers/230inspection records,45pending; no TEST/UI_QA data remains.

## Known scope and prioritized backlog
### P0 before actual multi-user business use (not requested in this iteration)
- Real user authentication, server-side roles (manager/supervisor/RTO/tester/storekeeper), project membership and authorization; load backend-authorization skill before implementing.
- Replace example data with verified company/site records and unit/point inventory; confirm project-specific testing procedure with qualified electrical personnel.
### P1
- Photo attachments for work/inspection/test evidence, authenticated object storage.
- Configurable work/point templates and real circuit schedules, instrument/calibration details, tester signatures, configurable authorized test criteria.
- Unit-level materials allocation, labour job assignments and deliberate linking to expenses; purchase orders/supplier invoices.
- Project archive/remove workflow with safe cascade/retention policy (no project delete currently).
- Multi-document transactions/recovery, pagination for very large workspaces and offline/pending-sync updates.
### P2
- QR labels to open individual units quickly on site.
- Bulk import of verified floor/unit layouts, customizable reports and handover packs.
- PDF export if requested: load document-verification skill before implementing.
- Reminders if requested: load scheduled-recurring-tasks skill (no timers/background schedulers currently).

## Next actions
1. Review actual unit numbering, templates and point inventory with user.
2. Add authenticated role-based access before sharing real business data among staff.
3. Add photo evidence and unit QR access to improve site reporting.
