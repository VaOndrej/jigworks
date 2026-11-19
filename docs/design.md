# Jigworks — společný brainstorming a architektonický návrh

- **Verze:** 0.6 (zúžené MVP + rozsah prototypu pro case study)
- **Datum aktualizace:** 19. 11. 2026
- **Stav:** pracovní návrh, ne hotová technická specifikace
- **Kontext:** take-home case study „Design Your Software Factory" (AI Engineer, FTMO & OANDA); doporučený čas ~4 h, živé demo + záložní nahrávka, repo vč. agent instrukcí, promptů, testů, evalů a build logu; jen veřejná/syntetická data.
- **Primární použití:** AI-first software development (cílovka = vývojáři)
- **Budoucí použití:** další týmové procesy (HR, právní, ops) — v MVP jen jako ukázka směru
- **Licence:** FSL-1.1-ALv2 (viz `LICENSE.md`)

**Zásada projektu:** Stavíme webový hub pro psaní, verzování a distribuci existujících LangGraph workflow do VS Code a lokální runner, který je vykoná. Nestavíme vlastní náhradu LangGraphu. Jediný zdroj pravdy je publikovaná verze vykonatelného Python workflow.

**Jméno:** „Software Factory" kolidovalo s firmou Factory (factory.ai, AI coding agenti). Pracovní jméno **Jigworks** — *jig* je výrobní přípravek, který vede nástroj tak, aby každý řez byl stejný; workflow dělá totéž s agentem.

---

## 1. Rozsah

### Tři produktové části

1. **Web Hub** (React + TypeScript, Vite): psaní workflow jako **normální Python kód** přímo ve webu; graf je **jen read-only vizualizace** přes LangGraph `get_graph()` → React Flow (se zvýrazněním běžících uzlů). Verzování, publikování, přehled běhů, audit log a cena. Textová záložka „HR oddělení".
2. **VS Code extension** (TypeScript + React Webview): výběr publikovaného workflow, prompt, spuštění, živý průběh kroků, tlačítko Schválit/Zamítnout (human-in-the-loop). Přes lokální Python runner vykonává LangGraph graf, který volá `claude -p` (později další CLI).
3. **Hub API** (Python + FastAPI + PostgreSQL) na Vercelu: drafty a releasy workflow, distribuce do extension, příjem událostí běhů, analytika usage/ceny.

### Rozsah prototypu (case study, v pořadí stavby)

Každý krok musí jít ukázat samostatně; když 3 nestihneme, demo stojí na 1 + 2 a Hub je v prezentaci jako „co jsem vyškrtl".

