# Similarweb Free API

## Source live Automation SEO

| Element | Valeur |
|---|---|
| Live URL | https://similarweb-api.streamlit.app/ |
| Repository principal | https://github.com/Heart-Quake/Similarweb-free-API |
| Branche locale actuelle | `2026-01-23-sa97` |
| Entrypoint Streamlit | `streamlit_app.py` |
| Commande locale | `streamlit run streamlit_app.py` |
| Compilation | `python3 -m py_compile streamlit_app.py similar.py core_async.py cache.py rate_state.py automation_seo_theme.py` |
| Tests | `python3 -m pytest` |
| Secrets | Aucun secret requis par defaut. Proxies optionnels via UI. |

Documentation de reprise :

- [Contrats de donnees](docs/DATA_CONTRACTS.md)
- [Architecture](docs/ARCHITECTURE.md)
- [Runbook Streamlit](docs/RUNBOOK.md)

The Similarweb Chrome extension (or Firefox add-on) provides free access for some basic data (traffic, global and country rank, bounce rate, geo, traffic sources, screenshot, category) using an undocumented API endpoint. With [extension source viewer](https://addons.mozilla.org/hu/firefox/addon/crxviewer/), you can find the URL, which returns free data about a given domain without using any API keys. Example:

    https://data.similarweb.com/api/v1/data?domain=github.com
    
Note that subdomain requests returns the main domain statistics. We don't know what is the limitation of this API endpoint, so be careful and wait some minutes/hours when the limit reached.

**Is it legal?** Yes, the endpoint is just hidden, not forbidden. The data also available on their website, for free (so you can write a crawler also, if you don't want to use this API).

## 🚀 Features

### Optimizations for Batch Processing

This implementation now prioritizes reliable collection over speed:

- **Patient sequential batch**: one domain at a time, no async concurrency in the Streamlit batch path
- **Cache/resume first**: results are cached for 24 hours and reused before any live call
- **Configurable long delays**: the default live preset waits 60 seconds between domains
- **Plain 403 retry**: non-provider 403 responses can retry without aborting the whole batch
- **Optional guarded mode**: `preflight_check=True` and `abort_on_provider_block=True` remain available for defensive scripts

### Streamlit Interface

A complete Streamlit web interface is included with:

- **🔍 Single Domain Search**: Quick lookup for individual domains
- **📋 Batch Processing**: Upload CSV/TXT files or paste domain lists
- **📊 Results Visualization**: Interactive charts and tables
- **📥 Export Options**: Download results as CSV or JSON
- **💾 Cache Management**: Automatic caching to speed up repeated queries

## 📦 Installation

```bash
pip install -r requirements.txt
```

## 🎯 Usage

### Command Line / Python

```python
import similar

# Single domain
result = similar.similarGet('github.com')

# Batch processing
domains = ['github.com', 'stackoverflow.com', 'google.com']
results = similar.similarGetBatch(
    domains,
    delay_between_requests=60.0,  # seconds, patient mode
    use_cache=True,
    progress_callback=lambda current, total, domain, result: print(f"{current}/{total}: {domain}"),
    preflight_check=False,
    abort_on_provider_block=False,
)
```

### Streamlit Interface

```bash
streamlit run streamlit_app.py
```

Then open http://localhost:8501 in your browser.

## ⚙️ Configuration

### Cache Settings

The cache is stored in `similarweb_cache.json` and is valid for 24 hours by default. You can modify `CACHE_DURATION_HOURS` in `similar.py`.

### Rate Limiting

The API has undocumented rate limits. The implementation includes:

- Default Streamlit preset of 60 seconds between live requests
- Random delay variations to avoid patterns
- Exponential backoff on 403/429 errors
- Stable HTTP session and User-Agent per process
- Batch-level cache fallback and resume

**⚠️ Important**: Be respectful with the API. Don't make too many requests too quickly.

## 📝 File Formats

### CSV Input
- Must contain a column with domain names
- Column names can be: `domain`, `url`, `site`, `website`, `domaine`
- Or the first column will be used

### TXT Input
- One domain per line
- Can include or exclude `http://` or `https://`

## 🔧 API Functions

### `similarGet(website, use_cache=True, retry_count=3, delay_between_retries=2)`

Fetches Similarweb data for a single domain.

**Parameters:**
- `website`: URL or domain name
- `use_cache`: Use cached results if available (default: True)
- `retry_count`: Number of retry attempts on failure (default: 3)
- `delay_between_retries`: Delay between retries in seconds (default: 2)

**Returns:** Dictionary with data or False on error

### `similarGetBatch(domains, delay_between_requests=2.0, use_cache=True, progress_callback=None, preflight_check=False, abort_on_provider_block=False)`

Processes multiple domains. Default behavior is patient and sequential: the batch tries each uncached domain directly, saves cache progressively, and does not abort the full lot on the first rate-limited domain.

**Parameters:**
- `domains`: List of domains or URLs
- `delay_between_requests`: Delay between requests in seconds (default: 2.0)
- `use_cache`: Use cached results (default: True)
- `progress_callback`: Function called with (current, total, domain, result)
- `preflight_check`: Run a Similarweb healthcheck before live domains (default: False)
- `abort_on_provider_block`: Abort remaining domains after provider block detection (default: False)

**Returns:** Dictionary mapping domains to their results

## 📊 Data Structure

The API returns JSON data with the following structure:

```json
{
  "SiteName": "github.com",
  "EstimatedMonthlyVisits": {
    "2025-10-01": 500250210,
    "2025-11-01": 484288875,
    "2025-12-01": 504040936
  },
  "GlobalRank": {"Rank": 65},
  "CountryRank": {"Country": 840, "CountryCode": "US", "Rank": 92},
  "CategoryRank": {"Rank": "4", "Category": "..."},
  "Engagments": {
    "BounceRate": "0.36",
    "PagePerVisit": "6.04",
    "Visits": "504040936",
    "TimeOnSite": "378.45"
  },
  "TrafficSources": {
    "Search": 0.30,
    "Direct": 0.55,
    "Social": 0.01,
    ...
  },
  "TopCountryShares": [...],
  "Category": "..."
}
```

## ⚠️ Limitations

- Unknown rate limits (be conservative)
- Some domains may not have data available
- API endpoint is undocumented and may change
- Cache duration is 24 hours by default

## 📄 License

This project uses the Similarweb free API endpoint. Use responsibly and respect rate limits.
