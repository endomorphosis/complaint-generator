# REF-306 Codebase Scan Finding

Date: 2026-07-23
Fingerprint: 08605ffbd8d9b23a386f9b818e78094bf1c2ad1d
Kind: swallowed_exception
Source: tests/test_website_cohesion_playwright.py:407
Priority: P1
Track: quality

## Evidence

```text
except Exception:
```

## Suggested Handling

Review the finding in context, decide whether it represents a bug, missing test,
maintenance risk, or false positive, and land a small fix with validation. If the
finding is a false positive, document why in the changed code or discovery notes
so the supervisor does not keep re-adding the same work.
