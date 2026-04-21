# Example: codebase triage on a concatenated corpus

This walkthrough assumes a corpus file produced by something like:

```bash
find /path/to/repo -type f \( -name "*.py" -o -name "*.ts" -o -name "*.md" \) -print0 | xargs -0 cat > /tmp/repo_corpus.txt
```

## Goal

Answer: *"Where is auth token issuance implemented, and what tests guard refresh edge cases?"*

## 1) Load corpus and verify session

```json
{"tool":"rlm_init","args":{"path":"/tmp/repo_corpus.txt","session_id":"triage_case"}}
```

```json
{"tool":"rlm_status","args":{"session_id":"triage_case"}}
```

Mock status:

```json
{"session_id":"triage_case","chars":1299442,"buffers":0,"globals":0}
```

## 2) Broad grep discovery

```json
{"tool":"rlm_grep","args":{"session_id":"triage_case","pattern":"token|refresh|jwt|session|auth|oauth|expiry|revoke","max_matches":120,"window":180,"case_insensitive":true}}
```

Why: broad anchors identify candidate modules before deep reading.

## 3) Build evolving map in `rlm_exec`

```json
{
  "tool":"rlm_exec",
  "args":{
    "session_id":"triage_case",
    "code":"hits = grep(r'issueToken|refreshToken|verifyToken|revokeToken', max_matches=200, case_insensitive=True)\nprint('api_hits', len(hits))\nfor h in hits[:12]:\n    print(h['match'])\nadd_buffer(f'Auth API candidate hits: {len(hits)}')"
  }
}
```

Mock output identifies likely implementation clusters plus helper utilities.

## 4) Focused semantic checks with sub-queries

```json
{"tool":"rlm_sub_query","args":{"session_id":"triage_case","max_tokens":900,"prompt":"Based on located auth snippets, infer the primary token issuance path and list functions in call order."}}
```

```json
{"tool":"rlm_sub_query","args":{"session_id":"triage_case","max_tokens":900,"prompt":"From discovered test-like snippets, summarize refresh token edge cases currently covered and obvious missing cases."}}
```

Mock synthesis:

- Issuance pipeline likely flows `createSession` -> `signAccessToken` -> `persistRefreshToken`.
- Tests cover expired access token refresh and revoked refresh token rejection; no explicit clock-skew case found.

## 5) Store findings and produce triage summary

```json
{"tool":"rlm_add_buffer","args":{"session_id":"triage_case","text":"Potential gap: no explicit clock-skew tolerance test for refresh boundary."}}
```

```json
{"tool":"rlm_get_buffers","args":{"session_id":"triage_case"}}
```

Final triage output (host model):

- **Likely implementation files:** auth service + token signer utility + persistence adapter.
- **Existing tests:** happy path, revoked token, expiration rollover.
- **Recommended next probe:** add/locate tests for skew, duplicate refresh races, and rotation replay attempts.

---

### Practical notes

- Keep corpus generation reproducible so span indexes stay stable between runs.
- Use `rlm_clear_buffers` at phase boundaries to avoid carrying stale hypotheses.
