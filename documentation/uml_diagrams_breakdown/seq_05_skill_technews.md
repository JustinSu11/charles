# Sequence Diagram 5 of 7 — Skill: Tech News (Hacker News)

Covers: how the tech news skill is triggered, the parallel Hacker News API calls, and context injection. Triggered when the user's message contains "hacker news", "news" with tech context words, or "trending" with tech context words.

```mermaid
sequenceDiagram
    participant Chat as POST /chat<br>(chat.py)
    participant SR as SkillRouter<br>(skill_router.py)
    participant HN as TechNews Skill<br>(tech_news.py)
    participant HNAPI as Hacker News API<br>(hacker-news.firebaseio.com)
    participant OR as OpenRouter API<br>(external)

    Chat ->> SR: route(message)
    Note over SR: Tier 1: "hacker news" / " hn "<br>Tier 2: "news" + tech context word<br>("tech"/"latest"/"today"/"trending"/etc.)<br>Tier 3: "trending"/"latest" + tech domain word
    SR -->> Chat: ["tech_news"]

    Chat ->> HN: run_skill("tech_news", message)

    HN ->> HNAPI: GET /v0/topstories.json
    Note over HNAPI: No auth required
    HNAPI -->> HN: [id1, id2, ..., id500]
    HN ->> HN: slice top 10 IDs

    par Parallel story fetches (asyncio.gather)
        HN ->> HNAPI: GET /v0/item/{id1}.json
        HN ->> HNAPI: GET /v0/item/{id2}.json
        HN ->> HNAPI: GET /v0/item/{id3}.json
        Note over HN,HNAPI: ... × 10 concurrent requests
    end

    HNAPI -->> HN: story objects<br>{title, url, score,<br>descendants (comments), by}

    HN ->> HN: filter type == "story"<br>skip exceptions
    HN -->> Chat: skill_context block:<br>titles, scores, comment counts,<br>authors, URLs

    Chat ->> OR: POST /chat/completions<br>{history, system_prompt + skill_context}
    Note over OR: Voice: LLM picks top 2-3 stories<br>Web: LLM can reference full list
    OR -->> Chat: reply summarising top stories
```
