# viewBase Workbench — architektura služeb, aplikací a přístupu (detailní specifikace)

**Stav:** návrh pro scaffold / MVP  
**Projekt:** [viewBase2](https://github.com/alchy/viewBase2/)  
**Související:** logické oddělení access / screen / window; pluginový frontend (`wm/*`, `plugins/*`)

Tento dokument popisuje cílový model Workbenche, externích aplikací (content providerů), identity pro MVP a toky na příkladech — včetně toho, jak by do modelu zapadl současný graf.

---

## 0. Slovník

| Termín | Význam |
|--------|--------|
| **Workbench** | Celé prostředí screenů a oken (viewBase jako hostitel). |
| **Screen** | Plocha (Amiga-style); má stabilní `screen_id`. |
| **Window (slupka)** | Rám, chrome, geometrie, z-order, minimalizace — řídí Workbench. |
| **Window (content)** | Tělo okna; dodává **apka** (content provider). |
| **Apka / App** | Samostatně nasaditelný content provider (`kind` + backend + client module). |
| **Instance** | Běhová vazba apky na konkrétní okno: `(screen_id, window_id)`. |
| **kind** | Typ okna/obsahu v protokolu (`graph`, `log`, `shell`, `hello-app`, …). |
| **Subject** | Aktér (uživatel nebo anonymní relace) v access-manageru. |
| **Session** | Relace prohlížeče (`session_id` / `sid`). |
| **Client module** | JS balíček, který v prohlížeči vykreslí a obslouží *tělo* okna daného `kind`. |
| **Scaffold** | In-process implementace za stabilními rozhraními; remote/kontejnery později. |

---

## 1. Cíle a ne-cíle

### 1.1 Cíle

1. Oddělit **access-manager**, **screen-manager** a **content vrstvu (apky / window-manager)**.
2. Umožnit publikovat **vlastní apku** (vlastní API + vlastní JS) v izolovaném kontejneru.
3. Apka **neřídí** chrome okna; obsluhuje jen požadavky pro `(screen_id, window_id)`.
4. Workbench je **jediný** přímý kontakt s JS klientem (WebSocket / HTTP static).
5. Access model řídí Workbench + access-manager; apka dostane alespoň **MVP SubjectContext**.
6. Stávající graf musí jít do stejného modelu popsat (nejdřív scaffold, pak kontejner).
7. Frontend už má pluginový řez (`registerType`, `actions`) — návrh na něj navazuje, nerozbíjí ho.

### 1.2 Ne-cíle MVP

- Kubernetes / plná orchestrace.
- LDAP / OIDC implementace (jen místo v access-manageru).
- Roles a libovolné claims nad rámec MVP subjectu.
- Přímé WebSocket spojení prohlížeče → apka.
- Big-bang přepis `GraphWindow` v jednom PR (přípustný postupný řez).

---

## 2. Velký obraz

```text
                    ┌──────────────────────────┐
                    │     access-manager       │
                    │  subject, session,       │
                    │  groups, authorize()     │
                    └────────────▲─────────────┘
                                 │
┌────────────┐         ┌─────────┴─────────┐         ┌─────────────────────────┐
│ JS klient  │◄───────►│  screen-manager   │◄───────►│  App registry + apps    │
│ Workbench  │  WS+HTTP│  screeny, slupka  │         │  graph / hello / …      │
│ chrome+UI  │         │  routing, bind    │         │  per (screen, window)   │
└────────────┘         └───────────────────┘         └─────────────────────────┘
```

**Pravidlo č. 1:** Prohlížeč mluví jen se screen-managerem.  
**Pravidlo č. 2:** Každá privilegovaná operace prochází `authorize`.  
**Pravidlo č. 3:** Apka dostává práci už v kontextu povoleného subjectu + instance.

---

## 3. Komponenty

### 3.1 access-manager

**Odpovědnost:** jediná autorita authn/authz.

**MVP umí:**

- vytvořit / validovat / invalidovat session,
- znát `subject_id` a `groups[]` (i prázdné),
- `authorize(subject, action, resource) → Allow | Deny`.

**MVP neumí (zatím):**

- LDAP, OIDC, jemné roles/claims UI,
- vlastní render login stránky (může zůstat ve Workbenchi).

**Resource (příklady):**

- `screen:{screen_id}`
- `window:{screen_id}/{window_id}`
- `app:{app_id}`
- `action:window.open` / `action:window.unlock` / `action:content.event`

### 3.2 screen-manager

**Odpovědnost:** nosná vrstva Workbenche.

**Vlastní:**

- registr screenů a oken (slupka),
- WebSocket k klientům,
- skládání protokolových zpráv (`init` / `patch` / akce),
- bind okna na apku: `(screen_id, window_id) → app_id`,
- volání access-manageru,
- volání app instance API,
- servírování / proxy statiky client modulů (volitelné).

**Nevlastní:**

- business stav grafu, obsah hello-app, PTY shellu (to mají apky),
- finální verdikt práv (access-manager).

### 3.3 App registry + apky (content vrstva)

**App registry** (logicky u Workbenche): katalog dostupných `app_id` / `kind`.

**Apka:**

- registruje se (metadata + endpointy),
- drží stav **per instance** `(screen_id, window_id)`,
- poskytuje content API,
- poskytuje popis client modulu,
- přijímá `SubjectContext` u user-facing volání.

Vestavěné apky (graph, log, shell…) mohou v MVP běžet in-process za stejným interface jako budoucí kontejnery.

---

## 4. SubjectContext (MVP)

```text
SubjectContext
  subject_id: string    # např. "user:42" | "anonymous"
  session_id: string    # sid prohlížeče
  groups: string[]      # může být []
```

### 4.1 Pravidla

1. User-facing volání Workbench → apka **vždy** nese `SubjectContext`.
2. Workbench volá apku až **po** úspěšném `authorize` (nebo apku nevolá).
3. Apka **nedělá** login Workbenche ani nevěří klientovi na slovo.
4. Apka **smí** filtrovat data podle `subject_id` / `groups` a auditovat.
5. Interní healthcheck bez uživatele subject nést nemusí.

### 4.2 Příklad JSON

```json
{
  "subject_id": "user:42",
  "session_id": "c3f1e2a0-…",
  "groups": ["ops"]
}
```

### 4.3 Později (mimo MVP)

`display_name`, `roles[]`, `claims{}`, IdP subject.

---

## 5. Identita instance

Každá běžící obsahová jednotka:

```text
InstanceRef
  screen_id:  number | string
  window_id:  string
  app_id:     string        # např. "viewbase.graph"
  kind:       string        # např. "graph" (to, co vidí klient)
```

Apka **neadresuje** „globální jeden graf procesu“, ale vždy instanci.  
(I když MVP často bude 1 graph na screen — model je připravený na víc.)

---

## 6. Registrace apky

### 6.1 Registration document

```json
{
  "app_id": "example.hello",
  "kind": "hello-app",
  "version": "1.0.0",
  "backend_base_url": "http://hello-app:8080",
  "client_module": {
    "id": "example.hello.ui",
    "version": "1.0.0",
    "url": "/apps/example.hello/ui.js"
  },
  "actions": ["content.event", "content.snapshot"],
  "health_url": "http://hello-app:8080/health"
}
```

### 6.2 Kdo registruje

- při startu kontejneru apka POST na Workbench App Registry, **nebo**
- deklarace v konfiguraci Workbenche (vestavěné apky).

### 6.3 MVP zjednodušení

- Registry může být konfig soubor + in-process handlery.
- Heartbeat/TTL může počkat; stačí static register + health.

---

## 7. Client module (JS obsahu)

### 7.1 Stav v repu (východisko)

Frontend už odděluje:

- **jádro WM** (`wm/window_manager.js`) — `registerType(kind, factory)`, chrome, z-order,
- **pluginy** (`plugins/*`) — obsah a `actions`,
- **Desktop** instaluje pluginy; graf je lazy; shell dynamicky importuje xterm.

### 7.2 Cílový princip

| Otázka | Odpověď |
|--------|---------|
| Kde běží Three.js / hello UI? | V prohlížeči, v client modulu apky. |
| Kdo modul spouští? | Desktop / WindowManager podle `kind`. |
| Kdo modul „posílá“? | Nepřenáší se přes WS jako kód z content backendu v každém packetch; klient ho **načte** (bundle nebo `import(url)`). |
| Role screen-manageru | V protokolu pošle `kind` (+ později `client_module` descriptor) a data; JS nespouští. |

### 7.3 Descriptor v protokolu (příprava)

```json
{
  "kind": "graph",
  "window_id": "g1",
  "client_module": {
    "id": "viewbase.graph.ui",
    "version": "…",
    "url": "/apps/viewbase.graph/ui.js"
  }
}
```

**MVP:** vestavěné kindy zůstanou v hlavním bundle; descriptor může být implicitní.  
**Později:** neznámý `kind` → dynamic import podle `url`.

### 7.4 Kontrakt client pluginu (sladěný s dneškem)

```text
install(ctx) → Plugin

Plugin {
  name: string
  actions?: { [actionName]: (msg) => void }
  onInit?: () => void
  setVisible?: (active: boolean) => void
  setResourcesPaused?: (hidden: boolean) => void
  destroy?: () => void
}

// při install:
//   windowManager.registerType(kind, factory)
//   factory volá adopt(BaseWindow subclass)
```

`ctx` obsahuje minimálně: `container`, `screenId`, `sendEvent`, `windowManager`, theme hooks — jako dnešní `createDesktop` context.

---

## 8. Protokol klient ↔ screen-manager (rozšíření konceptu)

Beze změny filosofie stávajícího protokolu (`init`, `patch`, `log`, eventy, akce).

### 8.1 init (zjednodušený tvar)

```json
{
  "type": "init",
  "protocol": 1,
  "seq": 1,
  "screen_id": 1,
  "sid": "c3f1e2a0-…",
  "config": {
    "title": "Ahoj",
    "theme": "cyber"
  },
  "windows": [
    {
      "kind": "graph",
      "window_id": "g1",
      "title": "Síť",
      "secured": false,
      "client_module": { "id": "viewbase.graph.ui", "url": "/apps/viewbase.graph/ui.js" }
    },
    {
      "kind": "hello-app",
      "window_id": "h1",
      "title": "Hello",
      "client_module": { "id": "example.hello.ui", "url": "/apps/example.hello/ui.js" }
    }
  ],
  "content": {
    "g1": { "nodes": [], "edges": [], "node_types": {}, "config": { "dimensions": 3 } },
    "h1": { "text": "" }
  }
}
```

**Poznámka k MVP migraci:** dnes jsou nodes/edges na top-level `init` kvůli historickému graph-hostiteli. Cíl je vázat content na `window_id`. Přechod může mapovat starý tvar → `content[g1]`.

### 8.2 patch

```json
{
  "type": "patch",
  "seq": 2,
  "screen_id": 1,
  "window_id": "g1",
  "add_nodes": [ { "id": "a", "meta": { "name": "Alfa" } } ]
}
```

### 8.3 klient → server event

```json
{
  "type": "event",
  "event": "hello_submit",
  "payload": {
    "window_id": "h1",
    "name": "MojeJmeno"
  }
}
```

Screen-manager doplní subject ze session, autorizuje, předá apce.

---

## 9. Instance API Workbench → apka

Společný contract pro každou apku (MVP).

```text
AppBackend

  create_instance(instance: InstanceRef, spec: Object, subject: SubjectContext) -> Snapshot
  destroy_instance(instance: InstanceRef, subject: SubjectContext) -> void

  snapshot(instance: InstanceRef, subject: SubjectContext) -> Snapshot
  apply_event(instance: InstanceRef, subject: SubjectContext, event: Object) -> EventResult

  # volitelné push z apky do Workbenche (callback / queue)
  # on_delta(instance, delta)
  # on_action(instance, action)   # např. focus, hello_set_text
```

### 9.1 Příklad volání

```json
POST /instances/create
{
  "instance": { "screen_id": 1, "window_id": "h1", "app_id": "example.hello", "kind": "hello-app" },
  "spec": { "title": "Hello" },
  "subject": { "subject_id": "user:42", "session_id": "…", "groups": ["ops"] }
}
```

```json
POST /instances/event
{
  "instance": { "screen_id": 1, "window_id": "h1", "app_id": "example.hello", "kind": "hello-app" },
  "subject": { "subject_id": "user:42", "session_id": "…", "groups": ["ops"] },
  "event": { "type": "hello_submit", "name": "MojeJmeno" }
}
```

```json
→ EventResult
{
  "deltas": [
    { "op": "set_text", "text": "nazdar MojeJmeno" }
  ]
}
```

Workbench přeloží `deltas` na zprávy ke klientovi (patch/action).

---

## 10. Access tok (MVP)

```text
Klient event
  → screen-manager: session → subject
  → access-manager.authorize(subject, "content.event", "window:1/h1")
       Deny  → chyba klientovi; apka se nevolá
       Allow → app.apply_event(instance, subject, event)
```

Apka může vrátit business deny („read-only“), ale **nesmí** být jediná brána pro „je vůbec přihlášen“.

---

## 11. Příklad A — Hello apka (publikovaná v kontejneru)

### 11.1 Záměr

- API: `GET /hello/{jmeno}` → `"nazdar {jmeno}"` (vnitřní API apky).
- Ve Workbenchi okno, které po odeslání jména vypíše pozdrav.
- Apka neřídí rám okna.

### 11.2 Registrace

```json
{
  "app_id": "example.hello",
  "kind": "hello-app",
  "version": "1.0.0",
  "backend_base_url": "http://hello-app:8080",
  "client_module": {
    "id": "example.hello.ui",
    "url": "/apps/example.hello/ui.js"
  }
}
```

### 11.3 Otevření okna (Python fasáda Workbenche)

```python
# ilustrativní API — pojmenování fasády může kopírovat dnešní styl viewBase
win = vb.AppWindow(
    screen=screen,
    kind="hello-app",
    window_id="h1",
    title="Hello",
)
project.serve(screen)
```

### 11.4 Sequence

```text
Developer/Workbench
  → screen-manager.add_window(S, kind=hello-app, id=h1)
  → authorize(subject, window.open, window:S/h1)
  → hello-app.create_instance(S,h1, spec, subject)
  → klient init/open_window kind=hello-app + client_module
  → klient import ui.js, registerType, open

User napíše "MojeJmeno" a odešle
  → klient event hello_submit { window_id:h1, name:"MojeJmeno" }
  → screen-manager + authorize
  → hello-app.apply_event(..., subject, event)
       vnitřně může zavolat vlastní GET /hello/MojeJmeno
  → delta set_text "nazdar MojeJmeno"
  → screen-manager → klient action/patch
  → ui.js zobrazí text v těle okna
```

### 11.5 Client module (náčrt)

```js
// example.hello ui.js — ilustrace
export function install(ctx) {
  const { windowManager, sendEvent } = ctx;
  windowManager.registerType('hello-app', (spec) => {
    const win = windowManager.adopt(new HelloWindow({
      id: spec.window_id,
      title: spec.title,
      manager: windowManager,
      onSubmit: (name) => sendEvent({
        type: 'event',
        event: 'hello_submit',
        payload: { window_id: spec.window_id, name },
      }),
    }));
    win.bringToFront();
    return win;
  });
  return {
    name: 'hello-app',
    actions: {
      hello_set_text: (msg) => {
        const w = windowManager.get(msg.window_id);
        w?.setText(msg.text);
      },
    },
  };
}
```

### 11.6 Co hello-app nedělá

- nevytváří screen,
- nemění z-order,
- neotevírá WebSocket na prohlížeč,
- nevyžaduje TOTP sama (secured řeší Workbench).

---

## 12. Příklad B — současný graf jako apka

### 12.1 Mapování kódu

| Dnes v repu | V app modelu |
|-------------|--------------|
| `GraphWindow` nodes/edges/drain/handlers | **graph-app** instance state + apply_event |
| `WindowsMixin` + registr log/shell/html na GraphWindow | **screen-manager** (pryč z graph-app) |
| `protocol` init nodes/edges | content snapshot instance `g1`, přeposlaný screen-managerem |
| `plugins/graph/*`, `physics/*`, `render/*` | **client_module** `viewbase.graph.ui` |
| `createGraphPlugin` + `registerType('graph')` | install() client modulu |
| `desktop.ensureGraphPlugin` | lazy load kind=graph pro screen |
| chrome / Options lock | Workbench WM jádro |

### 12.2 Registration

```json
{
  "app_id": "viewbase.graph",
  "kind": "graph",
  "version": "…",
  "backend_base_url": "http://graph-app:8080",
  "client_module": {
    "id": "viewbase.graph.ui",
    "url": "/apps/viewbase.graph/ui.js"
  }
}
```

### 12.3 Veřejné API pro vývojáře (fasáda beze změny filosofie)

```python
import viewbase as vb

project = vb.Project(port=8080)
screen = vb.Screen(title="Infra")
graph = vb.GraphWindow(screen=screen, title="Síť", dimensions=3)

graph.add_node("a", name="Alfa")
graph.add_edge("a", "b")  # po ensure b …

project.serve(screen, open_browser=True)
```

Fasáda `GraphWindow.add_node` uvnitř volá graph-app (in-process nebo HTTP), **ne** sahá do WebSocket vrstvy přímo.

### 12.4 create_instance

Workbench:

```text
authorize(subject, window.open, window:1/g1)
graph-app.create_instance(
  instance={screen_id:1, window_id:"g1", app_id:"viewbase.graph", kind:"graph"},
  spec={title:"Síť", dimensions:3, theme:"cyber", quality:"auto"},
  subject=SubjectContext(...)
) → Snapshot { nodes, edges, node_types, flows, config }
```

Klient dostane open `kind=graph` + snapshot; client module spustí PhysicsEngine + Renderer stejně jako dnes.

### 12.5 add_node za běhu

```text
graph.add_node("x", name="X")
  → graph-app mutuje stav instance (1,g1)
  → on_delta / pull drain
  → screen-manager patch { window_id:"g1", add_nodes:[…] }
  → GraphStore/plugin na klientovi
```

Fyzika zůstává **v prohlížeči** (Barnes-Hut ve workeru) — server posílá jen topologii.

### 12.6 Klik na uzel

```text
plugin sendEvent node_click
  → screen-manager
  → authorize(subject, content.event, window:1/g1)
  → graph-app.apply_event(instance, subject, {type:"node_click", node_id:"a"})
  → user handlers (@graph.on_click)
  → případně akce show_detail / highlight zpět přes Workbench
```

### 12.7 Subject v grafu (MVP)

Graf apka minimálně:

- loguje `subject_id` u handlerů,
- může později filtrovat meta podle `groups`,
- neimplementuje vlastní session store.

### 12.8 Co musí pryč z GraphWindow při řezu

Aby graph-app nebyla monolit:

1. registr a lifecycle **cizích** oken → screen-manager,
2. menu screenu → screen-manager / screen entita,
3. WS serve smyčka → screen-manager,
4. secured grant adresace → access-manager + screen-manager (`drain_actions` grant logika).

Graph-app si nechá: graph model, delty, graph-specific actions, every() úlohy vázané na graph data.

---

## 13. Příklad C — více klientů, jeden screen

```text
Session A (user:42, groups:[ops])
Session B (user:7,  groups:[guests])

Oba vidí screen 1, okno g1 (graph).

Event od B:
  authorize(user:7, content.event, window:1/g1)
  → Deny (guest nemůže editovat) → apka se nevolá

Snapshot pro B:
  authorize Allow na read
  → graph-app.snapshot(instance, subject B)
  → apka může vrátit redukovaná meta (MVP: klidně stejná data)
```

Workbench rozhoduje *zda* volat; apka může jemně škrtat *co* vrátí.

---

## 14. Secured okno v app modelu

1. `secured=True` na slupce drží screen-manager.  
2. Bez grantu klient dostane `kind: "locked"` (dnešní vzor) — content apka se pro plný snapshot nevolá.  
3. Unlock: klient → screen-manager → access-manager (kód/session) → grant.  
4. Po Allow: `create_instance`/`snapshot` s subjectem, client dostane skutečný `kind` + content.  
5. Apka neimplementuje Guru Meditation UI (to je Workbench core).

---

## 15. Static / načítání JS

### 15.1 MVP (vestavěné apky)

```text
Jeden frontend bundle (jako dnes)
  wm/* + plugins/graph + plugins/log + …
Desktop instaluje známé pluginy
Graph lazy, xterm dynamic import u shellu
```

### 15.2 Publikované apky

```text
Workbench HTTP:
  GET /apps/example.hello/ui.js

Klient:
  if (!registry.has("hello-app"))
    await import("/apps/example.hello/ui.js")
    install(ctx)
  windowManager.open("hello-app", spec)
```

Workbench může JS **proxyovat** z kontejneru apky, aby prohlížeč nemusel na cizí origin (jednodušší cookies/CORS).

---

## 16. Fázování implementace

### Fáze A — Spec (tento dokument)

### Fáze B — Scaffold in-process

1. Interface `AccessManager` + přesun session/secured rozhodování.  
2. Interface `ScreenManager` (slupka, WS, bind).  
3. Interface `AppBackend` + `AppRegistry`.  
4. Graph jako **in-process** `AppBackend` (bez HTTP).  
5. Frontend beze změny bundle; kind routování beze změny.  
6. `SubjectContext` na hranici screen → app.  
7. Oddělit registr cizích oken od `GraphWindow` (postupně).

### Fáze C — Tvrdší hranice

- DTO na hranicích, zákaz přímých importů napříč vrstvami.  
- Content v `init` vázaný na `window_id`.

### Fáze D — Remote apka

- Hello-app kontejner jako první remote.  
- Dynamic client_module.  
- Graph remote až po stabilizaci instance API.

---

## 17. Akceptační kritéria MVP scaffoldu

1. Existují dokumentovaná rozhraní access / screen / app.  
2. Alespoň jedna content cesta (graph nebo hello) jde přes `AppBackend` + `SubjectContext`.  
3. Klient stále používá jedno WS na Workbench.  
4. `authorize` je na open window a content event.  
5. Examples typu quickstart fungují přes fasádu.  
6. Žádný mandatory LDAP/roles.  
7. Spec client modulů je popsána; vestavěné kindy fungují ze stávajícího bundle.

---

## 18. Anti-patterns (nedělat)

1. Apka otevírá vlastní WS na prohlížeč „protože tak je to jednodušší“.  
2. Apka věří `subject_id` z těla požadavku od klienta bez Workbenche.  
3. Screen-manager obsahuje Three.js / business graf model.  
4. Graph-app znovu hostí shell/log okna.  
5. Nový `kind` vyžaduje editovat jádro `window_manager.js` (místo `registerType`).  
6. MVP nafukovat na plný IAM.

---

## 19. Souhrnné příklady vedle sebe

### Hello remote

```text
Container hello-app
  API /hello/{name}
  UI /ui.js
  instances (S,W) → last text

Workbench
  registry kind=hello-app
  window h1 → hello-app
  subject na každém event
```

### Graph vestavěný jako app

```text
In-process graph-app
  Graph model + drain
  Client = plugins/graph (bundle)

Workbench
  window g1 → graph-app
  patch nodes/edges
  subject na node_click
```

### Společné

```text
Chrome = Workbench
Content = App
Who = AccessManager → SubjectContext
Key = (screen_id, window_id)
```

---

## 20. Otevřené body (rozhodnout při implementaci, neblokují MVP model)

1. Přesné názvy Python fasád (`AppWindow` vs. zachovat `GraphWindow` only).  
2. Zda push delta z apky je callback in-process nebo queue.  
3. Jestli `groups` v MVP plnit z config mapy users→groups, nebo vždy `[]` do prvního reálného zdroje.  
4. Top-level vs. per-window content v protokolu během migrace.  
5. Proxy static `/apps/...` vs. veřejný origin kontejneru.

---

## 21. Jednověté shrnutí

**Workbench (screen-manager + access-manager) vlastní screeny, slupku oken, session a práva; apky v kontejnerech nebo in-process vlastní jen content a client JS pro své `kind`, adresují stav přes `(screen_id, window_id)` a na každém user-facing volání dostanou MVP `SubjectContext` (subject_id, session_id, groups) — nikdy neřídí chrome ani neautentizují Workbench samy.**

---

*Konec specifikace. Implementační plány (mapování na soubory v `python/viewbase/` a `frontend/src/`) patří do navazujícího plánu v `docs/superpowers/plans/`.*
