try:
    from requests import get, Session
    from urllib.parse import urlparse
    import time
    import random
    import json
    import os
    from datetime import datetime, timedelta
except ImportError as err:
    print(f"Failed to import required modules {err}")

# Liste de User-Agents pour rotation
USER_AGENTS = [
    'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
    'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
    'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/119.0.0.0 Safari/537.36',
    'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.1 Safari/605.1.15',
    'Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
    'Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:121.0) Gecko/20100101 Firefox/121.0',
    'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36 Edg/120.0.0.0',
]

# Cache pour éviter les requêtes répétées
CACHE_FILE = 'similarweb_cache.json'
CACHE_DURATION_HOURS = 24  # Durée de validité du cache en heures

# Fichier pour stocker les données historiques
HISTORY_FILE = 'similarweb_history.json'
HISTORY_LIMIT_PER_DOMAIN = 1000  # Nombre maximum d'entrées historiques par domaine

def load_cache():
    """Charge le cache depuis le fichier"""
    if os.path.exists(CACHE_FILE):
        try:
            with open(CACHE_FILE, 'r', encoding='utf-8') as f:
                return json.load(f)
        except:
            return {}
    return {}

def save_cache(cache):
    """Sauvegarde le cache dans le fichier"""
    try:
        with open(CACHE_FILE, 'w', encoding='utf-8') as f:
            json.dump(cache, f, indent=2, ensure_ascii=False)
    except Exception as e:
        print(f"Erreur lors de la sauvegarde du cache: {e}")

def is_cache_valid(timestamp, duration_hours=CACHE_DURATION_HOURS):
    """Vérifie si une entrée du cache est encore valide"""
    cache_time = datetime.fromisoformat(timestamp)
    return datetime.now() - cache_time < timedelta(hours=duration_hours)

def get_random_user_agent():
    """Retourne un User-Agent aléatoire"""
    return random.choice(USER_AGENTS)

def extract_domain(website):
    """Extrait et nettoie le domaine depuis une URL ou un nom de domaine"""
    parsed = urlparse(website)
    domain = parsed.netloc if parsed.netloc else parsed.path.split('/')[0]
    domain = domain.replace("www.", "")
    domain = domain.split('/')[0].split('?')[0].lower().strip()
    return domain

def similarGet(website, use_cache=True, retry_count=3, delay_between_retries=2):
    """
    Récupère les données Similarweb pour un domaine
    
    Args:
        website: URL ou nom de domaine
        use_cache: Utiliser le cache si disponible
        retry_count: Nombre de tentatives en cas d'échec
        delay_between_retries: Délai entre les tentatives (secondes)
    
    Returns:
        dict: Données JSON ou False en cas d'erreur
    """
    domain = extract_domain(website)
    
    # Vérifier le cache
    if use_cache:
        cache = load_cache()
        if domain in cache:
            cache_entry = cache[domain]
            if is_cache_valid(cache_entry.get('timestamp', '')):
                return cache_entry.get('data')
    
    ENDPOINT = 'https://data.similarweb.com/api/v1/data?domain=' + domain
    
    # Délai initial avec variation aléatoire pour éviter les requêtes simultanées
    base_delay = random.uniform(1.0, 3.0)
    time.sleep(base_delay)
    
    for attempt in range(retry_count):
        try:
            # Rotation du User-Agent
            headers = {
                'User-Agent': get_random_user_agent(),
                'Accept': 'application/json, text/plain, */*',
                'Accept-Language': 'en-US,en;q=0.9',
                'Referer': 'https://www.similarweb.com/',
                'Accept-Encoding': 'gzip, deflate, br',
                'Connection': 'keep-alive',
                'Upgrade-Insecure-Requests': '1'
            }
            
            resp = get(ENDPOINT, headers=headers, timeout=30)
            
            # Gestion des différents codes de statut
            if resp.status_code == 200:
                data = resp.json()
                
                # Sauvegarder dans le cache
                if use_cache:
                    cache = load_cache()
                    cache[domain] = {
                        'data': data,
                        'timestamp': datetime.now().isoformat()
                    }
                    save_cache(cache)
                
                # Sauvegarder dans l'historique
                save_to_history(domain, data)
                
                return data
            
            elif resp.status_code == 403:
                # Rate limit ou accès refusé
                wait_time = delay_between_retries * (2 ** attempt) + random.uniform(5, 15)
                print(f"⚠️ 403 Forbidden pour {domain}. Attente de {wait_time:.1f}s avant nouvelle tentative...")
                time.sleep(wait_time)
                continue
            
            elif resp.status_code == 429:
                # Trop de requêtes
                wait_time = delay_between_retries * (2 ** attempt) + random.uniform(10, 30)
                print(f"⚠️ 429 Too Many Requests pour {domain}. Attente de {wait_time:.1f}s...")
                time.sleep(wait_time)
                continue
            
            elif resp.status_code == 404:
                # Domaine non trouvé
                return {'error': 'Domain not found', 'domain': domain}
            
            else:
                resp.raise_for_status()
                
        except Exception as e:
            if attempt < retry_count - 1:
                wait_time = delay_between_retries * (2 ** attempt)
                print(f"❌ Erreur pour {domain} (tentative {attempt + 1}/{retry_count}): {str(e)}")
                print(f"   Attente de {wait_time}s avant nouvelle tentative...")
                time.sleep(wait_time)
            else:
                print(f"❌ Échec définitif pour {domain}: {str(e)}")
                return False
    
    return False

