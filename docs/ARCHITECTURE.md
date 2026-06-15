# Architecture, Similarweb Free API Cockpit

## Modules principaux

```text
streamlit_app.py
  -> UI Streamlit, formulaires, orchestration sync/async, exports

similar.py
  -> client synchrone historique, cache legacy, session warm-up, historique

core_async.py
  -> client async pour batch, concurrence bornee, pacing, fallback cache stale

cache.py
  -> cache SQLite persistant

rate_state.py
  -> circuit breaker local pour cooldown 403/429

config.py
  -> constantes reseau, headers, user-agents, statuts internes

ui_*.py
  -> rendu tables, charts, summary, exports, builders

automation_seo_theme.py
  -> design system Automation SEO, logo, build marker
```

## Flux domaine unique

```text
saisie domaine
  -> run_single_lookup
  -> similar.similarGet
  -> cache frais si disponible
  -> warm-up similarweb.com
  -> appel endpoint data.similarweb.com
  -> detection 403/429 / CloudFront
  -> cache stale si blocage
  -> affichage synthese + graphiques
```

## Flux batch

```text
CSV/TXT/textarea
  -> parse_uploaded_domains
  -> resolve_network_settings
  -> AsyncSimilarClient.health_check
  -> AsyncSimilarClient.fetch pour chaque domaine
  -> split success/error rows
  -> historique + exports
```

## Circuit breaker

`rate_state.py` centralise l'etat fournisseur :

- `CLOSED` : collecte autorisee ;
- `HALF_OPEN` : reprise prudente ;
- `OPEN` : cooldown actif.

Un 403/429 repete ouvre le circuit. L'UI affiche l'etat dans la sidebar.

## Cache

Deux couches existent :

- SQLite via `cache.py`, source principale ;
- JSON legacy via `similarweb_cache.json`, conserve pour compatibilite.

Le cache stale est acceptable comme fallback, mais doit etre signale dans l'UI.

## Design system

L'app live doit conserver :

- `apply_automation_seo_theme()` ;
- `logo-sidebar-cream.png` ;
- `.tool-hero` via `render_app_hero()` ;
- `data-app-build` injecte par le theme ;
- absence des patterns `#2BAF9C`, `DR SEO`, `Dr. SEO`, `base = "light"`.

## Points de vigilance

- Ne pas confondre absence de donnees et erreur fournisseur.
- Ne pas augmenter la concurrence par defaut sans verifier le taux 403/429.
- Ne jamais exposer les proxies saisis dans les exports.
- Ne pas supprimer le fallback cache stale sans alternative UX.
