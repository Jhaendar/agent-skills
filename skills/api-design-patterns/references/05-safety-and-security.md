# Part 6: Safety and Security (Chapters 24–30)

Covers versioning/compatibility, soft deletion, deduplication, dry-run validation, revisions, retries, and request authentication.

---

## Chapter 24: Versioning and Compatibility

### What Counts as Backward Compatible?
Backward compatibility is **behavioral, not just syntactic**:
- **Clearly Breaking:** Removing/renaming endpoints or fields; changing field types; tightening validation (turning a previously succeeding call into `400`); changing default values; changing ordering/semantics clients rely on; adding new enum values to closed client-side enums; introducing required child resources that block parent deletion; catastrophic latency regressions (100 ms → 10 s).
- **Usually Safe (when documented):** Adding new independent resources/endpoints; adding optional request fields with existing-behavior defaults; fixing `500 Internal Server Error` crashes; adding new response fields (if clients ignore unknown fields and memory isn't severely constrained).
- **Gray Area (decide upfront in policy):** Fixing subtle math bugs (e.g., `0.1 + 0.2` returning `0.30000000000000004` → `0.3`), upgrading ML models, or regulatory mandates (GDPR).

### Three Versioning Strategies
| Strategy | How It Works | Best For | Trade-off |
| :--- | :--- | :--- | :--- |
| **Perpetual Stability** | Keep `v1` forever for compatible changes; introduce `v2` only on breaking changes. | Public cloud / broad ecosystems (GCP style). | Older versions accumulate; strict IoT clients dislike any drift inside `v1`. |
| **Agile Instability** | Sliding window: 1 **Preview** (`v2`), 1 **Current** (`v1`), N **Deprecated** (fixed sunset clock) → **Deleted**. | Fast-moving APIs with engaged developers. | Client code eventually breaks unless actively upgraded. |
| **Semantic Versioning** | `MAJOR.MINOR.PATCH` (`v1.2.0` — breaking / compat feature / compat bugfix). | Libraries & version-pinned enterprise clients. | Server must host/route many frozen versions simultaneously. |

*(Industry supplement >90%: For web APIs, expose only the **major version or channel** in the URL path `/v1/...` or `/v1beta/...` rather than `MAJOR.MINOR.PATCH` in URLs to avoid route fragmentation.)*

---

## Chapter 25: Soft Deletion

Recycle-bin semantics using an **output-only** boolean flag plus expiration timestamp:

```ts
interface ChatRoom {
  id: string;
  // ...
  deleted: boolean;     // Output-only; defaults to false
  expireTime: Date;     // Set on Delete; reset to null on :undelete
}
```

### Exact Method Semantics
| Operation | HTTP / Signature | Behavior |
| :--- | :--- | :--- |
| **Get** | `GET /{id=chatRooms/*}` | **Still returns the soft-deleted resource** (caller has the ID and needs to see `deleted: true` / `expireTime`). |
| **List** | `GET /chatRooms` | **Excludes** soft-deleted resources by default. Add `includeDeleted?: boolean` on `ListRequest` (applied *before* `filter`, e.g. `includeDeleted=true&filter=deleted: true`). |
| **Update** | `PATCH /{resource.id=chatRooms/*}` | `deleted` is **output-only**—manual attempts to set `deleted` in `PATCH` are ignored without error. |
| **Delete** | `DELETE /{id=chatRooms/*}` | Sets `deleted = true`, sets `expireTime` (e.g., now + 30d), and **returns the modified `Resource`** (not `void`!). Calling `Delete` on an already soft-deleted resource returns **`412 Precondition Failed`**. |
| **Undelete** | `POST /{id=chatRooms/*}:undelete` | Sets `deleted = false`, clears `expireTime = null`, returns `Resource`. Calling `:undelete` on a non-deleted resource returns **`412 Precondition Failed`**. |
| **Expunge** | `POST /{id=chatRooms/*}:expunge` | Permanently deletes and returns `void`. Allowed on **any** resource (whether soft-deleted or active). |

- **Referential Integrity & Batch:** Keep the same referential integrity policy as hard delete. `BatchDelete` inherits soft-delete behavior; expose `BatchExpunge` if bulk permanent deletion is needed.
- **Versioning warning:** Switching an existing API from hard delete to soft delete alters `Delete` behavior and response shape (`void` → `Resource`)—treat as breaking unless explicitly planned.

---

## Chapter 26: Request Deduplication

Make non-idempotent mutations (`Create`, custom methods, `Batch*`) safe to retry over unreliable networks:

```ts
interface CreateChatRoomRequest {
  resource: ChatRoom;
  requestId?: string; // Client-generated UUID/token unique per logical intent
}
```

### Server Logic
1. On receiving `requestId`, look up `cache.get(requestId)` (scoped by caller/method, with bounded TTL e.g. 5 min–24 hr).
2. **Cache miss:** Execute operation, store `{ requestHash: sha256(canonicalRequest), response }`, return response.
3. **Cache hit + `requestHash` matches:** Return cached `response` immediately without re-executing.
4. **Cache hit + `requestHash` differs:** Return **`409 Conflict`** (catches client bugs reusing a `requestId` for a different payload).

*(Industry supplement >90%: Standard HTTP APIs commonly pass this via an **`Idempotency-Key`** request header instead of or alongside a body `requestId` field—the server-side `{ hash, response }` semantics are identical.)*

---

## Chapter 27: Request Validation (`validateOnly`)

For dangerous, expensive, or side-effecting operations, allow dry-run preflight checks:

```ts
interface CreateChatRoomRequest {
  resource: ChatRoom;
  validateOnly?: boolean; // Default false
}
```

- When `validateOnly: true`: run full authz, schema, quota, and business-rule checks; **do not persist state** and **do not trigger external side effects** (emails, charges, webhooks).
- If external dependencies cannot guarantee non-execution, mock/skip safely or document any non-deterministic caveats.

---

## Chapter 28: Resource Revisions

Point-in-time immutable snapshots of a resource as it evolves:

```ts
interface Message {
  id: string;                 // Base ID: "chatRooms/1/messages/2"
  revisionId: string;         // Random short ID (NEVER sequential integer or timestamp!)
  revisionCreateTime: Date;
  // ...
}
```

### Endpoints & Rules
- **Address a revision with `@`:** `GET /chatRooms/1/messages/2@a8f9c2` returns that snapshot; omitting `@...` returns the current head.
- **Random `revisionId`:** Never use sequential integers (`1, 2, 3`) or timestamps—random IDs avoid collisions under concurrent edits and prevent enumeration.
- **Creation:** Either **implicit** (every `PATCH` creates a new revision) or **explicit** (`POST /{id=chatRooms/*/messages/*}:createRevision`).
- **List revisions:** `GET /{id=chatRooms/*/messages/*}:listRevisions` (paginated).
- **Restore revision:** `POST /{id=chatRooms/*/messages/*}:restoreRevision` (`{ id, revisionId }`) **creates a new head revision** whose contents equal the target snapshot—**never rewrite or erase history**.
- **Delete revision:** `DELETE /{id=chatRooms/*/messages/*}:deleteRevision` (or `@rev:deleteRevision`; disallow deleting the active head revision).

---

## Chapter 29: Request Retrial

### Retry Eligibility Matrix
| HTTP Status | Retry? | Reason |
| :--- | :---: | :--- |
| `408 Request Timeout`, `429 Too Many Requests` | **Yes** | Transient / rate-limit; honor `Retry-After` header. |
| `502 Bad Gateway`, `503 Service Unavailable`, `504 Gateway Timeout` | **Yes** | Transient upstream/overload failure. |
| `500 Internal Server Error` | **Conditional** | Retry **only** if method is idempotent or carries `requestId` / `Idempotency-Key`. |
| `400`, `401`, `403`, `404`, `409`, `412`, `422` | **NO** | Client error or precondition mismatch; retrying won't fix it. |

### Exponential Backoff + Jitter
- Double delay per attempt (`1s → 2s → 4s → 8s...`), clamped by `maxDelayMs` (e.g., `32s`) and bounded by `maxRetries` (e.g., `10`).
- **Add random jitter** (`delayMs + Math.random() * 1000`) to avoid **thundering/stampeding herds** when a recovering service wakes all waiting clients simultaneously.
- **Honor `Retry-After`:** If the server sends a `Retry-After` header (seconds or HTTP-date), wait at least that duration instead of guessing.

---

## Chapter 30: Request Authentication

Three cryptographic guarantees: **Proof of Origin** (who sent it), **Proof of Integrity** (body/headers un-tampered in transit), and **Non-repudiation** (sender cannot deny sending it).

### Asymmetric HTTP Signature Pattern (Book Flow)
1. **Registration:** Client generates keypair (`RSA-SHA256` or `Ed25519`) and registers `publicKey` on `User` (`POST /users` → returns `userId`).
2. **Digest Header:** Hash exact raw body bytes:
   `Digest: SHA-256=<base64(sha256(body))>`
3. **Canonical Fingerprint:** Join lowercase ordered components with `\n`:
   ```text
   (request-target): patch /chatRooms/1
   host: example.org
   date: Tue, 27 Oct 2020 20:51:35 GMT
   digest: SHA-256=HV9PltG0QPRNsl1FB7ebQA8XPasvPyRg6hhU0QF2l4M=
   ```
4. **Signature Header:** Sign fingerprint with client private key and send metadata:
   `Signature: keyId="1234",algorithm="rsa-sha256",headers="(request-target) host date digest",signature="<base64>"`
5. **Verification:** Server verifies `Digest` matches raw body, checks `Date` freshness window (replay protection), reconstructs fingerprint using the exact `headers` order, fetches `publicKey` by `keyId`, and verifies signature.

### Industry Supplements (>90% Confidence)
- **When to use OAuth 2.0 / OIDC Bearer Tokens + TLS instead:** For standard user-delegated or service-to-service web APIs over HTTPS where transport integrity via TLS suffices and non-repudiation is unnecessary, **OAuth 2.0 / OIDC Bearer tokens** (`Authorization: Bearer <jwt>`) are the standard default. Reserve **asymmetric request signing** (such as **RFC 9421 HTTP Message Signatures**, which standardized the draft pattern in Ch 30) or **mTLS** for high-security financial/webhook/zero-trust payloads requiring end-to-end payload integrity and non-repudiation.
- **Canonical URL/Query Inclusion:** Include query parameters in `(request-target)` (e.g. `get /chatRooms?maxPageSize=10`) and enforce a strict clock-skew window (e.g., ±5 minutes) on `Date` to prevent replay attacks.