def similarGetBatch(domains, delay_between_requests=2.0, use_cache=True, progress_callback=None, chunk_size=100):
    """
    Récupère les données pour plusieurs domaines
    
    Args:
        domains: Liste de domaines ou URLs
        delay_between_requests: Délai entre chaque requête (secondes)
        use_cache: Utiliser le cache
        progress_callback: Fonction appelée avec (current, total, domain, result)
        chunk_size: Taille des chunks pour traiter par lots (défaut: 100)
    
    Returns:
        dict: {domain: data} ou {domain: False/error}
    """
    results = {}
    total = len(domains)
    
    # Traiter par chunks pour éviter les problèmes de mémoire et rate limiting
    for chunk_start in range(0, total, chunk_size):
        chunk_end = min(chunk_start + chunk_size, total)
        chunk_domains = domains[chunk_start:chunk_end]
        
        for idx, domain in enumerate(chunk_domains, 1):
            domain_clean = extract_domain(domain)
            current_idx = chunk_start + idx
            
            if progress_callback:
                progress_callback(current_idx, total, domain_clean, None)
            
            result = similarGet(domain, use_cache=use_cache)
            results[domain_clean] = result
            
            # Délai entre les requêtes (sauf pour la dernière)
            if current_idx < total:
                delay = delay_between_requests + random.uniform(-0.5, 0.5)
                time.sleep(delay)
        
        # Pause supplémentaire entre les chunks pour éviter le rate limiting
        if chunk_end < total:
            chunk_delay = delay_between_requests * 2
            time.sleep(chunk_delay)
    
    return results

# ========== FONCTIONS POUR LA PÉRIODICITÉ ==========

def load_history():
    """Charge l'historique des données depuis le fichier"""
    if os.path.exists(HISTORY_FILE):
        try:
            with open(HISTORY_FILE, 'r', encoding='utf-8') as f:
                return json.load(f)
        except:
            return {}
    return {}

def save_history(history):
    """Sauvegarde l'historique dans le fichier"""
    try:
        with open(HISTORY_FILE, 'w', encoding='utf-8') as f:
            json.dump(history, f, indent=2, ensure_ascii=False)
    except Exception as e:
        print(f"Erreur lors de la sauvegarde de l'historique: {e}")

