# Part 5: Collective Operations (Chapters 17–23)

Covers copy/move, batch operations, criteria-based deletion, anonymous writes, pagination, filtering, and import/export.

---

## Chapter 17: Copy and Move

Never emulate copy/move via client-side `Create` + `Delete` or `PATCH parent` (breaks permanence, atomicity, child resources, and internal blobs). Use dedicated custom methods:

```ts
@post("/{id=chatRooms/*}:copy")
CopyChatRoom(req: { id: string; destinationParent: string }): ChatRoom; // or Operation<...>

@post("/{id=chatRooms/*/messages/*}:move")
MoveMessage(req: { id: string; destinationParent: string }): Message;
```

### Design Checklist
- **Child resources:** Document whether copying/moving a parent recursively copies/moves children (usually yes).
- **Identifiers:** `:copy` must mint **fresh IDs** (unless user-specified IDs are supported); `:move` changes the hierarchical path/ID—decide explicitly whether old IDs return `404` or `301`/`410` redirects.
- **External data:** Clarify copy-by-value (independent clone) vs. copy-by-reference (shared underlying blob).
- **Inherited metadata & ACLs:** Decide whether destination parent's ACLs/policies override or merge with the source's.
- **Atomicity:** Make `:copy` and `:move` atomic (or return an `Operation<Resource, Metadata>` LRO if large/cross-shard).

---

## Chapter 18: Batch Operations

Bulk standard methods operating atomically in a single HTTP round-trip:

```http
GET /v1/chatRooms:batchGet?ids=chatRooms/a&ids=chatRooms/b
GET /v1/chatRooms/-/messages:batchGet?ids=chatRooms/1/messages/x&ids=chatRooms/2/messages/y

POST /v1/chatRooms:batchDelete
{ "ids": ["chatRooms/a", "chatRooms/b"] }
```

```ts
@post("/chatRooms:batchCreate")
BatchCreateChatRooms(req: { requests: CreateChatRoomRequest[] }): { resources: ChatRoom[] };

@get("/chatRooms:batchGet")
BatchGetChatRooms(req: { ids: string[] }): { resources: ChatRoom[] };

@post("/chatRooms:batchUpdate")
BatchUpdateChatRooms(req: {
  parent?: string;
  requests: UpdateChatRoomRequest[];
  fieldMask?: FieldMask; // Hoisted common field mask
}): { resources: ChatRoom[] };

@post("/chatRooms:batchDelete")
BatchDeleteChatRooms(req: { parent?: string; ids: string[] }): void;
```

### Strict Rules
- **HTTP Verbs:** `batchGet` uses `GET` (if many IDs risk exceeding URL length limits in practice, a `POST ...:batchGet` fallback may be needed, though the book prescribes `GET`). `batchCreate`, `batchUpdate`, and `batchDelete` all use **`POST`** (never `PATCH` or `DELETE`!).
- **100% Atomicity:** All items in the batch succeed, or the entire batch fails and rolls back (single HTTP error). Never return mixed partial-success arrays from `Batch*`—use an LRO or `:import` if partial progress is needed.
- **Exact Ordering:** Output `resources[]` **must match the exact order** of input `requests[]` / `ids[]`.
- **Hoisted Common Fields:** Allow shared fields (`parent`, `fieldMask`) on the outer batch request; if targeting resources across different parents in one call, use a **wildcard hyphen** parent (`chatRooms/-/messages:batchGet`).
- **Bounds:** Enforce a reasonable max batch size (e.g., 100–1,000 items).

---

## Chapter 19: Criteria-Based Deletion (`:purge`)

Avoid if possible; if users must bulk-delete by filter criteria, enforce strict safety guards:

```ts
@post("/{parent=chatRooms/*}/messages:purge")
PurgeMessages(req: {
  parent: string;
  filter: string;
  force?: boolean;       // MUST default to false (dry-run)!
}): {
  purgeCount: number;    // Exact or estimated count of matching resources
  purgeSample: string[]; // Sample of matching resource IDs (e.g., up to 10–100)
};
```

### Rules
- **Dry-run by default (`force: false`):** Calling `:purge` without `force: true` **must NOT delete anything**—it returns estimated `purgeCount` and `purgeSample` IDs so the caller can inspect what would be wiped.
- **Strict filter parsing:** Reject malformed or empty `filter` strings with `400 Bad Request` (prevent accidental full-collection deletion).
- **Consistency:** Adhere to the same consistency guarantees as standard `List`.

---

## Chapter 20: Anonymous Writes (`:write` / `:batchWrite`)

For high-volume, non-addressable data points (telemetry, analytics events, time-series metrics, logs) modeled as `Entry` objects rather than CRUD `Resource`s:

```ts
interface ChatRoomStatEntry { name: string; value: number | string | boolean | null; }

@post("/{parent=chatRooms/*}/statEntries:write")
WriteChatRoomStatEntry(req: { parent: string; entry: ChatRoomStatEntry }): void;

@post("/{parent=chatRooms/*}/statEntries:batchWrite")
BatchWriteChatRoomStatEntry(req: { parent: string; requests: WriteRequest[] }): void;
```

