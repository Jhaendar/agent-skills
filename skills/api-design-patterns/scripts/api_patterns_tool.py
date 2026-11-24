#!/usr/bin/env python3
"""CLI helper for the api-design-patterns skill (Python 3.9+ stdlib).

Subcommands:
  id-gen        Generate Crockford Base32 IDs with a Base37 checksum character (Ch 6).
  id-verify     Verify a Crockford Base32 + Base37 checksummed resource ID (Ch 6).
  lint-openapi  Audit an OpenAPI 3.x / Swagger 2.0 spec against book rules.
"""

import argparse
import json
import os
import re
import secrets
import sys
import uuid
from typing import Any, Dict, List, Optional, Tuple

ALPHABET_32 = "0123456789ABCDEFGHJKMNPQRSTVWXYZ"
ALPHABET_37 = ALPHABET_32 + "*~$=U"
CHAR_TO_VAL_32 = {ch: idx for idx, ch in enumerate(ALPHABET_32)}

UNITLESS_NUMBER_NAMES = {
    "size",
    "delay",
    "timeout",
    "duration",
    "weight",
    "distance",
    "length",
    "width",
    "height",
    "price",
    "amount",
    "cost",
    "fee",
}
PRECISION_SENSITIVE_SUFFIXES = ("id", "_id", "price", "amount", "balance", "cost")
NEGATIVE_BOOL_PREFIXES = ("disable", "disallow", "no_", "skip", "prevent", "exclude")
PAGINATION_ANTIPATTERN_PARAMS = {
    "pagesize",
    "page_size",
    "offset",
    "page",
    "skip",
    "per_page",
    "perpage",
}
PREPOSITION_RE = re.compile(r"(?:With|For|By|To)(?=[A-Z]|$)|(?:_with_|_for_|_by_|_to_)")


def encode_crockford_base32(raw_bytes: bytes) -> str:
    if not raw_bytes:
        raise ValueError("raw_bytes must be non-empty")
    n_chars = (len(raw_bytes) * 8 + 4) // 5
    pad_bits = n_chars * 5 - len(raw_bytes) * 8
    val = int.from_bytes(raw_bytes, "big") << pad_bits
    chars = []
    for i in range(n_chars - 1, -1, -1):
        chars.append(ALPHABET_32[(val >> (5 * i)) & 0x1F])
    return "".join(chars)


def checksum_char_for_bytes(raw_bytes: bytes) -> str:
    remainder = int.from_bytes(raw_bytes, "big") % 37
    return ALPHABET_37[remainder]


def generate_id(prefix: Optional[str] = None, num_bytes: int = 8, use_uuid: bool = False) -> str:
    raw_bytes = uuid.uuid4().bytes if use_uuid else secrets.token_bytes(num_bytes)
    token = encode_crockford_base32(raw_bytes) + checksum_char_for_bytes(raw_bytes)
    return f"{prefix.strip('/')}/{token}" if prefix else token


def _normalize_body_char(ch: str) -> Optional[str]:
    u = ch.upper()
    if u in ("I", "L"):
        return "1"
    if u == "O":
        return "0"
    if u in CHAR_TO_VAL_32:
        return u
    return None


def _normalize_checksum_char(ch: str) -> Optional[str]:
    u = ch.upper()
    if u in ("I", "L"):
        return "1"
    if u == "O":
        return "0"
    if u in ALPHABET_37:
        return u
    return None


