# Provider Data Boundary

- Decision date: 19 July 2026
- Current permitted data: committed synthetic fixtures and privately held licensed synthetic test data
- Real customer or client invoices: `BLOCKED`
- Decision owner: Project owner; legal/privacy review not yet performed

## Data Flow

| Destination      | Data sent                                                                                   | Data not intentionally sent                                                  | Credential           |
| ---------------- | ------------------------------------------------------------------------------------------- | ---------------------------------------------------------------------------- | -------------------- |
| Mistral OCR      | Complete PDF encoded as a `data:application/pdf;base64` document plus OCR model name        | Local storage key, application user token, audit history, reviewer notes     | Mistral bearer token |
| OpenAI extractor | OCR text, extraction-only system instructions, model name, and JSON response-format request | Original PDF bytes, application user token, audit history, reviewer identity | OpenAI bearer token  |

Provider responses are reduced to parsed pages, trace identifiers, invoice fields, confidence
evidence, and sanitized error codes. Raw provider error bodies are not returned by the API.

## Enforced Application Controls

1. Provider endpoints must use HTTPS on port 443.
2. Hostnames must exactly match `MISTRAL_ALLOWED_HOSTS` or `EXTRACTOR_ALLOWED_HOSTS`; suffix matches
   such as `api.openai.com.attacker.test` are rejected.
3. Endpoint URLs cannot contain usernames, passwords, query strings, or fragments.
4. The HTTP transport installs a redirect-rejecting handler. Bearer-authenticated requests are not
   followed to another URL, including another allowlisted URL.
5. Provider timeout and fixed-limit processing retries remain enforced.
6. Public-demo mode remains mock-provider only.

These controls constrain where data can leave the application. They do not prove how a provider
stores, trains on, retains, deletes, or geographically processes submitted data.

OpenAI states that API data is not used to train its models unless the customer explicitly opts in.
Default abuse-monitoring logs may retain prompts and responses for up to 30 days. Modified Abuse
Monitoring and Zero Data Retention require account approval and must be verified for the exact
project before any real invoice is permitted. See the official
[OpenAI data controls](https://platform.openai.com/docs/models/default-usage-policies-by-endpoint).

## External Acceptance Record

Real invoices remain prohibited until each selected provider has dated evidence for:

- zero-data-retention or an explicitly accepted retention period;
- training opt-out and subprocessors;
- processing and storage region;
- DPA and permitted data categories;
- deletion request procedure and completion SLA;
- security incident notification terms;
- quota, retry, and outage behavior;
- account-level configuration matching the written terms.

Record the source URL or signed contract, reviewer, review date, account configuration screenshot or
export, and decision expiry. A marketing page or undocumented dashboard state is insufficient.

## Change Procedure

Adding a provider or proxy requires an explicit allowlist change, endpoint-policy regression tests,
an update to this document, and a new security release decision. Never broaden the allowlist with a
wildcard.
