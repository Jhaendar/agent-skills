---
name: api-design-patterns
description: >-
  Design, review, refactor, and audit resource-oriented web APIs (REST/HTTP,
  JSON, OpenAPI, gRPC/HTTP transcoding) using the patterns and rules from JJ
  Geewax's API Design Patterns. Use whenever the user designs API endpoints,
  schemas, resource hierarchies, naming, identifiers, standard or custom
  methods, field masks, long-running operations, rerunnable jobs, resource
  relationships, batch operations, pagination, filtering, import/export,
  versioning, soft deletion, request deduplication, dry-run validation,
  revisions, retries, or request authentication.
---

# API Design Patterns

Resource-oriented architectural blueprint distilled from JJ Geewax's *API Design Patterns* (Manning), with clearly labeled industry supplements where modern standards extend the book.

## Core Philosophy (Part 1, Ch 1–2)

A good web API is **Operational** (actually solves the user's goal reliably), **Expressive** (clearly communicates intent), **Simple** (minimal surface area and cognitive load), and **Predictable** (consistent rules across every endpoint so users can transfer knowledge).

**Resource-Oriented Architecture:** Model the system around a focused set of **resources** (nouns) manipulated primarily through a small, uniform set of **standard methods** (`Create`, `Get`, `List`, `Update`, `Delete`, and optionally `Replace`). Reach for **custom methods** (`POST /resources/123:action`) only when an operation has side effects or semantics that cannot fit a standard method cleanly. Favor global predictability over clever, one-off endpoint optimizations.

---

## Agent Workflows

### 1. Designing a New API
1. **Model Resources & Hierarchy** — Identify core nouns, decide what is a standalone resource vs. an inline data type, and keep parent-child nesting shallow (≤ 2–3 levels, only for true ownership/cascading ACLs & deletes). Read [01-design-principles.md](./references/01-design-principles.md) and [03-resource-relationships.md](./references/03-resource-relationships.md).
2. **Name Fields & Choose Data Types** — Apply consistent casing, imperative verbs, positive booleans, explicit units on primitives, string-serialized 64-bit ints/decimals, open strings over rigid enums, and bounded atomic lists/maps. Read [01-design-principles.md](./references/01-design-principles.md).
3. **Design Identifiers & Standard Methods** — Use hierarchical resource names (`parents/abc/children/xyz`), Crockford Base32 + Base37 checksum IDs, standard HTTP verbs, `FieldMask`, and `:customAction` methods for side effects or async LROs/jobs. Read [02-fundamentals.md](./references/02-fundamentals.md).
4. **Add Collective Operations** — Add cursor pagination (`maxPageSize` / `pageToken`), hermetic `filter` strings, atomic `Batch*`, `:copy`/`:move`, dry-run `:purge`, `:write`, or `:import`/`:export` where needed. Read [04-collective-operations.md](./references/04-collective-operations.md).
5. **Harden Safety & Security** — Define versioning/compatibility policy, soft deletion (`deleted` + `expireTime` + `:undelete`/`:expunge`), `requestId` deduplication, `validateOnly` dry-runs, revisions (`@rev`), exponential-backoff + jitter retries, and request auth. Read [05-safety-and-security.md](./references/05-safety-and-security.md).

### 2. Reviewing / Auditing an Existing API
When asked to review an OpenAPI spec, router, TypeScript/Proto schema, or endpoint list:
1. Load the relevant reference file(s) from the routing table below.
2. Audit top-down and report findings grouped by severity:
   - **Safety & Compatibility Risks** (non-atomic batches, missing `requestId` on retries, unsafe `purge`, breaking enum/default changes, covert side effects on `PATCH`/`GET`).
   - **Structural & Hierarchy Smells** (deep nesting > 3 levels, resources-for-everything, unbounded inline arrays, missing association resources vs. leaky `add`/`remove`, singleton sub-resource mistakes).
   - **Naming & Type Pitfalls** (prepositions in resource/method names, missing units on numbers, floats for money, rigid schema enums, negative booleans, sequential numeric IDs).
   - **Operational Gaps** (offset pagination vs. opaque tokens, stopping on empty `results` instead of empty `nextPageToken`, missing `FieldMask`, missing `Operation<ResultT, MetadataT>` on slow calls).
3. Provide concrete before/after interface or HTTP definitions for each finding.

---

## High-Signal Book Rules (Quick Audit Checklist)

- **Standard `DELETE` is NOT idempotent:** First call deletes (`200`/`204`), second returns `404 Not Found` (hard delete) or `412 Precondition Failed` (soft delete). Distinguish *this request deleted it* from *it is absent*.
- **No covert side effects on standard methods:** Never trigger emails, deployments, or state-machine transitions via `PATCH` (`{ status: "sent" }`). Use a `POST` custom method (`POST /emails/123:send`).
- **Custom methods use `POST` + colon syntax (`:verb`), never `PATCH`:** Only use `GET` for strictly read-only, safe, idempotent custom actions (e.g., `:wait`, `:read`, `:listRevisions`).
- **IDs are hierarchical strings with checksums:** `id` holds the relative resource path (`"chatRooms/ahm6a83henmp~/messages/..."`), encoded in Crockford Base32 + Base37 checksum char so `400` (bad checksum) is distinguishable from `404` (missing).
- **Pagination stops on empty `nextPageToken`, NOT empty `results`:** Use `maxPageSize` (never `pageSize`), treat `results: []` + non-empty `nextPageToken` as "keep paging", and keep `pageToken` opaque.
- **No floating-point or >53-bit integers in JSON numbers:** Serialize 64-bit IDs/integers and fixed-point decimals/money as **strings** (or structured currency objects).
- **Prefer documented strings over schema enums:** Closed enums break existing clients when servers add new values.
- **Lists are atomic; no array-index addressing:** Never support `items[0]` in `FieldMask` or `filter` strings. Use `*` only for field projection (`administrators.*.name`) on `GET`, and replace lists atomically (or promote to a sub-collection / map).
- **Batch operations (`:batchCreate`, `:batchGet`, `:batchUpdate`, `:batchDelete`) are 100% atomic:** All succeed or all fail, returning results in exact request order. For partial failures, use LROs or `:import`/`:export`.
- **Criteria-based `:purge` defaults to dry-run (`force: false`):** Never execute bulk criteria deletion unless `force: true` is explicitly passed; always return `purgeCount` and `purgeSample`.
- **Cross-references (`*Id`) do not require strict DB referential integrity by default:** Prefer `*Id` string fields over unbounded inline arrays, and accept dangling references unless business integrity strictly requires blocking deletion.

---

## Pattern Routing Table

Read the matching reference file(s) before finalizing designs or code reviews:

| If the task involves... | Read | Chapters |
| :--- | :--- | :--- |
| Naming, casing, grammar, prepositions, units, resource scope vs. inline data types, hierarchy depth, `null` vs. omitted, booleans, numbers/floats, UTF-8 NFC strings, enums, lists, maps | [01-design-principles.md](./references/01-design-principles.md) | Ch 3–5 |
| Resource IDs, Crockford Base32, checksums, UUIDs, tombstoning, `Create`/`Get`/`List`/`Update`/`Delete`/`Replace`, `FieldMask`, custom `:methods`, LROs (`Operation`), rerunnable `Job`/`Execution` | [02-fundamentals.md](./references/02-fundamentals.md) | Ch 6–11 |
| Singleton sub-resources (`/location`), cross-references (`authorId`), many-to-many association resources (`Membership`), `:add`/`:remove` custom methods, polymorphic resources (`type` discriminator) | [03-resource-relationships.md](./references/03-resource-relationships.md) | Ch 12–16 |
| `:copy` & `:move`, atomic `:batch*` operations, `:purge` (criteria deletion), anonymous `:write` telemetry, cursor pagination (`maxPageSize` / `pageToken` / `:read`), `filter` string DSL, `:import` & `:export` | [04-collective-operations.md](./references/04-collective-operations.md) | Ch 17–23 |
| Backward compatibility, versioning strategies, soft delete (`deleted`, `expireTime`, `:undelete`, `:expunge`), `requestId` deduplication, `validateOnly` dry-runs, `@revision` snapshots, retries + backoff/jitter, HTTP request signing | [05-safety-and-security.md](./references/05-safety-and-security.md) | Ch 24–30 |