def verify_token(token: str) -> Tuple[bool, str]:
    cleaned = token.replace("-", "")
    if len(cleaned) < 2:
        return False, "Token too short (must include body + checksum character)."

    body_raw, cs_raw = cleaned[:-1], cleaned[-1]
    norm_cs = _normalize_checksum_char(cs_raw)
    if norm_cs is None:
        return False, f"Invalid checksum character: {cs_raw!r}"

    norm_body_chars: List[str] = []
    for ch in body_raw:
        mapped = _normalize_body_char(ch)
        if mapped is None:
            return False, f"Invalid Crockford Base32 character in ID body: {ch!r}"
        norm_body_chars.append(mapped)

    val = 0
    for ch in norm_body_chars:
        val = (val << 5) | CHAR_TO_VAL_32[ch]

    total_bits = len(norm_body_chars) * 5
    byte_len = total_bits // 8
    pad_bits = total_bits - byte_len * 8
    if byte_len < 1 or pad_bits >= 5 or (val & ((1 << pad_bits) - 1)) != 0:
        return False, "Invalid Base32 bit padding length."

    raw_bytes = (val >> pad_bits).to_bytes(byte_len, "big")
    expected_cs = checksum_char_for_bytes(raw_bytes)
    if expected_cs != norm_cs:
        return False, f"Checksum mismatch: expected {expected_cs!r}, got {norm_cs!r}."
    return True, "Valid Crockford Base32 ID and Base37 checksum."


def verify_identifier(identifier: str, all_segments: bool = False) -> Dict[str, Any]:
    path_part = identifier.split("@", 1)[0].strip("/")
    if not path_part:
        return {"identifier": identifier, "valid": False, "httpStatusHint": 400, "reason": "Empty identifier."}

    segments = path_part.split("/")
    if all_segments and len(segments) >= 2:
        targets = [segments[i] for i in range(1, len(segments), 2)]
    else:
        targets = [segments[-1]]

    for seg in targets:
        ok, reason = verify_token(seg)
        if not ok:
            return {
                "identifier": identifier,
                "valid": False,
                "httpStatusHint": 400,
                "reason": f"Segment {seg!r}: {reason}",
            }

    return {
        "identifier": identifier,
        "valid": True,
        "httpStatusHint": 200,
        "reason": "All checked ID segment(s) pass Base37 checksum verification (404 if absent in DB).",
    }


def _load_spec(spec_path: str) -> Dict[str, Any]:
    with open(spec_path, "r", encoding="utf-8") as f:
        raw = f.read()

    ext = os.path.splitext(spec_path)[1].lower()
    if ext in (".yaml", ".yml"):
        try:
            import yaml  # type: ignore
        except ImportError as exc:
            raise RuntimeError(
                "YAML OpenAPI file provided, but PyYAML is not installed in this Python environment. "
                "Convert to JSON or install pyyaml."
            ) from exc
        data = yaml.safe_load(raw)
    else:
        try:
            data = json.loads(raw)
        except json.JSONDecodeError:
            try:
                import yaml  # type: ignore
                data = yaml.safe_load(raw)
            except Exception as exc:
                raise RuntimeError(f"Failed to parse {spec_path} as JSON: {exc}") from exc

    if not isinstance(data, dict):
        raise RuntimeError("OpenAPI specification root must be a JSON/YAML object.")
    return data


def _add_finding(
    findings: List[Dict[str, str]],
    severity: str,
    chapter: str,
    location: str,
    message: str,
) -> None:
    findings.append(
        {
            "severity": severity,
            "chapter": chapter,
            "location": location,
            "message": message,
        }
    )


