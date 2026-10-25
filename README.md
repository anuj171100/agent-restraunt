# Restaurant agent

A command-line agent that recommends restaurants for a trip. You give it a city, a meal, a diet, and an optional note. It searches for places, finds a menu page, reads the menu text, reads the Google review summary, and writes one recommendation plus a backup.

The answer is in English. Dish names, prices, and review lines are copied from the pages and summaries it reads.

## What you need

- Python 3.11 or newer
- A [Google Places API](https://developers.google.com/maps/documentation/places/web-service/overview) key (Text Search and Place Details)
- A [Tavily](https://tavily.com) API key (used to find menu pages)
- An [OpenRouter](https://openrouter.ai) API key (the model that decides each step)

## Setup

```bash
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env
```

Fill in `.env`:

```text
GOOGLE_PLACES_API_KEY=your-places-key
TAVILY_API_KEY=your-tavily-key
OPENAI_API_KEY=your-openrouter-key
OPENAI_MODEL=openai/gpt-4o-mini
```

`OPENAI_API_KEY` is sent to OpenRouter, not to OpenAI directly. `OPENAI_MODEL` needs the provider prefix, for example `openai/gpt-4o-mini`.

## Run

```bash
python -m src.demo --city London --meal lunch --diet vegetarian \
  --note "normal sit-down lunch, not a tasting menu"
```

| Flag | Required | What it is |
| --- | --- | --- |
| `--city` | yes | City name, for example `London` or `Paris` |
| `--meal` | yes | `breakfast`, `lunch`, or `dinner` |
| `--diet` | yes | Free text, for example `vegetarian` or `no restrictions` |
| `--note` | no | Extra constraint, such as a budget or the kind of meal |

The same command works for another city. Change `--city` and the rest of the flags.

A first run calls Google Places, Tavily, and OpenRouter, so it needs a network connection and can take a few minutes. Every HTTP response and every model reply is stored under `cache/`. Running the same command again replays that cache and finishes much faster.

## What you get

The transcript prints in the terminal and is saved as `runs/<timestamp>.md`. It contains each tool call, the result of that call, and the final answer.

The final answer is meant to include:

- The restaurants found, and the searches that found them
- Which places were kept, which were dropped, and why
- Everyday dishes and prices copied from the menu, and the menu page URL
- An English translation when the menu was not in English
- A positive review line and a negative review line, each with the reviews link
- Review lines that match the diet, the meal, and the note
- One restaurant and one backup, each with its homepage and menu URL

Read the transcript if you want to check a dish name or a quote against the page text.

## Limits

- Menus have to be HTML text. A PDF or a picture comes back as unreadable, and the agent cannot quote dishes from it.
- Translation is the model's reading of the page. There is no separate translation step.
- Reviews are one Google summary for the whole place, with one link. There are no individual reviews and no per-review stars. If the summary has no negative line, the answer should say so.
- The agent can stop before every part of the answer is filled in. Nothing in the program sends it back to fill a gap.
- A run stops after 16 tool rounds. That cap ends the loop; it does not pick a restaurant.
- London searches are biased to the city center, within 4 km. Other cities are not.
- Places come from Google Places and menu URLs come from Tavily. Either can miss a place or a menu page.
- There is no booking, no map, and no account. The output is the transcript.
