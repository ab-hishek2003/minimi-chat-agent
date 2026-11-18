# Design notes: minimi

## The brief
Build the best chat agent I can with **one tool, web search**. It should answer fast, get things right, and remember what was asked and when.

## Overview
- **One tool.** The model has exactly one tool, `web_search` (Tavily). It decides for itself when a question needs fresh facts.
- **Model.** `openai/gpt-oss-120b` on Groq, through the OpenAI-compatible API.
- **Memory.** SQLite. Every message is stored with a timestamp.
- **Interface.** A FastAPI backend and a plain HTML/JS chat page.

```
Browser -> FastAPI /chat -> Groq model --(needs facts?)--> Tavily search -> Groq model -> reply
                |
             SQLite (messages + timestamps, per visitor)
```

## 1. Answer fast
- Groq's inference is fast, and the request path is short.
- **No search, one model call.** With search, exactly two calls (decide and search, then answer). There is no agent loop that can run away.
- Context is bounded: the last 20 messages of the current chat, each trimmed to 4,000 characters, and replies are capped at 4,000 tokens.
- Search returns only 4 short results, so the second call stays small.
- Endpoints are plain functions, so a slow call never blocks other visitors.

## 2. Get things right
- **Search only when it helps.** The system prompt says to search for live, recent or verifiable facts, to name the sources it used, and to say when it is unsure instead of inventing an answer.
- **The model knows the date.** The current time (UTC) is in the system prompt, so "today" and "this week" are resolved correctly.
- **Search results are untrusted.** The prompt tells the model to ignore any instructions hidden in a web page.
- **Output checks.** An empty or degenerate reply (for example a loop of dots) is detected, retried once with a clean context, and otherwise replaced by a short apology. Hidden reasoning tags and echoed timestamps are stripped.
- **Failures leave no trace.** If the model call fails, the saved user message is rolled back, so one failure never corrupts later answers.

## 3. Remember what was asked and when
- Every message is saved with a UTC timestamp.
- Each of the user's messages is sent to the model with its timestamp in front. The model answers "what did I ask, and when?" from these.
- Assistant messages are sent **without** timestamps. In testing the model copied the format into its own replies and produced garbage, so only user messages carry them.
- Besides the current chat's history, the model is given the user's last 15 questions from their **other** chats, with times. "What did I ask yesterday?" works even in a new chat.
- Each visitor has a private random cookie id, so people never see each other's memory.

## Trade-offs and limits
- Inside one chat only the last 20 messages are in context, so a very long chat forgets its oldest messages. Questions from other chats are kept as a short digest.
- There are no accounts. Memory belongs to a browser cookie.
- The free host's disk is temporary, so saved chats are erased when the service restarts. A managed database is the production fix.
- Answer quality depends on four Tavily snippets per search; it does not read full pages.
- Times are in UTC. The model says so unless the user gives a time zone.
- **Beyond the brief.** Picture and document understanding, voice input and read-aloud, and image generation (switched off when no key is set) are interface conveniences. The model's only tool is still `web_search`.

## Reliability and testing
There are 16 automated tests, with the AI model replaced by a fake so no keys are needed. They cover the web search tool call, timestamps and memory across chats, visitor isolation, rate limits, file limits, broken-output recovery and failure rollback. They run on every push through GitHub Actions. Rate limits (per visitor, per IP, per day) protect the API keys.

## How it was built
I built minimi with Claude as a coding assistant. I set the requirements and the design direction, set up the accounts and keys, deployed it, tested it, and worked through the problems we hit along the way, such as a failed deployment and a bug where the model repeated its own timestamps.

## What I would do next
- Stream replies so the first words appear sooner.
- Move memory to a managed database so it survives restarts.
- Show sources as clickable links under each answer.
- Build a small evaluation set of factual questions to measure accuracy, and measure latency instead of estimating it.