def _walk_schema(
    schema: Any,
    loc: str,
    findings: List[Dict[str, str]],
) -> None:
    if not isinstance(schema, dict):
        return

    if "enum" in schema:
        _add_finding(
            findings,
            "MINOR",
            "Ch 5, 24",
            loc,
            "Closed schema 'enum' risks client breakage on additions; prefer documented string validation.",
        )

    props = schema.get("properties")
    if isinstance(props, dict):
        for prop_name, prop_schema in props.items():
            prop_loc = f"{loc}.{prop_name}"
            if not isinstance(prop_schema, dict):
                continue
            ptype = prop_schema.get("type")
            lower_name = prop_name.lower()

            if ptype in ("number", "integer"):
                if lower_name in UNITLESS_NUMBER_NAMES:
                    _add_finding(
                        findings,
                        "MAJOR",
                        "Ch 3, 5",
                        prop_loc,
                        f"Ambiguous unitless numeric field '{prop_name}'; append unit (e.g. sizeBytes, delaySeconds) or use a structured value object.",
                    )
                if any(lower_name.endswith(sfx) for sfx in PRECISION_SENSITIVE_SUFFIXES):
                    _add_finding(
                        findings,
                        "MAJOR",
                        "Ch 5, 6",
                        prop_loc,
                        f"Field '{prop_name}' typed as {ptype}; IDs must be strings and monetary/decimal values should be strings or structured objects to avoid IEEE-754 precision loss.",
                    )

            if ptype == "boolean" and lower_name != "includedeleted":
                if any(lower_name.startswith(pfx) for pfx in NEGATIVE_BOOL_PREFIXES) or (
                    lower_name.startswith("no") and len(prop_name) > 2 and prop_name[2].isupper()
                ):
                    _add_finding(
                        findings,
                        "MINOR",
                        "Ch 5",
                        prop_loc,
                        f"Negative boolean '{prop_name}'; prefer positive naming (e.g. enableX, allowX) to avoid double negatives.",
                    )

            _walk_schema(prop_schema, prop_loc, findings)

    items = schema.get("items")
    if isinstance(items, dict):
        _walk_schema(items, f"{loc}[]", findings)

    for key in ("allOf", "oneOf", "anyOf"):
        sub = schema.get(key)
        if isinstance(sub, list):
            for idx, entry in enumerate(sub):
                _walk_schema(entry, f"{loc}.{key}[{idx}]", findings)


def lint_openapi_spec(spec: Dict[str, Any]) -> List[Dict[str, str]]:
    findings: List[Dict[str, str]] = []
    paths = spec.get("paths") or {}
    if isinstance(paths, dict):
        for path, path_item in paths.items():
            if not isinstance(path_item, dict):
                continue

            # Ignore optional leading /v1 or /api/v1 prefix when counting resource levels
            clean_path = re.sub(r"^/(?:api/)?v\d+(?:alpha|beta)?", "", path)
            param_segments = [s for s in clean_path.split("/") if s.startswith("{") and s.endswith("}")]
            if len(param_segments) > 3:
                _add_finding(
                    findings,
                    "MAJOR",
                    "Ch 4",
                    path,
                    f"Deep resource hierarchy ({len(param_segments)} parameter levels > 3); flatten intermediate groupings into cross-references or filterable fields.",
                )

            if PREPOSITION_RE.search(clean_path):
                _add_finding(
                    findings,
                    "MINOR",
                    "Ch 3",
                    path,
                    "Preposition in path name; often signals a missing FieldMask, filter, or association resource.",
                )

            has_put = "put" in path_item
            has_patch = "patch" in path_item
            if has_put and not has_patch:
                _add_finding(
                    findings,
                    "MINOR",
                    "Ch 7, 8",
                    path,
                    "Defines PUT without PATCH; prefer partial PATCH (+ fieldMask) over full-replacement PUT to prevent silent data loss.",
                )

            is_custom = ":" in path
            is_delete_rev = ":deleteRevision" in path

            path_params = path_item.get("parameters") or []
            for method in ("get", "post", "put", "patch", "delete"):
                op = path_item.get(method)
                if not isinstance(op, dict):
                    continue
                op_loc = f"{method.upper()} {path}"

                op_id = op.get("operationId", "")
                if isinstance(op_id, str) and PREPOSITION_RE.search(op_id):
                    _add_finding(
                        findings,
                        "MINOR",
                        "Ch 3",
                        op_loc,
                        f"Preposition in operationId '{op_id}'; check whether FieldMask, filter, or an association resource avoids combinatorial method names.",
                    )

                if is_custom and method in ("patch", "put") or (is_custom and method == "delete" and not is_delete_rev):
                    _add_finding(
                        findings,
                        "MAJOR",
                        "Ch 9, 18",
                        op_loc,
                        "Custom/batch methods (:action) must use POST (or GET if strictly safe/read-only), never PATCH/PUT/DELETE (except :deleteRevision).",
                    )

                all_params = list(path_params) + list(op.get("parameters") or [])
                for param in all_params:
                    if not isinstance(param, dict):
                        continue
                    if param.get("in") == "query":
                        pname = str(param.get("name", ""))
                        if pname.lower() in PAGINATION_ANTIPATTERN_PARAMS:
                            _add_finding(
                                findings,
                                "MAJOR",
                                "Ch 21",
                                f"{op_loc}?{pname}",
                                f"Pagination parameter '{pname}' risks off-by-one/end-of-list bugs or deep-offset cost; prefer 'maxPageSize' + opaque 'pageToken'.",
                            )

                req_body = op.get("requestBody")
                if isinstance(req_body, dict):
                    content = req_body.get("content") or {}
                    if isinstance(content, dict):
                        for mime, media in content.items():
                            if isinstance(media, dict) and "schema" in media:
                                _walk_schema(media["schema"], f"{op_loc} requestBody({mime})", findings)

                responses = op.get("responses") or {}
                if isinstance(responses, dict):
                    for code, resp in responses.items():
                        if isinstance(resp, dict):
                            content = resp.get("content") or {}
                            if isinstance(content, dict):
                                for mime, media in content.items():
                                    if isinstance(media, dict) and "schema" in media:
                                        _walk_schema(media["schema"], f"{op_loc} response[{code}]({mime})", findings)

    components = spec.get("components") or {}
    schemas = components.get("schemas") if isinstance(components, dict) else None
    if not isinstance(schemas, dict):
        schemas = spec.get("definitions")
    if isinstance(schemas, dict):
        for sname, sdef in schemas.items():
            _walk_schema(sdef, f"schema.{sname}", findings)

    return findings


