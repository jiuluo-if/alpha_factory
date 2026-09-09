# Credentials discovery / authentication configuration design

## Boundary

`wqb_agent/credentials.py` is a local-only resolver. It reads and validates a complete username/password pair, selects one source, and reports only a source category. It does not import Client, requests, Agent, Simulator, proposal execution, or state, and it never authenticates against BRAIN.

`WQBClient` remains the authentication and transport owner. Its constructor either uses a complete explicit pair, or calls the resolver once when both arguments are omitted. A half-specified explicit pair fails before discovery. The existing Basic Auth request, empty body, thread-local Session, `trust_env=False`, 401 handling, Retry-After, 5xx retry, submit spacing and `WQBSubmitUnknownError` paths are outside this change.

## Deterministic precedence

1. Complete explicit `WQBClient(username, password)` pair.
2. Complete `WQB_USERNAME` + `WQB_PASSWORD` system environment pair.
3. Explicit `WQB_CREDENTIALS_ENV_FILE` path, if configured. This is the only supported dotenv-style file and may contain the existing `WQB_*` or `BRAIN_*` names.
4. `~/.brain_credentials.txt`, with username on the first non-empty line and password on the second.
5. No source: return no credentials and let Client raise its existing category-level auth error.

There is no cwd, parent-directory, package-directory, recursive, or implicit repository `.env` search. An explicitly configured env-file path that is missing, unreadable, malformed, or incomplete fails closed. The default home file may fall through only when it does not exist; if it exists but is unreadable or malformed, it fails.

## Fail-closed and secret safety

Each source is independently tri-state: both values absent, both present, or incomplete (error). Values from different sources are never combined. File values retain the current stripping behavior; system environment values retain their current raw-string behavior except empty strings count as missing. Error messages use source categories only and never include values, file contents, or auth headers. `CredentialSource.__repr__` omits username/password.

## Documentation and tests

README and agent guidance recommend WQB env vars for CI/server and the home file for local workstations, while documenting explicit env-file opt-in only. Tests cover old implicit locations as ignored, cwd independence, source precedence, malformed/unreadable files, partial sources, Client lazy resolution, and unchanged transport/auth behavior through the existing suites.
