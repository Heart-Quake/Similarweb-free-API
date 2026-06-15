# Runbook, Similarweb Free API Cockpit

## Source live

| Element | Valeur |
|---|---|
| Live URL | https://similarweb-api.streamlit.app/ |
| Repository | `Heart-Quake/Similarweb-free-API` |
| Branche locale observee | `2026-01-23-sa97` |
| Entrypoint | `streamlit_app.py` |
| Build marker attendu | `Similarweb-free-API:<commit>` ou equivalent `data-app-build` |

## Commandes locales

```bash
cd /Users/vincentflaceliere/Github/Similarweb-free-API
python3 -m venv .venv
source .venv/bin/activate
python -m pip install -r requirements.txt
streamlit run streamlit_app.py
```

Verification :

```bash
python3 -m py_compile streamlit_app.py similar.py core_async.py cache.py rate_state.py automation_seo_theme.py
python3 -m pytest
```

## Smoke test live

Dans l'app Streamlit :

- `.tool-hero` present ;
- `.sidebar-logo img` present ;
- `data-app-build` present ;
- un domaine simple comme `github.com` charge sans traceback ;
- le mode batch accepte un TXT court ;
- les erreurs 403/429 affichent un message utilisateur clair ;
- les exports ne contiennent pas de secrets proxy.

## Incident 403 / 429

Symptomes :

- beaucoup de domaines en erreur ;
- messages `provider blocked`, `HTTP 403`, `HTTP 429` ;
- circuit breaker en `OPEN` ;
- fallback cache stale visible.

Actions :

1. Ne pas relancer un batch massif immediatement.
2. Verifier le cooldown affiche dans la sidebar.
3. Reduire concurrence et cadence.
4. Utiliser le cache si la donnee fraiche n'est pas obligatoire.
5. Si besoin, tester avec proxies propres et limites explicites.

## Cache corrompu

Symptomes :

- erreurs SQLite ;
- donnees incoherentes ;
- historique qui ne s'affiche plus.

Actions locales :

```bash
rm -f similarweb_cache.db similarweb_cache.db-shm similarweb_cache.db-wal
rm -f verify_cache.db
```

Ne pas supprimer le cache live sans avoir confirme que l'app peut reconstruire les donnees.

## Build Streamlit

Verifier :

- `requirements.txt` inclut les dependances UI et async ;
- pas de dependance systeme non disponible sur Streamlit Community Cloud ;
- pas de fichier runtime versionne ;
- `automation_seo_theme.py` et `logo-sidebar-cream.png` presents.
