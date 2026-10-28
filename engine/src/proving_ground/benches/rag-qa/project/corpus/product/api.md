# REST API

Updated: 2026-03-10

The Brindle Desk REST API lets you read and write tickets, contacts and inboxes. Authenticate with a bearer token created under Settings, API.

Rate limit: each API token may make 600 requests per minute. Requests over the limit receive HTTP 429 with a Retry-After header.

Responses are paged, 100 records at a time. The older v1 API was retired in 2025.