def _run_self_test() -> int:
    # 1. Crockford Base32 + Base37 roundtrips
    for nbytes in (8, 15):
        token = generate_id(prefix="books", num_bytes=nbytes)
        res = verify_identifier(token)
        assert res["valid"] is True, f"Roundtrip failed for {token}: {res}"
        # Lowercase + hyphens + Crockford I/L/O tolerance on body
        body, cs = token.split("/", 1)[1][:-1], token.split("/", 1)[1][-1]
        mangled_body = body.lower().replace("1", "l").replace("0", "o")
        mangled = f"books/{mangled_body[:4]}-{mangled_body[4:]}{cs.lower()}"
        assert verify_identifier(mangled)["valid"] is True, f"Normalization failed for {mangled}"
        # Flip one body char -> must fail checksum
        bad_ch = "8" if body[0] != "8" else "9"
        corrupted = f"books/{bad_ch}{body[1:]}{cs}"
        assert verify_identifier(corrupted)["valid"] is False, f"Corrupted ID passed unexpectedly: {corrupted}"

    # 2. UUID mode
    uid_token = generate_id(prefix="chatRooms", use_uuid=True)
    assert len(uid_token.split("/", 1)[1]) == 27
    assert verify_identifier(uid_token)["valid"] is True

    # 3. 'U' checksum handling (remainder == 36)
    raw_u = (36).to_bytes(8, "big")
    u_token = encode_crockford_base32(raw_u) + checksum_char_for_bytes(raw_u)
    assert u_token.endswith("U")
    assert verify_identifier(u_token)["valid"] is True
    assert verify_identifier(u_token[:-1] + "u")["valid"] is True
    # 'U' in body must be rejected
    assert verify_identifier("U" + u_token[1:])["valid"] is False

    # 4. OpenAPI linter checks
    sample_spec = {
        "openapi": "3.0.3",
        "paths": {
            "/orgs/{o}/teams/{t}/projects/{p}/tasks/{k}": {"get": {"responses": {}}},
            "/booksWithAuthors": {
                "get": {
                    "operationId": "listBooksWithAuthors",
                    "parameters": [{"name": "pageSize", "in": "query"}],
                    "responses": {},
                }
            },
            "/emails/{id}:send": {"patch": {"responses": {}}},
            "/orders/{id}": {"put": {"responses": {}}},
        },
        "components": {
            "schemas": {
                "Order": {
                    "type": "object",
                    "properties": {
                        "orderId": {"type": "integer"},
                        "size": {"type": "number"},
                        "totalPrice": {"type": "number"},
                        "disableNotifications": {"type": "boolean"},
                        "status": {"type": "string", "enum": ["NEW", "PAID"]},
                    },
                }
            }
        },
    }
    findings = lint_openapi_spec(sample_spec)
    chapters_hit = {f["chapter"] for f in findings}
    assert len(findings) >= 9, f"Expected >= 9 findings, got {len(findings)}: {findings}"
    assert "Ch 4" in chapters_hit and "Ch 21" in chapters_hit and "Ch 9, 18" in chapters_hit
    print(f"SELF-TEST PASSED ({len(findings)} sample OpenAPI rules verified, Base32/Base37 checksums verified)")
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description="API Design Patterns CLI helper")
    parser.add_argument("--self-test", action="store_true", help="Run built-in unit checks")
    sub = parser.add_subparsers(dest="cmd")

    p_gen = sub.add_parser("id-gen", help="Generate Crockford Base32 + Base37 checksum ID(s)")
    p_gen.add_argument("--prefix", default=None, help="Collection path prefix (e.g. books)")
    p_gen.add_argument("--bytes", type=int, default=8, help="Random byte width (default: 8 -> 13+1 chars; 15 -> 24+1 chars)")
    p_gen.add_argument("--uuid", action="store_true", help="Generate from 16-byte UUID v4 (26+1 chars)")
    p_gen.add_argument("--count", type=int, default=1, help="How many IDs to generate")

    p_ver = sub.add_parser("id-verify", help="Verify Crockford Base32 + Base37 checksum ID")
    p_ver.add_argument("identifier", help="Resource ID or token to verify")
    p_ver.add_argument("--all-segments", action="store_true", help="Verify every resource ID segment in a hierarchical path")

    p_lint = sub.add_parser("lint-openapi", help="Lint an OpenAPI 3.x / Swagger 2.0 JSON (or YAML) spec")
    p_lint.add_argument("spec_path", help="Path to OpenAPI spec file")
    p_lint.add_argument("--json", action="store_true", help="Output findings as JSON")

    args = parser.parse_args()
    if args.self_test:
        return _run_self_test()

    if args.cmd == "id-gen":
        for _ in range(args.count):
            print(generate_id(prefix=args.prefix, num_bytes=args.bytes, use_uuid=args.uuid))
        return 0

    if args.cmd == "id-verify":
        res = verify_identifier(args.identifier, all_segments=args.all_segments)
        print(json.dumps(res, indent=2))
        return 0 if res["valid"] else 1

    if args.cmd == "lint-openapi":
        try:
            spec = _load_spec(args.spec_path)
        except Exception as exc:
            print(f"Error loading OpenAPI spec: {exc}", file=sys.stderr)
            return 2
        findings = lint_openapi_spec(spec)
        if args.json:
            print(json.dumps({"spec": args.spec_path, "count": len(findings), "findings": findings}, indent=2))
        else:
            if not findings:
                print(f"No anti-patterns flagged in {args.spec_path}.")
            else:
                print(f"Found {len(findings)} potential issue(s) in {args.spec_path}:")
                for f in findings:
                    print(f"[{f['severity']}] ({f['chapter']}) {f['location']}: {f['message']}")
        return 0

    parser.print_help()
    return 1


if __name__ == "__main__":
    sys.exit(main())