def save_to_history(domain, data, period_label=None):
    """
    Sauvegarde les données dans l'historique avec timestamp
    
    Args:
        domain: Nom du domaine
        data: Données à sauvegarder
        period_label: Label optionnel pour la période (ex: "2025-01", "Q1-2025")
    """
    if not data or isinstance(data, bool):
        return
    
    history = load_history()
    domain_clean = extract_domain(domain)
    timestamp = datetime.now().isoformat()
    
    if domain_clean not in history:
        history[domain_clean] = []
    
    # Préparer les données à sauvegarder
    history_entry = {
        'timestamp': timestamp,
        'date': datetime.now().strftime('%Y-%m-%d'),
        'period': period_label or datetime.now().strftime('%Y-%m'),
        'data': data
    }
    
    history[domain_clean].append(history_entry)
    
    # Garder seulement les N dernières entrées par domaine
    history[domain_clean] = history[domain_clean][-HISTORY_LIMIT_PER_DOMAIN:]
    
    save_history(history)

def get_history_for_domain(domain, start_date=None, end_date=None, period=None):
    """
    Récupère l'historique pour un domaine
    
    Args:
        domain: Nom du domaine
        start_date: Date de début (datetime ou string ISO)
        end_date: Date de fin (datetime ou string ISO)
        period: Période spécifique (ex: "2025-01")
    
    Returns:
        list: Liste des entrées historiques
    """
    history = load_history()
    domain_clean = extract_domain(domain)
    
    if domain_clean not in history:
        return []
    
    entries = history[domain_clean]
    
    # Filtrer par période si spécifiée
    if period:
        entries = [e for e in entries if e.get('period') == period]
    
    # Filtrer par dates si spécifiées
    if start_date or end_date:
        filtered = []
        for entry in entries:
            entry_date = datetime.fromisoformat(entry['timestamp'])
            
            if start_date:
                if isinstance(start_date, str):
                    start_date = datetime.fromisoformat(start_date)
                if entry_date < start_date:
                    continue
            
            if end_date:
                if isinstance(end_date, str):
                    end_date = datetime.fromisoformat(end_date)
                if entry_date > end_date:
                    continue
            
            filtered.append(entry)
        
        entries = filtered
    
    # Trier par timestamp
    entries.sort(key=lambda x: x['timestamp'])
    
    return entries

def get_all_domains_in_history():
    """Retourne la liste de tous les domaines dans l'historique"""
    history = load_history()
    return list(history.keys())

def compare_periods(domain, period1, period2):
    """
    Compare les données entre deux périodes
    
    Args:
        domain: Nom du domaine
        period1: Première période (ex: "2025-01")
        period2: Deuxième période (ex: "2025-02")
    
    Returns:
        dict: Comparaison des deux périodes
    """
    history1 = get_history_for_domain(domain, period=period1)
    history2 = get_history_for_domain(domain, period=period2)
    
    if not history1 or not history2:
        return None
    
    data1 = history1[-1]['data']  # Dernière entrée de la période 1
    data2 = history2[-1]['data']  # Dernière entrée de la période 2
    
    comparison = {
        'domain': domain,
        'period1': period1,
        'period2': period2,
        'data1': data1,
        'data2': data2,
        'changes': {}
    }
    
    # Comparer les visites mensuelles
    if 'EstimatedMonthlyVisits' in data1 and 'EstimatedMonthlyVisits' in data2:
        visits1 = data1['EstimatedMonthlyVisits']
        visits2 = data2['EstimatedMonthlyVisits']
        
        if isinstance(visits1, dict) and isinstance(visits2, dict):
            latest1 = list(visits1.values())[-1] if visits1 else 0
            latest2 = list(visits2.values())[-1] if visits2 else 0
            
            if latest1 > 0:
                change_pct = ((latest2 - latest1) / latest1) * 100
                comparison['changes']['visits'] = {
                    'period1': latest1,
                    'period2': latest2,
                    'change': latest2 - latest1,
                    'change_percent': change_pct
                }
    
    # Comparer le classement
    if 'GlobalRank' in data1 and 'GlobalRank' in data2:
        rank1 = data1['GlobalRank'].get('Rank', 0) if isinstance(data1['GlobalRank'], dict) else data1['GlobalRank']
        rank2 = data2['GlobalRank'].get('Rank', 0) if isinstance(data2['GlobalRank'], dict) else data2['GlobalRank']
        
        if rank1 and rank2:
            comparison['changes']['rank'] = {
                'period1': rank1,
                'period2': rank2,
                'change': rank2 - rank1  # Positif = baisse de classement
            }
    
    return comparison
    