# Similarweb Free API

The Similarweb Chrome extension (or Firefox add-on) provides free access for some basic data (traffic, global and country rank, bounce rate, geo, traffic sources, screenshot, category) using an undocumented API endpoint. With [extension source viewer](https://addons.mozilla.org/hu/firefox/addon/crxviewer/), you can find the URL, which returns free data about a given domain without using any API keys. Example:

    https://data.similarweb.com/api/v1/data?domain=github.com
    
Note that subdomain requests returns the main domain statistics. We don't know what is the limitation of this API endpoint, so be careful and wait some minutes/hours when the limit reached.

**Is it legal?** Yes, the endpoint is just hidden, not forbidden. The data also available on their website, for free (so you can write a crawler also, if you don't want to use this API).

## 🚀 Features

### Optimizations for Batch Processing

This implementation includes several optimizations to handle large lists of domains:

- **🔄 User-Agent Rotation**: Automatically rotates between different User-Agents to avoid detection
- **💾 Caching System**: Results are cached for 24 hours to avoid redundant API calls
- **⏱️ Intelligent Delays**: Configurable delays between requests with random variations
- **🔄 Automatic Retry**: Exponential backoff retry mechanism for 403/429 errors
- **📊 Batch Processing**: Process multiple domains efficiently with progress tracking

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
    delay_between_requests=2.0,  # seconds
    use_cache=True,
    progress_callback=lambda current, total, domain, result: print(f"{current}/{total}: {domain}")
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

- Default delay of 2 seconds between requests (configurable)
- Random delay variations to avoid patterns
- Exponential backoff on 403/429 errors
- User-Agent rotation

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

### `similarGetBatch(domains, delay_between_requests=2.0, use_cache=True, progress_callback=None)`

Processes multiple domains.

**Parameters:**
- `domains`: List of domains or URLs
- `delay_between_requests`: Delay between requests in seconds (default: 2.0)
- `use_cache`: Use cached results (default: True)
- `progress_callback`: Function called with (current, total, domain, result)

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
