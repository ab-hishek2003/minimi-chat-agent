# Security Policy

## Reporting a vulnerability
Please do not open a public issue for security problems.
Use GitHub's **Report a vulnerability** button on the Security tab of this repository, or email ABHISHEKRAUTARAY360@GMAIL.COM.
You will get a reply within a few days.

## What is already protected
- API keys are read from environment variables on the server and never sent to the browser.
- Each visitor only sees their own chats (random private cookie id).
- Per-visitor and global rate limits protect the API keys from abuse.
- Uploaded files are size-limited, type-checked and never executed.
- Web search results are treated as untrusted data in the system prompt.

## Never commit
`.env`, API keys, tokens, or `chat_memory.db`. If a key is ever pushed to GitHub, delete it at the provider and create a new one.
