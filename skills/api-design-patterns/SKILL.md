---
name: api-design-patterns
description: >-
  Design, review, refactor, and audit resource-oriented HTTP/REST/JSON web APIs,
  OpenAPI/Swagger specs, Protobuf HTTP transcoding, and backend route
  handlers/DTOs using JJ Geewax's API Design Patterns. Trigger for: designing or
  reviewing REST endpoints, URL/resource hierarchies, OpenAPI schemas, standard
  or :custom methods, partial PATCH field masks, cursor pagination, filter DSLs,
  batch endpoints, async long-running operations, rerunnable jobs, soft
  deletion, idempotency/deduplication keys, dry-run validation, revisions, retry
  policies, or HTTP request signatures. DO NOT trigger for: GraphQL-only
  schemas, internal in-process library/SDK functions, frontend UI table
  pagination, or raw SQL authoring.
---

# API Design Patterns

Operational playbook distilled from JJ Geewax's *API Design Patterns* (Manning), with clearly labeled >90%-confidence industry supplements. Goal: maximize **Operational** utility, **Expressiveness**, **Simplicity**, and **Predictability** by keeping actions constrained to uniform standard methods over clean resource models.

---

## 1. Greenfield vs. Brownfield Precedence

**Predictability across the whole API overrides textbook purity on a single endpoint.**

- **Brownfield (existing API/repo):** Match the codebase's established *surface conventions* (`snake_case` vs. `camelCase`, UUID vs. Base32 IDs, auth headers, error envelope, URL version prefix) unless the user asks for a v2 redesign. **Always** enforce *behavioral and safety invariants* (atomic batches, cursor termination, dry-run purge, no covert side effects on `GET`/`PATCH`, string decimals/money, non-retriable `4xx` rules).
- **Greenfield (new API or v2 redesign):** Apply all book conventions by default.

---

## 2. Selective Progressive Disclosure (Load Only What You Need)

Read **only** the 1–2 reference files relevant to the current task—never load all 5 for a narrow endpoint change:

| Task / Topic | Reference File | Chapters |
| :--- | :--- | :--- |
| Naming, units, hierarchy depth, inline vs. resource, `null` vs. omitted, booleans, numbers/money, UTF-8 NFC, enums, lists/maps | [01-design-principles.md](./references/01-design-principles.md) | Ch 3–5 |
| Base32/checksum IDs, `Create`/`Get`/`List`/`Update`/`Delete`/`Replace`, `FieldMask`, `:customMethod`, LRO `Operation`, `Job`/`Execution`, ETag/If-Match | [02-fundamentals.md](./references/02-fundamentals.md) | Ch 6–11 |
| Singleton sub-resources, cross-references (`*Id`), M:N `Membership` vs. `:add`/`:remove`, polymorphic `type` resources | [03-resource-relationships.md](./references/03-resource-relationships.md) | Ch 12–16 |
| `:copy`/`:move`, atomic `:batch*`, dry-run `:purge`, `:write` telemetry, cursor pagination (`maxPageSize`/`pageToken`/`:read`), `filter` DSL, `orderBy`, `:import`/`:export` | [04-collective-operations.md](./references/04-collective-operations.md) | Ch 17–23 |
| Compatibility & versioning, soft deletion (`deleted`/`expireTime`/`:undelete`/`:expunge`), `requestId` deduplication, `validateOnly`, `@rev`, backoff+jitter retries, request signing | [05-safety-and-security.md](./references/05-safety-and-security.md) | Ch 24–30 |

---

## 3. HTTP Wire-Binding Rules (Pseudo-TS → Real HTTP)

Book listings use abstract request interfaces (`UpdateReq { resource, fieldMask }`). On the HTTP wire:

| Operation | HTTP Verb & URL | Query Parameters | JSON Body |
| :--- | :--- | :--- | :--- |
| **Get** | `GET /v1/chatRooms/{id}` | `?fieldMask=a&fieldMask=b` | *(none)* |
| **List** | `GET /v1/chatRooms` | `?maxPageSize=50&pageToken=...&filter=...&includeDeleted=true` | *(none)* |
| **Create** | `POST /v1/chatRooms` | `?validateOnly=true` *(or header `Idempotency-Key`)* | Resource JSON |
| **Update** | `PATCH /v1/chatRooms/{id}` | `?fieldMask=title&fieldMask=settings.theme` | **Bare partial resource** (`{"title":"New"}`) |
| **Delete** | `DELETE /v1/chatRooms/{id}` | *(none)* | *(none)* |
| **Custom / Batch** | `POST /v1/chatRooms/{id}:send` or `POST /v1/chatRooms:batchUpdate` | *(read-only `:wait`/`:read`/`:batchGet` use `GET`)* | Action payload (`{ destinationParent }`, `{ requests, fieldMask }`) |

```http
❌ BAD: PATCH /v1/chatRooms/1   { "resource": { "title": "New" }, "fieldMask": ["title"] }
✅ GOOD: PATCH /v1/chatRooms/1?fieldMask=title   { "title": "New" }
```

---

## 4. Non-Obvious Book Guardrails

- **Standard `DELETE` is NOT idempotent:** `204`/`200` on first delete, `404` on repeat (hard delete) or `412 Precondition Failed` (soft delete returning the updated resource).
- **No covert side effects:** Never send emails or trigger jobs via `PATCH { status: "sent" }`; use `POST /emails/{id}:send`.
- **Pagination stops ONLY on empty `nextPageToken`:** Use `maxPageSize` (upper bound, never `pageSize`). Keep paging even if `results` is `[]` while `nextPageToken` is present.
- **No precision-unsafe JSON numbers:** Serialize 64-bit IDs/ints and money/decimals as **strings** (or `{ currencyCode, units, nanos }`).
- **Open strings over closed enums:** Document allowed string values and validate server-side instead of rigid schema enums.
- **Atomic lists; no index addressing:** Never support `items[0]` in `FieldMask` or `filter`.
- **100% atomic `:batch*`:** All items succeed or roll back together in exact input order; use an LRO or `:import` for partial-failure jobs.
- **Safe `:purge`:** `force` defaults to `false` (dry-run preview returning `purgeCount` + `purgeSample`).

---

## 5. Workflows, Output Contracts & Tooling

### Design Deliverable
When designing an API from requirements:
1. State **Greenfield vs. Brownfield** assumptions and target resource hierarchy (≤ 2–3 levels).
2. Output concrete **endpoints table** (HTTP verb, path, request/response schemas, key status codes) + TypeScript/OpenAPI definitions.
3. Explicitly note applied safety patterns (`requestId`/`Idempotency-Key`, pagination, soft delete, LROs).

### Audit / Review Deliverable
When reviewing a spec or route code:
1. Run `lint-openapi` (below) first if an OpenAPI JSON/YAML file is present.
2. Group findings by severity: **`[CRITICAL]`** (data loss/security/breaking) → **`[MAJOR]`** (structural/operational defects) → **`[MINOR]`** (naming/polish).
3. For every finding include: **Pattern & Chapter**, **`❌ Current` → `✅ Recommended Fix`**, and **Failure Mode**.

### Executable Helper (`scripts/api_patterns_tool.py`)
Use [api_patterns_tool.py](./scripts/api_patterns_tool.py) instead of computing Base32 checksums manually or auditing large OpenAPI files purely by eye:
```bash
# Generate / verify Ch 6 Crockford Base32 + Base37 checksum IDs
python3 scripts/api_patterns_tool.py id-gen --prefix books --bytes 8 --count 3
python3 scripts/api_patterns_tool.py id-verify "books/ahm6-a83h-enmp~"

# Run automated OpenAPI anti-pattern checks (JSON, or YAML if PyYAML installed)
python3 scripts/api_patterns_tool.py lint-openapi path/to/openapi.json
```
