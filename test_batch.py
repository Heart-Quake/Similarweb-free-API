#!/usr/bin/env python3
"""
Script de test pour le traitement par lots
"""
import similar
import time

def test_batch_processing():
    """Test le traitement par lots avec quelques domaines"""
    print("🧪 Test du traitement par lots Similarweb\n")
    
    # Liste de test
    test_domains = [
        'github.com',
        'stackoverflow.com',
        'google.com'
    ]
    
    print(f"📋 Domaines à tester: {len(test_domains)}")
    for domain in test_domains:
        print(f"   - {domain}")
    print()
    
    # Callback de progression
    def progress(current, total, domain, result):
        status = "✅" if result and isinstance(result, dict) and 'error' not in result else "⏳"
        print(f"{status} [{current}/{total}] {domain}")
    
    # Traitement
    start_time = time.time()
    results = similar.similarGetBatch(
        test_domains,
        delay_between_requests=2.0,
        use_cache=True,
        progress_callback=progress
    )
    elapsed_time = time.time() - start_time
    
    # Résultats
    print(f"\n📊 Résultats:")
    success_count = 0
    error_count = 0
    
    for domain, data in results.items():
        if data and isinstance(data, dict) and 'error' not in data:
            success_count += 1
            visits = 0
            if 'EstimatedMonthlyVisits' in data:
                visits_dict = data['EstimatedMonthlyVisits']
                if isinstance(visits_dict, dict):
                    visits = list(visits_dict.values())[-1] if visits_dict else 0
                else:
                    visits = visits_dict
            
            rank = 'N/A'
            if 'GlobalRank' in data and isinstance(data['GlobalRank'], dict):
                rank = data['GlobalRank'].get('Rank', 'N/A')
            
            print(f"   ✅ {domain}: {visits:,} visites/mois, Rank #{rank}")
        else:
            error_count += 1
            error_msg = data.get('error', 'Erreur inconnue') if isinstance(data, dict) else 'Erreur'
            print(f"   ❌ {domain}: {error_msg}")
    
    print(f"\n⏱️  Temps total: {elapsed_time:.1f}s")
    print(f"✅ Succès: {success_count}/{len(test_domains)}")
    print(f"❌ Erreurs: {error_count}/{len(test_domains)}")
    
    return results

if __name__ == "__main__":
    test_batch_processing()
