# Part 3: Fundamentals (Chapters 6–11)

Covers resource identification, standard methods, field masks, custom methods, long-running operations, and rerunnable jobs.

---

## Chapter 6: Resource Identification

### 7 Traits of a Good Identifier
Easy to use · Unique · Permanent (never reused, even after deletion) · Fast/easy to generate · Unpredictable (non-sequential to prevent enumeration/scraping) · Readable, shareable, and verifiable (checksummed) · Informationally dense.

### Recommended Format: Hierarchical String + Crockford Base32 + Base37 Checksum
1. **Data type & Charset:** `string` using **ASCII** (never raw Unicode).
2. **Crockford's Base32:** Alphabet `0123456789ABCDEFGHJKMNPQRSTVWXYZ` (32 chars = 5 bits/char; excludes `I`, `L`, `O`, `U` to prevent `1`/`0` confusion and English profanity). Decoding is case-insensitive, accepts `i`/`l` as `1` and `o` as `0`, and ignores optional hyphens (`books/ahm6-a83h-enmp~`).
3. **1-Char Base37 Checksum:** Compute `BigInt(bytes) % 37n` and encode with Base32 + 5 extra chars (`*`, `~`, `$`, `=`, `U`, alphabet: `0123456789ABCDEFGHJKMNPQRSTVWXYZ*~$=U`).
   - **Why:** Distinguishes `400 Bad Request` (invalid checksum — ID could never exist, e.g., user typo) from `404 Not Found` (valid checksum — deleted or never created).
   - Store only raw bytes / integer / Base32 core in the DB; **compute and strip the checksum dynamically** at the API boundary.
4. **Sizing:**
   - Per-resource-type uniqueness: 60 bits (12 Base32 chars) + 1 checksum = **13 chars**.
   - Global uniqueness (or UUID v4 encoded in Crockford Base32): 120–128 bits (24–26 Base32 chars) + 1 checksum = **25–27 chars** (more compact and shareable than 36-char hex UUIDs).
5. **Resource Type & Hierarchy in `id`:**
   - Prefix with plural collection path: `"books/ahm6a83henmp~"` or `"books/1234/pages/5678"`.
   - Child IDs only need uniqueness within their parent (`books/1/pages/2` and `books/9/pages/2` are distinct full IDs).
   - Only nest when ownership is permanent (pages never move books; books *do* move shelves, so use `shelfId`, not `shelves/1/books/1`).
6. **Server-Generated & Tombstoned:** Never let users invent random IDs unless strictly necessary (causes PII leaks in IDs and collision confusion). Never reuse deleted IDs—keep tombstones (via soft delete, ID table, or Bloom filter) or use ≥ 120-bit CSPRNG IDs.

---

## Chapter 7: Standard Methods

Every resource uses the same predictable verbs, paths, and semantics:

| Method | HTTP & Path | Request | Response | Idempotent? | Side Effects? |
| :--- | :--- | :--- | :--- | :---: | :---: |
| **Create** | `POST /chatRooms` or `POST /{parent=chatRooms/*}/messages` | `{ parent?, resource }` | `Resource` (`201`/`200`) | No (use `requestId` for retries) | Forbidden |
| **Get** | `GET /{id=chatRooms/*}` | `{ id }` | `Resource` (`200`, or `404`) | Yes (safe) | Forbidden |
| **List** | `GET /chatRooms` or `GET /{parent=chatRooms/*}/messages` | `{ parent?, maxPageSize?, pageToken?, filter? }` | `{ results: Resource[], nextPageToken }` | Yes (safe) | Forbidden |
| **Update** | `PATCH /{resource.id=chatRooms/*}` | `{ resource, fieldMask? }` | Updated `Resource` | Yes (for direct field sets) | Forbidden |
| **Delete** | `DELETE /{id=chatRooms/*}` | `{ id }` | `void` (`204`/`200`, **`404` on repeat**) | **NO** | Forbidden |
| **Replace** *(semi-standard)* | `PUT /{resource.id=chatRooms/*}` | `{ resource }` | `Resource` | Yes | Forbidden |

