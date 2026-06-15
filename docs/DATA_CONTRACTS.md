# Contrats de donnees, Similarweb Free API Cockpit

## Entrees utilisateur

L'application accepte trois modes d'entree :

- domaine unique saisi dans l'interface ;
- liste de domaines collee dans un champ texte ;
- fichier CSV ou TXT.

## Domaines

Les domaines peuvent etre fournis avec ou sans protocole.

Exemples acceptes :

- `example.com`
- `www.example.com`
- `https://www.example.com/path`

Le domaine est normalise dans `similar.extract_domain` ou `AsyncSimilarClient._extract_domain` :

- suppression du protocole ;
- suppression de `www.` ;
- suppression du path, query string et fragment ;
- passage en minuscules.

## CSV d'entree

Pour les imports CSV, `parse_uploaded_domains` cherche une colonne dont le nom contient :

- `domain`
- `url`
- `site`
- `website`
- `domaine`

Si aucune colonne ne matche, la premiere colonne est utilisee.

## TXT d'entree

Un domaine par ligne. Les lignes vides sont ignorees.

## Donnees Similarweb

L'endpoint non officiel retourne un JSON dont les champs utiles peuvent inclure :

- `SiteName`
- `EstimatedMonthlyVisits`
- `GlobalRank`
- `CountryRank`
- `CategoryRank`
- `Engagments`
- `TrafficSources`
- `TopCountryShares`
- `Category`
- `Screenshot`

Tous les champs doivent etre traites comme optionnels. Certaines reponses ne contiennent pas de donnees exploitables.

## Sources et cache

Les payloads peuvent provenir de :

- API live ;
- cache SQLite frais ;
- cache SQLite stale en fallback apres blocage fournisseur ;
- ancien cache JSON, conserve pour compatibilite.

Les metadonnees internes utilisent notamment :

- `_source`
- `_cache_status`
- `_fetched_at`
- `_fallback_reason`
- `status_code`
- `error_kind`

Ces champs servent a l'UI et au diagnostic, mais ne doivent pas etre presentes comme donnees Similarweb brutes.

## Sorties

L'interface produit :

- cartes de synthese domaine ;
- tableaux batch ;
- graphiques traffic sources, pays, visites, engagement ;
- exports CSV/JSON via `ui_exports.py` ;
- historique local des domaines consultes.

## Fichiers runtime

Ne pas versionner :

- `similarweb_cache.db*`
- `similarweb_cache.json`
- `similarweb_history.json`
- `.runtime/`
- `streamlit.log`
- exports CSV/XLSX clients.

## Limites

- L'API est non documentee et peut changer sans preavis.
- Les limites de rate limit sont inconnues.
- Les erreurs 403/429 doivent etre interpretees comme blocage fournisseur probable.
- Les donnees Similarweb gratuites sont indicatives, pas une source de mesure analytics.
