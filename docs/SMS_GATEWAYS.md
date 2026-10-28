# SMS gateways (any provider, set up on screen)

A school can send SMS through any HTTP SMS provider without code: Advanta, Onfon, Celcom Africa, Mobitech and others,
as well as international ones. Africa's Talking keeps its own built-in option.

## Set up

1. **School SMS Gateway → New**. Fill it in from the provider's API documentation:

| Field | What to enter |
| --- | --- |
| Send URL | The send-SMS endpoint. Must be `https://`. |
| Method, Body Format | Usually POST and JSON. Some providers want Form, or GET. |
| Phone Number / Message Parameter | The provider's names for them, e.g. `mobile` and `message` |
| Number Format | `2547…`, `+2547…` or `07…` (local, using the school's country code) |
| Recipients | One request per number, or all numbers in one request (with the separator) |
| Sender ID Parameter, Sender ID | e.g. `shortcode` and your approved sender name |
| API Key Parameter, Send API Key In, Prefix, API Key | e.g. `apikey` in the Body; or `Authorization` in a Header with prefix `Bearer `. The key is stored encrypted and is never shown in errors. |
| Other Fixed Parameters | Anything else every request needs, e.g. `partnerID`. Tick Header for HTTP headers. |
| **Success Field and Success Values** | Where the status is in the JSON reply, and its value on success, e.g. `responses.0.response-code` and `200`. **Set this:** many gateways reply HTTP 200 even when the message failed (low credit, unapproved sender ID). |
| Or: Reply Contains | For plain-text replies: text that a successful reply contains |

2. Save, then click **Send Test SMS**. It says exactly what the gateway answered, if the message was refused.
3. **School Settings → SMS Provider = SMS Gateway**, and choose the gateway.

## How it behaves

- **Failures are recorded as failed.** A message only counts as sent when the reply matches the success rule. Failures
  go to the Error Log with the provider's reply; the API key is replaced by `***`.
- **What leaves the school is only the message.** Messages that were sent are recorded in the SMS Log.
- **Safe for a shared server.** The URL must be `https://` on port 443, to a public internet address. Each request
  resolves the name once and connects to exactly that address, with TLS checked against the name, so a gateway
  cannot be pointed at the server's own network, even by a DNS answer that changes later.
- **Licensing.** The School SMS Gateway screen belongs to the messaging module.