### Key Standard Method Rules
- **Standard `Delete` is intentionally NOT idempotent:** First call removes the resource (`204`/`200`); subsequent calls return `404 Not Found` (or `412` when soft-deleted). Callers must know whether *their* request performed the deletion vs. the resource was already gone.
- **No covert side effects:** Modifying `email.state` via `PATCH` to send an email is a bug. Standard methods mutate only the target resource (and its documented internal timestamps/cascades).
- **Prefer `PATCH` (+ `FieldMask`) over `PUT` (`Replace`):** `PUT` overwrites omitted fields to defaults/nulls, causing silent data loss when older clients round-trip a resource with newer server fields.
- **List access control:** Either filter out unauthorized items or return `403` if the caller lacks collection-level permission (be consistent and document which).

---

## Chapter 8: Partial Updates and Retrievals (`FieldMask`)

```ts
type FieldMask = string[];
interface GetChatRoomRequest { id: string; fieldMask?: FieldMask; }
interface UpdateChatRoomRequest { resource: ChatRoom; fieldMask?: FieldMask; }
```

### Transport
- Use **repeated query parameters** on both `GET` and `PATCH`:
  `GET /chatRooms/1?fieldMask=title&fieldMask=loggingConfig.maxSizeMb`
  `PATCH /chatRooms/1?fieldMask=title` with body `{ "title": "New" }` (never wrap `{ resource, fieldMask }` in the `PATCH` body—the `PATCH` body must remain the resource itself).

### Path Syntax Rules
1. Dot `.` separates nested fields: `"loggingConfig.maxSizeMb"`.
2. Wildcard `*` selects all fields of a resource/nested object (`"*"`, `"loggingConfig.*"`) or projects fields across every item of a repeated field (`"administrators.*.name"` — **allowed on `GET` only, never `PATCH`**).
3. Map keys that aren't plain identifiers (numbers, dots, `*`, spaces, backticks) are quoted in backticks: ``"settings.`1234`"``, ``"settings.`test.value`"``, ``"settings.`*`"``.
4. Escape literal backticks by doubling them: ``"settings.```hello```"`` for key ``"`hello`"``.
5. **Never support array-index addressing** (`items[0]`): concurrent inserts/reorders make index targeting unsafe.

### Defaults, Clearing Dynamic Keys, and Unknown Fields
- **`GET` default (unset `fieldMask`):** Return all fields (except explicitly documented heavyweight/expensive fields that require opt-in via `*` or explicit name).
- **`PATCH` default (unset `fieldMask`) — Implicit Field Mask:** Infer the mask recursively from every present non-`undefined` key in the JSON body:
  - Missing key → untouched.
  - Explicit `null` → sets field to `null`.
- **Removing a key from a dynamic map (`undefined` in JSON):** Since JSON cannot represent `undefined`, pass an **explicit `fieldMask`** naming the key while **omitting that key** from the `PATCH` body:
  `PATCH /chatRooms/1?fieldMask=settings.test` with `{}` → deletes `settings["test"]`.
- **Unknown/invalid fields in `fieldMask`:** Treat as `undefined` (do not throw errors), preserving forward/backward compatibility as fields are added or removed.

---

## Chapter 9: Custom Methods

Use when an operation has side effects or does not fit CRUD (`send`, `archive`, `validate`, `export`, `cancel`).

```ts
@post("/{id=users/*/emails/*}:send")
SendEmail(req: SendEmailRequest): Email;

@post("/{parent=users/*}/emails:export")
ExportEmails(req: ExportEmailsRequest): Operation<ExportEmailsResponse, ExportEmailsMetadata>;

@post("/emailAddress:validate")          // Stateless top-level custom method
ValidateEmailAddress(req: ValidateEmailAddressRequest): ValidateEmailAddressResponse;
```