- **One-way street:** Entries have no `id` and cannot be retrieved, updated, or deleted individually.
- **Response:** Returns `void` (`204`/`200` if synchronously accepted, or `202 Accepted` if buffered/queued asynchronously). Expect eventual consistency when querying aggregated results.

---

## Chapter 21: Pagination

### Collection Pagination
```ts
interface ListChatRoomsRequest { maxPageSize?: number; pageToken?: string; }
interface ListChatRoomsResponse { results: ChatRoom[]; nextPageToken?: string; }
```
1. **Name it `maxPageSize`, never `pageSize`:** It is an **upper bound**, not an exact count. The server may return fewer items (even `0` items) per page due to filtering, permissions, or byte/time budgets. Apply a sensible server default when omitted and clamp excessive values.
2. **Termination Condition:** Stop paging **ONLY when `nextPageToken` is empty, `null`, or omitted**. **NEVER** stop because `results.length === 0` or `results.length < maxPageSize`!
```ts
// ❌ BAD: Drops remaining pages whenever filtering/auth leaves a partial or empty page
do { page = await list({ maxPageSize: 50, pageToken }); } while (page.results.length === 50);

// ✅ GOOD: Keep paging until nextPageToken is absent/empty
let pageToken: string | undefined;
do {
  const page = await list({ maxPageSize: 50, pageToken });
  all.push(...page.results);
  pageToken = page.nextPageToken || undefined;
} while (pageToken);
```
3. **Opaque Cursor `pageToken`:** Encode/encrypt cursor state (e.g., Base64 opaque token)—never expose raw SQL `OFFSET`/`LIMIT` or internal row IDs directly.
4. **Avoid exact `totalCount`:** Computing exact totals on huge/filtered sets hurts scalability; omit it or document it as an estimate only if needed.

### Intra-Resource Pagination (`:read`)
For streaming/paging slices of a single huge resource (attachments, blobs):
```ts
@get("/{id=chatRooms/*/messages/*/attachments/*}:read")
ReadAttachment(req: { id: string; pageToken?: string; maxBytes?: number }):
  { chunk: Attachment; fieldMask: FieldMask; nextPageToken?: string };
```

---

## Chapter 22: Filtering

```ts
interface ListChatRoomsRequest { filter?: string; maxPageSize?: number; pageToken?: string; }
```

- **Always use a `filter: string` DSL** (SQL `WHERE` / Google AIP-160 / CEL style: `(title = "General" AND userLimit >= 5) OR archived = false`), **never a nested JSON filter object** (`{ $or: [...] }`) which bloats schemas and locks clients into rigid structures.
- **Hermetic single-resource evaluation:** A filter may inspect **only** the candidate resource itself (`evaluate(filter, resource): boolean`). **Forbid** cross-resource joins, remote lookups, or aggregations (no dereferencing `administrator.name` if `administratorId` is just a foreign ID).
- **No array-index filtering:** Forbid `tags[0] = "new"`. Support membership/presence checks (`"new" in tags` or `tags: "new"`).
- **Strict error reporting:** Return `400 Bad Request` on typos, unknown field names, or type mismatches (`userCount = "abc"`)—never silently coerce types or return empty `results: []`.
- **Custom functions for advanced matching:** Instead of overloading operators with wildcards, expose explicit documented functions (`endsWith(title, "(new)")`, `substring(...)`).

---

## Chapter 23: Importing and Exporting

Moving data between an API and external storage (S3, GCS, Samba)—**not** a transactional backup/restore mechanism.

```ts
@post("/{parent=chatRooms/*}/messages:export")
ExportMessages(req: {
  parent: string;
  outputConfig: MessageOutputConfig;     // Format: contentType ("json"|"csv"), compressionFormat, maxFileSizeMb, filenameTemplate
  dataDestination: DataDestination;      // Transport: { type: "s3", bucketId, objectPrefix }
  filter?: string;
  fieldMask?: FieldMask;
}): Operation<ExportMessagesResponse, ExportMessagesMetadata>;

@post("/{parent=chatRooms/*}/messages:import")
ImportMessages(req: {
  parent: string;
  inputConfig: MessageInputConfig;
  dataSource: DataSource;
}): Operation<ImportMessagesResponse, ImportMessagesMetadata>;
```

- **Orthogonal configs:** Separate *where bytes live* (`DataSource`/`DataDestination`) from *how bytes convert to resources* (`InputConfig`/`OutputConfig`).
- **Scope & Consistency:** Limit each `:import`/`:export` to a **single resource type**, return an LRO, clarify whether exports are point-in-time snapshots or subject to concurrent edits, and document ID collision handling on import (default: generate fresh IDs on import rather than trusting external IDs).

---

## Industry Supplement (>90% Confidence)

- **Sorting (`orderBy: string`):** When `List` supports custom sort orders, use a comma-separated string field (`orderBy="createTime desc, priority asc"`, matching Google AIP-132), validate field names strictly (`400 Bad Request` on unknown fields), append a deterministic tie-breaker (`id asc`), and bind `(filter, orderBy)` into the `pageToken` (rejecting mismatched reuse across pages).