1. **Runner + workflow `feature-development` (jádro)**
   - `plan → testy ze zadání (jiný agent) → implement → nezávislý review → gate → schválení člověkem (interrupt) → PR`
   - Ukázkové repo: malá **syntetická order-handling služba s invarianty** hlídanými property testy (odpověď senior engineerovi: „agenti tiše rozbíjí invarianty").
   - Audit log: kdo spustil, verze workflow (digest), model, změněné soubory, tokeny, cena.
2. **VS Code extension:** výběr workflow, prompt, živé kroky, Schválit/Zamítnout.
3. **Hub na Vercelu (minimální):** Python editor + publish verze, `get_graph()` graf, seznam běhů s audit logem a cenou, textová záložka HR.

### Výslovně mimo

- Vizuální editace grafu (jen read-only `get_graph()`), vlastní graph engine, DSL, katalog node typů.
- Serverové CI/CD gates, automatický production deploy, governance napříč všemi nástroji.
- HR/právní funkcionalita (jen textová záložka), veřejné API, marketplace, JetBrains, cloudové runnery.
- Integrace s otevřenou chat session oficiální Claude Code extension.

**Produktová hranice:** workflow může vyžadovat review/testy/schválení a runner to v rámci řízeného běhu vykoná. Nelze tvrdit, že zabráníme použít jiný nástroj nebo obejít kontroly při mergi.

## 2. Mapování na lidi ze zadání

| Kdo | Problém | Odpověď v návrhu |
|---|---|---|
| Senior engineer (trading) | agent tiše rozbíjí invarianty | testy/invarianty píše jiný agent ze zadání **před** implementací; property testy jako gate |
| Early adopter | velké PR, testy od stejného agenta, povrchní review | nezávislý review uzel, gate před člověkem, malé kroky |
| Team lead | každý má vlastní setup, odchází s ním; neví, jestli jsou rychlejší | workflow sdílené a verzované v Hubu; porovnání verzí (cena, počet oprav, úspěšnost) |
| Long-task engineer | agent ztrácí kontext napříč sessions | LangGraph checkpoint + git snapshot per uzel; stav běhu je mimo kontext agenta |
| Platform engineer | laptopy, vlastní credentials, žádný záznam ani cena | audit log každého běhu, analytika ceny, izolace do git worktree; deklarace oprávnění agenta per release (návrh) |
| Security & compliance | audit trail, approver ≠ author, autorství | události běhu = audit trail; `interrupt` = lidské schválení; autor = člověk, který běh spustil a schválil |
| Ops analytik (ne-inženýr) | shadow IT na laptopu | mimo prototyp; v Hubu záložka popisující směr (workflow + varianty pro oddělení, běh mimo IDE) |

## 3. Technologie

| Vrstva | Technologie | Stav |
|---|---|---|
| Web Hub frontend | React + TypeScript (Vite) | Schváleno |
| Graf | React Flow (`@xyflow/react`), read-only z `get_graph()` | Schváleno |
| Hub API | Python + FastAPI | Schváleno |
| Hosting | Vercel, jeden projekt `jigworks`, **Vercel Services** (Beta) pro web + API | Schváleno |
| Databáze | PostgreSQL (Neon přes Vercel Marketplace) | Schváleno |
| Úložiště balíčků | Vercel Blob | Návrh |
| Izolovaná validace kódu workflow | Vercel Sandbox | Návrh |
| Workflow execution | LangGraph (Python) | Schváleno |
| Python prostředí | `uv`, jedno venv per digest releasu | Schváleno |
| IDE klient | VS Code extension (TS) + React Webview, instalace lokálně přes `.vsix` | Schváleno |
| Agent | `claude -p --output-format stream-json`; později Codex | Schváleno |
| Účty | primárně firemní API klíč; Pro účty mají pro `claude -p` samostatný programatický kredit (ověřit v code.claude.com/docs/en/legal-and-compliance) | K ověření |
| Rust | nepoužít | Rozhodnuto |

Langflow / LangSmith Studio: jen inspirace. LangSmith Studio už graf vizualizuje a trasuje, ale je vázané na LangSmith (self-host jen Enterprise). Odlišujeme se: VS Code + lokální CLI agenti + distribuce verzí týmu + varianty pro oddělení.

## 4. Architektura

```
                 WEB HUB (React, Vite)            ┐
        Python editor | get_graph() graf | běhy   │ Vercel projekt "jigworks"
        audit | cena | záložka HR                 │ (Vercel Services)
                        |                         │
                 HUB API (FastAPI)                │
        Postgres | releases | channels | events   ┘
                        |
              HTTPS REST (+ SSE s reconnectem / polling)
                        |
              VS CODE EXTENSION (TS)
        Webview: workflow | prompt | kroky | Schválit
                        |
                 lokální proces
                        |
              LOCAL RUNNER (Python, uv venv per digest)
        LangGraph graf | checkpoint + git snapshot | audit log
                        |
              CLI AGENT ADAPTÉRY
        claude -p (stream-json) | později Codex
                        |
              repo | git worktree | testy | Playwright
```

- Hub vlastní publikované verze, přiřazení a souhrnnou historii. Nepotřebuje přístup ke kódu ani k CLI credentials.
- Runner vlastní vykonávání; streamuje události do extension i hubu. Při výpadku spojení fronta lokálně a sync po obnovení.
- SSE na Vercel funkcích má časový limit → klient musí počítat s reconnectem (případně polling).

## 5. Web Hub: workflow jako Python

- Workflow se píše jako standardní Python LangGraph (`StateGraph`, `add_node`, `add_edge`, `add_conditional_edges`, `interrupt`).
- Graf se zobrazuje **jen pro čtení**: kód se zkompiluje v izolovaném prostředí, `get_graph()` → JSON → React Flow. Žádný roundtrip, žádné tiché přepisování kódu.
- AI úpravy: návrh změny jako diff; před uložením syntax/import/compile v izolaci.

### Workflow balíček

```
feature-development/
  graph.py            # StateGraph, vstupní bod
  steps/              # node funkce
  prompts/            # prompty fází
  workflow.toml       # name, entrypoint, min runner version, inputs, oprávnění agenta (návrh)
  requirements.lock   # uv lock
  README.md
```

Kód publikovaných workflow se nikdy nevykonává v procesu Hub API.

## 6. Verze a distribuce

`Draft → Validate → Publish immutable release (workflowId, version, digest) → Channel (stable/beta) → Sync do extension → Run pinned version`

- **Distribuce přes Hub API:**
  - `GET /api/workflows/{id}/channels/stable` → release id + digest
  - `GET /api/releases/{id}/bundle` → `.zip`
  - extension ověří digest, rozbalí do vlastní cache, `uv` venv per digest
- **Fallback:** příkaz „Import workflow ze souboru" ve VS Code (stejný `.zip`).
- Rollback = přesměrování kanálu na starší release. Běžící úkol se novou verzí nikdy nezmění.
- Nová verze se nabídne, ale nespustí se bez explicitního režimu nastaveného týmem.

## 7. VS Code extension

- Výběr workspace, workflow (`feature-development@1.3.0`), agenta/modelu.
- Prompt + volitelné přílohy z workspace.
- Start / stop / resume; živé kroky, tool calls, tokeny, cena, odkazy na diff a Playwright artefakty.
- **Human-in-the-loop:** LangGraph `interrupt` → Schválit/Zamítnout v extension (schválení plánu, schválení před PR).
- Paralelní běhy v samostatných git worktrees.
- Remote SSH / Dev Containers: runner a CLI musí běžet u workspace.

### Rozhraní agenta

- `run(prompt, cwd, options) → result + events`
- Claude adapter: `claude -p --output-format stream-json`, `--resume` pro navazující session, oprávnění přes `--allowedTools` / `--permission-mode`. Auth patří Claude Code, ne Jigworks.

## 8. Hub API, analytika, audit

| Endpoint | Použití |
|---|---|
| `GET /api/workflows` | seznam workflow |
| `GET/PUT /api/workflows/{id}/draft` | draft |
| `POST /api/workflows/{id}/validate` | validace v izolaci |
| `POST /api/workflows/{id}/publish` | nový release |
| `GET /api/workflows/{id}/releases` | verze |
| `GET /api/workflows/{id}/channels/{name}` | resolve kanálu |
| `GET /api/releases/{id}/bundle` | stažení `.zip` |
| `POST /api/runs` | registrace běhu + pinned release |
| `POST /api/runs/{id}/events` | ingest událostí |
| `GET /api/runs/{id}/events/stream` | SSE |
| `GET /api/analytics/usage` | reporting |

### Analytika (vlastní, bez LangSmith/Langfuse)

- Zdroj: závěrečná zpráva `stream-json` (`usage`, `total_cost_usd`) — přesná pole ověřit ve spiku B.
- Ukládat **surové tokeny per volání**: `runId, node, attempt, model, adapter, input, output, cache_write, cache_read`.
- **Ceník jako tabulka s platností:** `model, token_type, price_per_mtok, valid_from`; cena se počítá při čtení.
- Cache tokeny oceňovat zvlášť (v agentních smyčkách tvoří většinu).
- U Pro účtů štítek „API ekvivalent". `total_cost_usd` z CLI jen jako kontrola.
- Adaptér normalizuje do stejných polí (Codex hlásí jinak).

### Audit

Každý běh: kdo spustil, release + digest, model, kroky, změněné soubory (git snapshot per uzel), výsledky gate, kdo schválil a kdy, tokeny a cena.

### Události běhu (příklad)

```json
{
  "runId": "run_123",
  "release": "feature-development@1.3.0",
  "node": "review",
  "status": "running",
  "attempt": 2,
  "at": "2026-11-19T15:00:00Z"
}
```

## 9. První workflow `feature-development`

```
START → plan → [human approve plan] → write_tests (jiný agent, ze zadání)
      → implement → review (nezávislý agent)
            review FAIL → fix → review          (limit iterací)
            review PASS → gate (testy + property testy invariantů)
            gate FAIL → fix → gate
            gate PASS → [human approve] → open PR → summary → END
```

- Kroky jsou běžné Python funkce přes `add_node`; smyčky přes `add_conditional_edges`; checkpointy LangGraph + git commit per uzel (hash ve stavu grafu).
- Akceptace: runner projde aspoň jednou opravnou smyčkou a extension zobrazí průběh i schválení.

## 10. Odloženo

- HR/právní/ops: jen textová záložka v Hubu (Ondřej popíše use-casy, např. automatický CV screening). Budoucí tvar: základní workflow + varianta oddělení s přidanými kontrolními/schvalovacími uzly (subgrafy + `interrupt`) a běh mimo IDE.
- Veřejné API, JetBrains, cloud runnery, scheduling, marketplace, pokročilá oprávnění, fakturace, server-side CI enforcement.

## 11. Otevřené otázky

1. Checkpoint + git snapshot: obnova po restartu IDE bez dvojího side-effectu.
2. Deklarace oprávnění agenta per release (`--allowedTools`, síť, zápis) a její zobrazení před instalací.
3. Porovnání verzí workflow z analytiky (cena, opravy, úspěšnost).
4. Granularita telemetrie `stream-json` — ověřit ve spiku B.
5. Billing Pro účtů pro `claude -p` — ověřit aktuální podmínky.

## 12. Repo struktura (plán)

```
jigworks/
  AGENTS.md            # instrukce pro agenty; povinná Playwright kontrola vizuálu (390 px + 1440 px)
  CLAUDE.md            # odkaz na AGENTS.md
  LICENSE.md           # FSL-1.1-ALv2
  BUILD_LOG.md         # čas a co bylo delegováno/reviewováno/ručně/co se pokazilo
  vercel.json          # Services: hub-web + hub-api
  apps/hub-api/        # FastAPI
  apps/hub-web/        # Vite + React + React Flow
  clients/vscode/      # extension; později jetbrains/, hr-portal/
  runner/              # lokální runner + adaptéry
  packages/contracts/  # schéma událostí a API → TS + Python typy
  workflows/feature-development/
  sample-repo/         # syntetická order-handling služba s invarianty
  demo/                # později
  e2e/                 # Playwright
  docs/
```

Nástroje: pnpm workspace (TS), uv workspace (Python).

## 13. Historie rozhodnutí

- **v0.6 (19. 11. 2026):** projekt pojmenován Jigworks, licence FSL-1.1-ALv2. Web Hub = psaní Pythonu + read-only `get_graph()` graf (vizuální editace vyřazena). Distribuce přes Hub API + fallback import `.zip`. Analytika vlastní (tokeny × ceník s platností). Hosting Vercel Services + Neon. Cílovka vývojáři, HR jen textová záložka. Governance prvky (audit, nezávislý review, human approval) přesunuty do jádra kvůli zadání case study. Rozsah prototypu: runner → extension → minimální Hub.
- **v0.5:** striktně tříčásté MVP, bez policy engine a DSL, lokální vykonávání Python LangGraph balíčku.
- **v0.4:** FastAPI REST/SSE hub, VS Code TS/React Webview, releases, live usage.
- **v0.3:** React/TS, React Flow, Python/FastAPI + LangGraph; Rust volitelný.
- **v0.2:** lokální vykonávání s centrálně publikovanými workflow.

## 14. Odkazy

- LangGraph Graph API: https://docs.langchain.com/oss/python/langgraph/graph-api
- LangGraph conditional routing: https://reference.langchain.com/python/langgraph/graph/state/StateGraph/add_conditional_edges
- LangGraph persistence: https://docs.langchain.com/oss/python/langgraph/persistence
- React Flow: https://reactflow.dev/
- VS Code Extension Host: https://code.visualstudio.com/api/advanced-topics/extension-host
- VS Code Webviews: https://code.visualstudio.com/api/extension-guides/webview
- Vercel Services: https://vercel.com/docs/services
- Claude Code legal & compliance: https://code.claude.com/docs/en/legal-and-compliance
- FSL: https://fsl.software