- **Syntax:** Colon `:` separates target resource/collection from imperative verb (`:send`, `:archive`).
- **HTTP Verb:** Almost always **`POST`**. **Never `PATCH`** (and avoid `PUT`/`DELETE` except `:deleteRevision` when modeling revision sub-operations). Use **`GET` only** when the custom method is strictly read-only, safe, and idempotent (e.g., `:wait`, `:read`, `:listRevisions`).
- **Scope:** Target the individual resource (`/{id=...}:send`) for single-item actions, the collection (`/{parent=...}/emails:export`) for multi-item actions, or top-level (`/emailAddress:validate`) for stateless computations.

---

## Chapter 10: Long-Running Operations (LROs)

Async operations act as **API promises/futures** when work takes longer than a few hundred milliseconds.

```ts
interface Operation<ResultT, MetadataT> {
  id: string;                            // e.g., "operations/abc123~" or "chatRooms/1/operations/abc123~"
  done: boolean;
  expireTime: Date;                      // Persisted, e.g., 30 days TTL
  result?: ResultT | OperationError;     // Populated when done === true
  metadata?: MetadataT;                  // Progress info (e.g., percentComplete, paused)
}
interface OperationError { code: string; message: string; details?: any; }
```

### Standard LRO Endpoints
- Triggering method returns `Operation<ResultT, MetadataT>` (`done: false`): e.g. `POST /{parent=chatRooms/*}/messages:analyze`
- `GET /{id=operations/*}` — Poll status (`GetOperation`).
- `GET /operations` — List operations with `filter` (`ListOperations`).
- `GET /{id=operations/*}:wait` — Long-poll / blocking wait until completion or server timeout (`WaitOperation`).
- `POST /{id=operations/*}:cancel` · `:pause` · `:resume` — Optional lifecycle controls.

### Key Rules
- **Error distinction:** If `GetOperation` itself succeeds for a *failed* background job, return HTTP `200 OK` with `done: true` and `result: OperationError`. Return HTTP `4xx`/`5xx` only if the `GetOperation` request itself fails (e.g., `404` unknown operation).
- **Persistence:** Persist operations in durable storage with an `expireTime` (e.g., 30 days) so clients can inspect outcomes long after completion.

---

## Chapter 11: Rerunnable Jobs

When a background task needs **saved configuration**, **repeated runs**, **separation of permissions** (admins configure the job, operators trigger `:run`), or a **queryable execution history**, model a `Job` resource + `:run` + read-only `Execution` child resources instead of a raw LRO custom method:

```ts
// 1. Configure job (Create / Get / List / Update / Delete)
@post("/analyzeChatRoomJobs")
CreateAnalyzeChatRoomJob(req: CreateAnalyzeChatRoomJobRequest): AnalyzeChatRoomJob;

// 2. Trigger run -> returns LRO resolving to an Execution resource
@post("/{id=analyzeChatRoomJobs/*}:run")
RunAnalyzeChatRoomJob(req: RunAnalyzeChatRoomJobRequest):
  Operation<AnalyzeChatRoomJobExecution, RunAnalyzeChatRoomJobMetadata>;

// 3. Inspect past outputs (read-only: Get, List, optional Delete — never Create/Update)
@get("/{parent=analyzeChatRoomJobs/*}/executions")
ListAnalyzeChatRoomJobExecutions(req: ListExecutionsRequest): ListExecutionsResponse;
@get("/{id=analyzeChatRoomJobs/*/executions/*}")
GetAnalyzeChatRoomExecution(req: GetExecutionRequest): AnalyzeChatRoomJobExecution;
```

---

## Industry Supplements (>90% Confidence)

- **HTTP Status Codes (RFC 9110):** Use `201 Created` (with `Location` header) or `200 OK` on `Create`; `202 Accepted` when returning an asynchronous `Operation`; `204 No Content` on `void` `Delete`.
- **Standard Error Envelope (RFC 9457 / Google AIP-193):** Return structured JSON errors (`{ error: { code, message, details } }` or RFC 9457 `application/problem+json` with `type`, `title`, `status`, `detail`) consistently across `4xx`/`5xx` and `OperationError`.
