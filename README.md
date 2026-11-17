# idea-bot

**English** · [Русский](README.ru.md)

A Telegram bot that takes a business idea apart step by step and gives a GO / PIVOT / KILL verdict. Not one wall of text
in answer to a prompt, but eight separate steps with a gate between them: each step is its own model call, its own
message and its own fork, "next / correct / pause". The bot talks to its users in Russian.

## Steps

| # | Step | Web | In fast mode |
|---|------|-----|--------------|
| 1 | Statement | — | yes |
| 2 | Assumptions (🔴 fatal ones) | — | yes |
| 3 | Demand, checked against real data | yes | — |
| 4 | Competitors | yes | — |
| 5 | Pre-mortem | — | yes |
| 6 | Resource reality check | — | — |
| 7 | The cheapest test | — | yes |
| 8 | Verdict | — | yes |

A step sees the raw idea and every step before it, and nothing about the steps after it. So it cannot fold the whole
analysis into a single answer.

## Business profile

After the brief, the bot asks with a button what this is: **a venue with premises**, **a service without premises** or
**an online product**. The profile changes both the system prompt (who is in front of you and what kills this kind of
business) and the emphasis of individual steps: `PROFILE_SYSTEM` and `PROFILE_HINTS` in `bot/steps.py`.

For a venue, demand is looked up in maps and reviews of the neighbourhood, competitors within walking distance,
resources are counted as receipts per day against rent and payroll, and the cheap test is counting passers-by with a
stopwatch, not a post on Reddit. For a mobile service the same goes through requests on local classifieds and business
directories (Avito, 2GIS), the cost of a lead and the ceiling of "how many jobs fit into a week". The online profile
stayed as it was.

## The brief

"Analyse an idea" opens not with an empty field but with a list of seven points: the idea, the customer, what the
customer does now, money, what already exists, how much you will put in, the city. Then comes an empty template in
`<pre>`: tap, copy, fill in. The description can be sent in several messages, which are joined together; a character
counter and a "Done" button wait until the person decides it is enough. Under 320 characters the bot warns honestly
that the analysis will come out generic, but does not stop them from starting.

## A short survey between steps

Before steps 1, 3 and 6 the bot makes a separate cheap call to come up with two questions for this particular idea,
not from a fixed list. Each comes with 3-4 answer buttons, a "✍️ In my own words" button and two ways out: "→ Skip" and
"→ Skip all". Answering is optional: skipping is a full answer, and the step simply goes on without that data.

The answers collect in the `questions` table and are mixed into every later step as a block "what the user has told
about themselves". Skipped questions never reach the context. Which steps ask is the `ask=True` flag in `bot/steps.py`.

## Running it

1. `@BotFather` → a new bot → its token into `.env` (`TELEGRAM_BOT_TOKEN=`).
2. An Anthropic key into `.env` (`ANTHROPIC_API_KEY=`). The default model is `claude-sonnet-5`, changed by the line
   `ANTHROPIC_MODEL=` in the same file. OpenRouter stays as a fallback: it is used only when there is no Anthropic key.
3. `run.bat`.

## The report

After the verdict (and on the card of any analysis) the "📄 Report" button gives the analysis as one self-contained
`.html`: a cover with the verdict badge, score bars, a table of contents, the steps, the assumptions as a table with
🔴🟡⚪ markers, sources as links, and a spread "what this report does not answer", which also leads into the paid track.

There is nothing external inside the file: no fonts, no pictures, no scripts. It opens from the chat, works offline and
prints to PDF with Ctrl+P (page breaks are already in place). The Markdown export is still there, but only the admin
sees it.

## Checking without Telegram

```
python tools/dry_run.py 2 fast     # the first two steps of the fast route
python tools/dry_run.py 8 full     # the whole analysis, with web search on steps 3-4
python tools/test_flow.py          # an offline check of the survey and the report, no keys needed
python tools/demo_report.py        # rebuild the demo report from exports/demo-razbor-*.md
```

## Where things are

- `bot/steps.py` — every prompt. Tone and strictness are changed here only.
- `bot/engine.py` — building a step's context and calling the model.
- `bot/handlers.py` — the Telegram flow: gates, pause, "correct", the list of analyses.
- `bot/llm.py` — the Anthropic Messages API (server-side `web_search`, adaptive thinking, continuing after
  `pause_turn`); OpenRouter as the fallback provider. Search is on only for steps 3-4 and only by a button.
- `bot/render.py` — the model's markdown-lite into safe Telegram HTML, split into messages.
- `bot/billing.py` — Telegram Stars, a free first analysis, referrals.
- `exports/` — analyses exported as files.

## "Launch", the paid track

After a GO or PIVOT verdict the bot offers the "Launch" package: a financial model, location, a legal checklist, a cost
estimate with suppliers, a 60-day plan. After KILL it does not: an upsell on top of "don't do it" looks rude.

Payment is manual, with no provider: the bot issues an invoice with a number, the buyer pays by the details in
`PAY_DETAILS` and presses "I've paid", and the admin gets a request with confirm / reject buttons. `/orders` shows the
latest invoices and everything waiting for a check. A double press does not multiply invoices: an open invoice for the
same analysis is reused.

`LAUNCH_ENABLED=0` in `.env` hides the offer from everyone but the admin. Until the deliverables exist, that is how it
should be: you cannot sell what does not exist. Fill in `PAY_DETAILS`, or the bot will honestly say there is nowhere to
pay.

## What an analysis costs

It is charged once, when the analysis starts: a full one is 30⭐, a fast one 12⭐. The first analysis is free. A paid
analysis can be paused and resumed any number of times, and "correct" on a step is free, up to three times.
