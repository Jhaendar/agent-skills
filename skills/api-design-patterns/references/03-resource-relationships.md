# Part 4: Resource Relationships (Chapters 12–16)

Covers singleton sub-resources, cross-references, many-to-many modeling, and polymorphism.

---

## Relationship Pattern Decision Matrix

| Need | Pattern | Chapter |
| :--- | :--- | :---: |
| Small, bounded data owned 1:1 by parent, fetched/updated together | **Inline Property / Interface** | Ch 4–5 |
| Distinct subset of 1:1 parent data that is huge, hot-updated, or needs separate ACLs | **Singleton Sub-Resource** | Ch 12 |
| 1:1 or 1:N pointer to an independent resource (parent doesn't own lifecycle) | **Cross-Reference (`*Id`)** | Ch 13 |
| M:N relationship **with metadata** (`role`, `joinedAt`, `expireTime`) | **Association Resource** | Ch 14 |
| M:N relationship **without metadata** (simple set membership) | **Add/Remove Custom Methods** | Ch 15 |
| Heterogeneous items listed/stored in one unified collection | **Polymorphic Resource** | Ch 16 |

```ts
// ❌ BAD: Ambiguous bare ID field, unbounded M:N array, wrong singleton verb
interface BookBad { id: string; author: string; }                 // Is `author` an ID or name?
interface GroupBad { id: string; userIds: string[]; }             // Unbounded array; write conflicts
// POST /drivers/123/location                                     // Singletons cannot be Created

// ✅ GOOD: Explicit `*Id` suffix, separate Membership resource, PATCH on singleton
interface BookGood { id: string; authorId: string; }              // "authors/xyz789~"
interface MembershipGood { id: string; groupId: string; userId: string; role: string; }
// PATCH /drivers/123/location  (or POST /drivers/123/location:reset)
```

---

## Chapter 12: Singleton Sub-Resources

A hybrid between a property and a resource: exactly **one** instance exists implicitly per parent, at a fixed singular path.

```ts
// Parent: Driver ("drivers/123") -> Singleton: DriverLocation ("drivers/123/location")
@get("/{id=drivers/*/location}")
GetDriverLocation(req: GetDriverLocationRequest): DriverLocation;

@patch("/{resource.id=drivers/*/location}")
UpdateDriverLocation(req: UpdateDriverLocationRequest): DriverLocation;

// Optional: restore default values
@post("/{id=drivers/*/location}:reset")
ResetDriverLocation(req: ResetDriverLocationRequest): DriverLocation;
```

### Rules & Constraints
- **When to use:** Size isolation (large blob/config shouldn't bloat `GET /drivers/123`), different update cadence/rate limits (high-frequency GPS location updates), or distinct security/ACLs (`users/*/securitySettings`).
- **Allowed methods:** **ONLY `Get`, `Update` (`PATCH`), and optional `:reset`.**
- **Forbidden methods:** **Never** `Create`, `Delete`, or `List`. Lifecycle is bound automatically to the parent.
- **No chained singletons:** A singleton sub-resource must belong to a regular parent resource, never to another singleton.

---

## Chapter 13: Cross References

Pointing from one resource to another without ownership.

```ts
interface Book {
  id: string;        // "books/abc123~"
  authorId: string;  // "authors/xyz789~"  <-- ALWAYS "*Id" suffix + full relative ID
  title: string;
}

// Polymorphic cross-reference (e.g., audit log pointing to any resource type):
interface ChangeLogEntry {
  id: string;
  targetId: string;    // Full relative ID e.g. "chatRooms/1/messages/2"
  targetType: string;  // Redundant helper for filtering/routing e.g. "Message"
  description: string;
}
```

### Key Rules
- **Naming:** Always suffix reference fields with `Id` (`authorId`, `adminUserId`). Reserve `author` for an **inlined** object—never put a string ID in `author`.
- **Value = full relative resource ID:** Store `"authors/xyz789~"`, not bare `"xyz789~"`.
- **Referential Integrity:** By default, **do not enforce strict database-style foreign-key constraints** across loosely coupled resources (otherwise deleting a popular `User` fails or triggers massive cascades). Accept that references can become dangling (`404` on follow-up `Get`), or explicitly document strict `409 Conflict` / cascade behavior only where domain-critical.
- **Inline Caching (`authorName` copy) Caveat:** Copying foreign fields inline for read speed introduces stale data when the source changes. Optimize for the common case; prefer clean references unless read latency forces denormalization.

---

## Chapter 14: Association Resources

Explicit join resource for **many-to-many** relationships, especially when the relationship carries metadata (`role`, `expireTime`, `invitedBy`).

```ts
interface Membership {
  id: string;           // "memberships/m123~"
  groupId: string;      // Immutable after creation
  userId: string;       // Immutable after creation
  role: string;         // Relationship metadata
  expireTime?: Date;
}

// Full standard CRUD on /memberships
@post("/memberships")       CreateMembership(...): Membership;
@get("/{id=memberships/*}") GetMembership(...): Membership;
@patch("/{resource.id=memberships/*}") UpdateMembership(...): Membership;
@delete("/{id=memberships/*}") DeleteMembership(...): void;
@get("/memberships")        ListMemberships(...): ListMembershipsResponse; // filter by groupId or userId

// Optional read-only convenience aliases (skip if unnecessary)
@get("/{groupId=groups/*}/users") ListGroupUsers(...): ListGroupUsersResponse;
@get("/{userId=users/*}/groups")  ListUserGroups(...): ListUserGroupsResponse;
```

### Rules
- **Naming:** Name after the relationship concept (`Membership`, `Enrollment`, `Subscription`), not `GroupUserAssociation`.
- **Uniqueness:** Reject duplicate `(groupId, userId)` pairs with `409 Conflict` (unless multi-role associations are explicitly allowed).
- **Immutability:** Treat `groupId` and `userId` as immutable after creation; to change them, delete and recreate.
- **Never inline `userIds[]` on `Group` or `groupIds[]` on `User`:** Unbounded arrays fail at scale and cause concurrent write conflicts.

---

## Chapter 15: Add and Remove Custom Methods

Lightweight alternative to Ch 14 **only when no relationship metadata is needed**.

```ts
@post("/{parent=groups/*}/users:add")
AddGroupUser(req: { parent: string; userId: string }): void;

@post("/{parent=groups/*}/users:remove")
RemoveGroupUser(req: { parent: string; userId: string }): void;

@get("/{parent=groups/*}/users")
ListGroupUsers(req: ListGroupUsersRequest): ListGroupUsersResponse;

@get("/{parent=users/*}/groups")
ListUserGroups(req: ListUserGroupsRequest): ListUserGroupsResponse;
```

### Trade-offs vs. Association Resources (Ch 14)
- **Pros:** Simpler API surface, no extra resource type or IDs.
- **Cons:** **Painful migration** if you ever need per-link metadata (like `role` or `expireTime`) later—you cannot easily attach fields to `:add` without breaking or duplicating the model. If metadata is plausible in the future, start with Ch 14 (`Membership`).
- **Idempotency:** `:add` on an already-present member or `:remove` on an absent member should return `409 Conflict` / `404` or be documented clearly (follow Ch 7 imperative consistency).

---

## Chapter 16: Polymorphism

Allowing one collection/resource type to take multiple concrete shapes (e.g., `Message` as text, image, audio, or video).

```ts
interface Message {
  id: string;
  sender: string;
  // Open string discriminator — NOT a rigid enum
  type: 'text' | 'image' | 'audio' | 'video' | string;
  content: string | Media; // Or type-specific fields / union
}
interface Media { uri: string; contentType: string; }
```

### Rules
- **When to use:** Only when callers naturally **list and handle the variants together** in a single stream (e.g., a chat timeline of text + image + video messages). If variants are rarely listed together, keep them separate resources.
- **Type field:** Use an **open `string`** discriminator validated server-side (not a closed enum) so new variants don't break existing clients.
- **Validation:** Validate that fields required for the declared `type` are present; tolerate/ignore leftover or unfamiliar fields rather than failing brittlely on type transitions.
- **Avoid polymorphic methods:** Do **not** overload one method (`Execute(req: any)`) with wildly different behaviors per type—keep methods uniform and put polymorphism on the **resource** structure.
