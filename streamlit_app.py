import streamlit as st
import similar
import json
import pandas as pd
from datetime import datetime, timedelta
import io
import time

from automation_seo_theme import apply_automation_seo_theme

# Configuration de la page
st.set_page_config(
    page_title="Similarweb Free API",
    page_icon="📊",
    layout="wide"
)
apply_automation_seo_theme()

st.markdown(
    """
    <section class="tool-hero">
        <div class="tool-kicker">Traffic intelligence</div>
        <h1 class="tool-title">Similarweb Free API Cockpit</h1>
        <p class="tool-lead">
            Analyse un domaine ou une liste de domaines avec les données publiques Similarweb :
            trafic estimé, engagement, sources, géographie et historique.
        </p>
    </section>
    """,
    unsafe_allow_html=True,
)

# Sidebar avec informations
with st.sidebar:
    with st.expander("Informations", expanded=False):
        st.markdown("""
        **Données disponibles :** trafic, classement, engagement, géographie, sources et catégorie.

        **Robustesse :** rotation User-Agent, cache 24h, délais entre requêtes et retry automatique.
        """)

# ========== DÉFINITIONS DES FONCTIONS ==========

def display_single_result(result):
    """Affiche les résultats pour un seul domaine"""
    st.header("📈 Résultats")
    
    # Création de colonnes pour l'affichage
    col1, col2, col3, col4 = st.columns(4)
    
    # Trafic estimé (dernière valeur disponible)
    if 'EstimatedMonthlyVisits' in result:
        visits = result['EstimatedMonthlyVisits']
        if isinstance(visits, dict):
            latest_visits = list(visits.values())[-1] if visits else 0
        else:
            latest_visits = visits
        with col1:
            st.metric("Visites mensuelles estimées", f"{int(latest_visits):,}".replace(",", " "))
    
    # Classement global
    if 'GlobalRank' in result and isinstance(result['GlobalRank'], dict):
        rank = result['GlobalRank'].get('Rank', 'N/A')
        with col2:
            st.metric("Classement global", f"#{rank:,}".replace(",", " ") if isinstance(rank, int) else f"#{rank}")
    elif 'GlobalRank' in result:
        with col2:
            st.metric("Classement global", f"#{result['GlobalRank']:,}".replace(",", " "))
    
    # Taux de rebond
    if 'Engagments' in result and isinstance(result['Engagments'], dict):
        bounce_rate = result['Engagments'].get('BounceRate', 0)
        with col3:
            st.metric("Taux de rebond", f"{float(bounce_rate) * 100:.2f}%")
    
    # Pages par visite
    if 'Engagments' in result and isinstance(result['Engagments'], dict):
        pages_per_visit = result['Engagments'].get('PagePerVisit', 0)
        with col4:
            st.metric("Pages par visite", f"{float(pages_per_visit):.2f}")
    
    st.markdown("---")
    
    # Informations détaillées
    tabs = st.tabs(["🌍 Géographie", "📊 Sources de trafic", "📱 Appareils", "📄 Données brutes"])
    
    # Onglet Géographie
    with tabs[0]:
        if 'TopCountryShares' in result and result['TopCountryShares']:
            st.subheader("Répartition géographique du trafic")
            countries_data = []
            for country in result['TopCountryShares']:
                country_code = country.get('CountryCode', 'N/A')
                value = country.get('Value', 0)
                countries_data.append({
                    'Pays': country_code,
                    'Part du trafic (%)': f"{value * 100:.2f}%",
                    'Valeur': value * 100
                })
            
            df_countries = pd.DataFrame(countries_data)
            df_countries_sorted = df_countries.sort_values('Valeur', ascending=False)
            
            st.dataframe(df_countries_sorted[['Pays', 'Part du trafic (%)']], use_container_width=True, hide_index=True)
            
            if len(df_countries_sorted) > 0:
                st.bar_chart(df_countries_sorted.set_index('Pays')['Valeur'], height=400)
        else:
            st.info("Aucune donnée géographique disponible")
    
    # Onglet Sources de trafic
    with tabs[1]:
        if 'TrafficSources' in result:
            sources = result['TrafficSources']
            col1, col2 = st.columns(2)
            
            source_names = {
                'Search': 'Recherche',
                'Social': 'Réseaux sociaux',
                'Mail': 'Email',
                'Direct': 'Direct',
                'Referrals': 'Référents',
                'Paid Referrals': 'Référents payants',
                'Paid': 'Payant'
            }
            
            sources_list = list(sources.items())
            mid = len(sources_list) // 2
            
            with col1:
                for key, value in sources_list[:mid]:
                    name = source_names.get(key, key)
                    if value > 0:
                        st.metric(name, f"{value * 100:.2f}%")
            
            with col2:
                for key, value in sources_list[mid:]:
                    name = source_names.get(key, key)
                    if value > 0:
                        st.metric(name, f"{value * 100:.2f}%")
            
            if sources:
                sources_data = {source_names.get(k, k): v * 100 for k, v in sources.items() if v > 0}
                if sources_data:
                    df_sources = pd.DataFrame({
                        'Source': list(sources_data.keys()),
                        'Pourcentage': list(sources_data.values())
                    })
                    st.bar_chart(df_sources.set_index('Source')['Pourcentage'], height=300)
        else:
            st.info("Aucune donnée sur les sources de trafic disponible")
    
    # Onglet Appareils
    with tabs[2]:
        if 'TrafficShare' in result:
            devices = result['TrafficShare']
            col1, col2, col3 = st.columns(3)
            
            with col1:
                if 'Desktop' in devices:
                    val = devices['Desktop']
                    st.metric("Desktop", f"{val * 100:.2f}%" if val < 1 else f"{val:.2f}%")
            with col2:
                if 'Mobile' in devices:
                    val = devices['Mobile']
                    st.metric("Mobile", f"{val * 100:.2f}%" if val < 1 else f"{val:.2f}%")
            with col3:
                if 'Tablet' in devices:
                    val = devices['Tablet']
                    st.metric("Tablette", f"{val * 100:.2f}%" if val < 1 else f"{val:.2f}%")
            
            if devices:
                devices_data = {k: (v * 100 if v < 1 else v) for k, v in devices.items() if v > 0}
                if devices_data:
                    df_devices = pd.DataFrame({
                        'Appareil': list(devices_data.keys()),
                        'Pourcentage': list(devices_data.values())
                    })
                    st.bar_chart(df_devices.set_index('Appareil')['Pourcentage'], height=300)
        else:
            st.info("Aucune donnée sur les appareils disponible")
            if 'Engagments' in result:
                st.subheader("Données d'engagement disponibles")
                eng = result['Engagments']
                if 'Visits' in eng:
                    st.metric("Visites", f"{int(eng['Visits']):,}".replace(",", " "))
                if 'TimeOnSite' in eng:
                    st.metric("Temps sur le site (secondes)", f"{float(eng['TimeOnSite']):.2f}s")
    
    # Onglet Données brutes
    with tabs[3]:
        st.subheader("Données JSON complètes")
        st.json(result)
        
        json_str = json.dumps(result, indent=2, ensure_ascii=False)
        domain_name = result.get('SiteName', result.get('Domain', 'data'))
        st.download_button(
            label="📥 Télécharger les données JSON",
            data=json_str,
            file_name=f"similarweb_{domain_name}_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json",
            mime="application/json"
        )

def analyze_batch_period(domains_list, period_start, period_end):
    """Analyse les données historiques sur une période définie"""
    st.header("📊 Analyse par période")
    st.info(f"Analyse des données historiques du {period_start.strftime('%d/%m/%Y')} au {period_end.strftime('%d/%m/%Y')}")
    
    results_data = []
    domains_with_data = 0
    domains_without_data = 0
    
    progress_bar = st.progress(0)
    status_text = st.empty()
    
    for idx, domain in enumerate(domains_list, 1):
        domain_clean = similar.extract_domain(domain)
        progress = idx / len(domains_list)
        progress_bar.progress(progress)
        status_text.info(f"Analyse de {domain_clean} ({idx}/{len(domains_list)})...")
        
        # Récupérer l'historique pour cette période
        # Convertir les dates en datetime pour la fonction
        start_datetime = datetime.combine(period_start, datetime.min.time())
        end_datetime = datetime.combine(period_end, datetime.max.time())
        
        history_entries = similar.get_history_for_domain(
            domain_clean,
            start_date=start_datetime,
            end_date=end_datetime
        )
        
        if not history_entries:
            domains_without_data += 1
            row = {
                'Domaine': domain_clean,
                'Statut': '⚠️ Aucune donnée historique',
                'Période': f"{period_start.strftime('%d/%m/%Y')} - {period_end.strftime('%d/%m/%Y')}"
            }
            results_data.append(row)
            continue
        
        domains_with_data += 1
        
        # Calculer les statistiques sur la période
        visits_list = []
        ranks_list = []
        bounce_rates = []
        pages_per_visit_list = []
        duration_list = []
        direct_traffic = []
        organic_traffic = []
        paid_traffic = []
        social_traffic = []
        email_traffic = []
        
        for entry in history_entries:
            data = entry['data']
            
            # Visites
            if 'EstimatedMonthlyVisits' in data:
                visits = data['EstimatedMonthlyVisits']
                if isinstance(visits, dict):
                    latest_visits = list(visits.values())[-1] if visits else 0
                else:
                    latest_visits = visits
                visits_list.append(int(latest_visits) if latest_visits else 0)
            
            # Classement
            if 'GlobalRank' in data:
                if isinstance(data['GlobalRank'], dict):
                    rank = data['GlobalRank'].get('Rank', 0)
                else:
                    rank = data['GlobalRank']
                ranks_list.append(rank if rank else 0)
            
            # Engagement
            if 'Engagments' in data and isinstance(data['Engagments'], dict):
                bounce = data['Engagments'].get('BounceRate', 0)
                if bounce:
                    bounce_rates.append(float(bounce) * 100)
                
                pages = data['Engagments'].get('PagePerVisit', 0)
                if pages:
                    pages_per_visit_list.append(float(pages))
                
                time_site = data['Engagments'].get('TimeOnSite', 0)
                if time_site:
                    duration_list.append(float(time_site) / 60)  # En minutes
            
            # Sources de trafic
            if 'TrafficSources' in data and isinstance(data['TrafficSources'], dict):
                sources = data['TrafficSources']
                if sources.get('Direct'):
                    direct_traffic.append(float(sources['Direct']) * 100)
                if sources.get('Search'):
                    organic_traffic.append(float(sources['Search']) * 100)
                if sources.get('Paid') or sources.get('Paid Referrals'):
                    paid = float(sources.get('Paid', 0)) + float(sources.get('Paid Referrals', 0))
                    paid_traffic.append(paid * 100)
                if sources.get('Social'):
                    social_traffic.append(float(sources['Social']) * 100)
                if sources.get('Mail'):
                    email_traffic.append(float(sources['Mail']) * 100)
        
        # Créer la ligne de résultats avec statistiques
        row = {'Domaine': domain_clean}
        
        # Visites - moyenne, min, max
        if visits_list:
            row['Visites moyennes (M)'] = round(sum(visits_list) / len(visits_list) / 1_000_000, 2)
            row['Visites min (M)'] = round(min(visits_list) / 1_000_000, 2)
            row['Visites max (M)'] = round(max(visits_list) / 1_000_000, 2)
            row['Évolution visites (%)'] = round(((visits_list[-1] - visits_list[0]) / visits_list[0] * 100) if visits_list[0] > 0 else 0, 2)
        else:
            row['Visites moyennes (M)'] = 0
            row['Visites min (M)'] = 0
            row['Visites max (M)'] = 0
            row['Évolution visites (%)'] = 0
        
        # Classement - moyenne, évolution
        if ranks_list:
            row['Classement moyen'] = round(sum(ranks_list) / len(ranks_list))
            row['Classement min'] = min(ranks_list)
            row['Classement max'] = max(ranks_list)
            row['Évolution classement'] = ranks_list[-1] - ranks_list[0]
        else:
            row['Classement moyen'] = 'N/A'
            row['Classement min'] = 'N/A'
            row['Classement max'] = 'N/A'
            row['Évolution classement'] = 'N/A'
        
        # Taux de rebond - moyenne
        if bounce_rates:
            row['Taux rebond moyen (%)'] = round(sum(bounce_rates) / len(bounce_rates), 2)
        else:
            row['Taux rebond moyen (%)'] = 0
        
        # Pages par visite - moyenne
        if pages_per_visit_list:
            row['Pages/visite moyenne'] = round(sum(pages_per_visit_list) / len(pages_per_visit_list), 2)
        else:
            row['Pages/visite moyenne'] = 0
        
        # Durée - moyenne
        if duration_list:
            row['Durée moyenne (min)'] = round(sum(duration_list) / len(duration_list), 2)
        else:
            row['Durée moyenne (min)'] = 0
        
        # Trafic direct - moyenne
        if direct_traffic:
            row['Trafic direct moyen (%)'] = round(sum(direct_traffic) / len(direct_traffic), 2)
        else:
            row['Trafic direct moyen (%)'] = 0
        
        # Trafic organique - moyenne
        if organic_traffic:
            row['Trafic organique moyen (%)'] = round(sum(organic_traffic) / len(organic_traffic), 2)
        else:
            row['Trafic organique moyen (%)'] = 0
        
        # Trafic payant - moyenne
        if paid_traffic:
            row['Trafic payant moyen (%)'] = round(sum(paid_traffic) / len(paid_traffic), 2)
        else:
            row['Trafic payant moyen (%)'] = 0
        
        # Trafic social - moyenne
        if social_traffic:
            row['Trafic social moyen (%)'] = round(sum(social_traffic) / len(social_traffic), 2)
        else:
            row['Trafic social moyen (%)'] = 0
        
        # Trafic email - moyenne
        if email_traffic:
            row['Trafic email moyen (%)'] = round(sum(email_traffic) / len(email_traffic), 2)
        else:
            row['Trafic email moyen (%)'] = 0
        
        row['Nb points de données'] = len(history_entries)
        row['Période'] = f"{period_start.strftime('%d/%m/%Y')} - {period_end.strftime('%d/%m/%Y')}"
        
        results_data.append(row)
    
    progress_bar.progress(1.0)
    status_text.empty()
    
    # Affichage des résultats
    st.markdown("---")
    st.header("📊 Résultats de l'analyse par période")
    
    # Statistiques
    col1, col2, col3 = st.columns(3)
    with col1:
        st.metric("✅ Domaines avec données", domains_with_data)
    with col2:
        st.metric("⚠️ Domaines sans données", domains_without_data)
    with col3:
        st.metric("📦 Total", len(domains_list))
    
    if results_data:
        df_results = pd.DataFrame(results_data)
        
        # Définir l'ordre des colonnes
        column_order = [
            'Domaine',
            'Période',
            'Nb points de données',
            'Visites moyennes (M)',
            'Visites min (M)',
            'Visites max (M)',
            'Évolution visites (%)',
            'Classement moyen',
            'Classement min',
            'Classement max',
            'Évolution classement',
            'Taux rebond moyen (%)',
            'Pages/visite moyenne',
            'Durée moyenne (min)',
            'Trafic direct moyen (%)',
            'Trafic organique moyen (%)',
            'Trafic payant moyen (%)',
            'Trafic social moyen (%)',
            'Trafic email moyen (%)',
            'Statut'
        ]
        
        available_columns = [col for col in column_order if col in df_results.columns]
        other_columns = [col for col in df_results.columns if col not in column_order]
        final_column_order = available_columns + other_columns
        
        df_results = df_results[final_column_order]
        st.dataframe(df_results, use_container_width=True, hide_index=True)
        
        # Export
        st.markdown("---")
        st.subheader("📥 Export des résultats")
        col_export1, col_export2 = st.columns(2)
        
        with col_export1:
            csv = df_results.to_csv(index=False, encoding='utf-8-sig')
            st.download_button(
                label="📥 Télécharger CSV",
                data=csv,
                file_name=f"similarweb_period_analysis_{period_start.strftime('%Y%m%d')}_{period_end.strftime('%Y%m%d')}.csv",
                mime="text/csv"
            )
        
        with col_export2:
            json_data = json.dumps(results_data, indent=2, ensure_ascii=False)
            st.download_button(
                label="📥 Télécharger JSON",
                data=json_data,
                file_name=f"similarweb_period_analysis_{period_start.strftime('%Y%m%d')}_{period_end.strftime('%Y%m%d')}.json",
                mime="application/json"
            )
    else:
        st.warning("⚠️ Aucune donnée historique trouvée pour les domaines sélectionnés sur cette période.")

def process_batch(domains_list, delay, use_cache, retry_count, chunk_size=100):
    """Traite une liste de domaines par lots"""
    total = len(domains_list)
    results = {}
    progress_bar = st.progress(0)
    status_text = st.empty()
    
    # Container pour les résultats
    results_container = st.container()
    
    # Statistiques
    stats = {'success': 0, 'error': 0, 'cached': 0}
    
    def progress_callback(current, total_domains, domain, result):
        progress = current / total_domains
        progress_bar.progress(progress)
        
        # Ne pas compter ici - on comptera après avoir analysé toutes les données
        # Juste afficher le statut
        if result and not isinstance(result, bool):
            if isinstance(result, dict):
                if 'error' in result:
                    error_msg = result.get('error', 'Erreur inconnue')
                    status_text.warning(f"⚠️ [{current}/{total_domains}] {domain} - {error_msg}")
                else:
                    status_text.success(f"✅ [{current}/{total_domains}] {domain} - Succès")
            else:
                status_text.info(f"⏳ [{current}/{total_domains}] {domain} - Traitement...")
        else:
            status_text.warning(f"⚠️ [{current}/{total_domains}] {domain} - En attente...")
    
    # Traitement
    with st.spinner(f"Traitement de {total} domaine(s) en cours..."):
        try:
            results = similar.similarGetBatch(
                domains_list,
                delay_between_requests=delay,
                use_cache=use_cache,
                progress_callback=progress_callback,
                chunk_size=chunk_size
            )
        except Exception as e:
            st.error(f"❌ Erreur lors du traitement : {str(e)}")
            return
    
    progress_bar.progress(1.0)
    status_text.empty()
    
    # Affichage des résultats
    with results_container:
        st.markdown("---")
        st.header("📊 Résultats du traitement")
        
        # Séparer les succès et les erreurs
        success_data = []
        error_data = []
        
        for domain, data in results.items():
            row = {'Domaine': domain}
            
            # Déterminer si c'est une erreur
            # Une donnée est valide si elle contient au moins une clé importante ET n'a pas de clé 'error'
            is_error = False
            error_message = None
            
            if not data or isinstance(data, bool) or data is False:
                is_error = True
                error_message = "Aucune donnée retournée"
            elif isinstance(data, dict):
                # Vérifier d'abord si c'est une erreur explicite
                if 'error' in data:
                    is_error = True
                    error_message = data.get('error', 'Erreur inconnue')
                # Sinon, vérifier si les données sont valides (au moins une clé importante)
                # Les données sont valides si elles ont au moins une de ces clés
                elif any(key in data for key in ['EstimatedMonthlyVisits', 'GlobalRank', 'SiteName', 'Domain', 'Engagments', 'TrafficSources', 'TopCountryShares', 'Category']):
                    # C'est un succès - les données sont valides
                    is_error = False
                else:
                    # Aucune clé importante trouvée - probablement une erreur
                    is_error = True
                    error_message = "Données incomplètes ou invalides"
            else:
                # Format inattendu
                is_error = True
                error_message = f"Format de données inattendu: {type(data).__name__}"
            
            if is_error:
                row['Message d\'erreur'] = error_message or "Erreur inconnue"
                error_data.append(row)
            else:
                # 1. Nombre de visites en millions (Nber of visits in M)
                if 'EstimatedMonthlyVisits' in data:
                    visits = data['EstimatedMonthlyVisits']
                    if isinstance(visits, dict):
                        latest_visits = list(visits.values())[-1] if visits else 0
                    else:
                        latest_visits = visits
                    row['Visites mensuelles'] = int(latest_visits) if latest_visits else 0
                    row['Visites (M)'] = round(int(latest_visits) / 1_000_000, 2) if latest_visits else 0
                else:
                    row['Visites mensuelles'] = 0
                    row['Visites (M)'] = 0
                
                # 2. Single visit (visites uniques - peut être dérivé des Engagments)
                if 'Engagments' in data and isinstance(data['Engagments'], dict):
                    visits_count = data['Engagments'].get('Visits', 0)
                    row['Visites uniques'] = int(float(visits_count)) if visits_count else 0
                else:
                    row['Visites uniques'] = 0
                
                # 3. Nombre de pages par visite (Nber of pages per visit)
                if 'Engagments' in data and isinstance(data['Engagments'], dict):
                    pages_per_visit = data['Engagments'].get('PagePerVisit', 0)
                    row['Pages par visite'] = round(float(pages_per_visit), 2) if pages_per_visit else 0
                else:
                    row['Pages par visite'] = 0
                
                # 4. Durée en minutes (Duration (min))
                if 'Engagments' in data and isinstance(data['Engagments'], dict):
                    time_on_site = data['Engagments'].get('TimeOnSite', 0)
                    # Convertir les secondes en minutes
                    row['Durée (min)'] = round(float(time_on_site) / 60, 2) if time_on_site else 0
                else:
                    row['Durée (min)'] = 0
                
                # 5. Taux de rebond (Bounce rate)
                if 'Engagments' in data and isinstance(data['Engagments'], dict):
                    bounce = data['Engagments'].get('BounceRate', 0)
                    row['Taux de rebond (%)'] = round(float(bounce) * 100, 2) if bounce else 0
                else:
                    row['Taux de rebond (%)'] = 0
                
                # 6. Trafic direct (Direct traffic)
                if 'TrafficSources' in data and isinstance(data['TrafficSources'], dict):
                    direct = data['TrafficSources'].get('Direct', 0)
                    row['Trafic direct (%)'] = round(float(direct) * 100, 2) if direct else 0
                else:
                    row['Trafic direct (%)'] = 0
                
                # 7. Trafic organique (Organic traffic) - généralement dans Search
                if 'TrafficSources' in data and isinstance(data['TrafficSources'], dict):
                    search = data['TrafficSources'].get('Search', 0)
                    row['Trafic organique (%)'] = round(float(search) * 100, 2) if search else 0
                else:
                    row['Trafic organique (%)'] = 0
                
                # 8. Trafic payant (Paid traffic)
                if 'TrafficSources' in data and isinstance(data['TrafficSources'], dict):
                    paid = data['TrafficSources'].get('Paid', 0)
                    paid_refs = data['TrafficSources'].get('Paid Referrals', 0)
                    total_paid = float(paid) + float(paid_refs) if paid or paid_refs else 0
                    row['Trafic payant (%)'] = round(total_paid * 100, 2) if total_paid else 0
                else:
                    row['Trafic payant (%)'] = 0
                
                # 9. Trafic réseaux sociaux (Social media traffic)
                if 'TrafficSources' in data and isinstance(data['TrafficSources'], dict):
                    social = data['TrafficSources'].get('Social', 0)
                    row['Trafic réseaux sociaux (%)'] = round(float(social) * 100, 2) if social else 0
                else:
                    row['Trafic réseaux sociaux (%)'] = 0
                
                # 10. Trafic email (Email traffic)
                if 'TrafficSources' in data and isinstance(data['TrafficSources'], dict):
                    mail = data['TrafficSources'].get('Mail', 0)
                    row['Trafic email (%)'] = round(float(mail) * 100, 2) if mail else 0
                else:
                    row['Trafic email (%)'] = 0
                
                # Métriques supplémentaires (gardées pour référence)
                # Classement
                if 'GlobalRank' in data and isinstance(data['GlobalRank'], dict):
                    row['Classement global'] = data['GlobalRank'].get('Rank', 'N/A')
                elif 'GlobalRank' in data:
                    row['Classement global'] = data['GlobalRank']
                else:
                    row['Classement global'] = 'N/A'
                
                # Catégorie
                row['Catégorie'] = data.get('Category', 'N/A').replace('_', ' ').title() if data.get('Category') else 'N/A'
                
                success_data.append(row)
        
        # Recalculer les statistiques basées sur les données réelles
        actual_success = len(success_data)
        actual_errors = len(error_data)
        
        # Statistiques
        col1, col2, col3 = st.columns(3)
        with col1:
            st.metric("✅ Succès", actual_success)
        with col2:
            st.metric("❌ Erreurs", actual_errors)
        with col3:
            st.metric("📦 Total", total)
        
        # Afficher les erreurs en premier si elles existent
        if error_data:
            st.markdown("---")
            st.subheader("❌ Erreurs détectées")
            st.warning(f"⚠️ {len(error_data)} domaine(s) ont rencontré des erreurs lors du traitement.")
            
            df_errors = pd.DataFrame(error_data)
            st.dataframe(
                df_errors,
                use_container_width=True,
                hide_index=True
            )
            
            # Bouton pour télécharger uniquement les erreurs
            csv_errors = df_errors.to_csv(index=False, encoding='utf-8-sig')
            st.download_button(
                label="📥 Télécharger la liste des erreurs (CSV)",
                data=csv_errors,
                file_name=f"similarweb_errors_{datetime.now().strftime('%Y%m%d_%H%M%S')}.csv",
                mime="text/csv"
            )
        
        # Afficher les succès
        if success_data:
            st.markdown("---")
            st.subheader("✅ Domaines traités avec succès")
            df_results = pd.DataFrame(success_data)
            
            # Définir l'ordre des colonnes pour une meilleure lisibilité
            column_order = [
                'Domaine',
                'Visites (M)',  # Nber of visits in M
                'Visites mensuelles',
                'Visites uniques',  # Single visit
                'Pages par visite',  # Nber of pages per visit
                'Durée (min)',  # Duration (min)
                'Taux de rebond (%)',  # Bounce rate
                'Trafic direct (%)',  # Direct traffic
                'Trafic organique (%)',  # Organic traffic
                'Trafic payant (%)',  # Paid traffic
                'Trafic réseaux sociaux (%)',  # Social media traffic
                'Trafic email (%)',  # Email traffic
                'Classement global',
                'Catégorie'
            ]
            
            # Réorganiser les colonnes (garder seulement celles qui existent)
            available_columns = [col for col in column_order if col in df_results.columns]
            # Ajouter les colonnes restantes qui ne sont pas dans l'ordre
            other_columns = [col for col in df_results.columns if col not in column_order]
            final_column_order = available_columns + other_columns
            
            df_results = df_results[final_column_order]
            st.dataframe(df_results, use_container_width=True, hide_index=True)
        elif not error_data:
            st.info("ℹ️ Aucun résultat à afficher")
        
        # Boutons d'export (uniquement si on a des succès)
        if success_data:
            st.markdown("---")
            st.subheader("📥 Export des résultats")
            col_export1, col_export2 = st.columns(2)
            
            with col_export1:
                # Export CSV des succès
                csv = df_results.to_csv(index=False, encoding='utf-8-sig')
                st.download_button(
                    label="📥 Télécharger CSV (succès uniquement)",
                    data=csv,
                    file_name=f"similarweb_batch_success_{datetime.now().strftime('%Y%m%d_%H%M%S')}.csv",
                    mime="text/csv"
                )
            
            with col_export2:
                # Export JSON complet (avec erreurs)
                json_data = json.dumps(results, indent=2, ensure_ascii=False)
                st.download_button(
                    label="📥 Télécharger JSON (complet avec erreurs)",
                    data=json_data,
                    file_name=f"similarweb_batch_complete_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json",
                    mime="application/json"
                )

# Onglets principaux
tab1, tab2, tab3 = st.tabs(["🔍 Recherche unique", "📋 Traitement par lots", "📅 Périodicité & Historique"])

# ========== ONGLET 1: RECHERCHE UNIQUE ==========
with tab1:
    st.header("🔍 Recherche de domaine")
    
    col1, col2 = st.columns([3, 1])
    
    with col1:
        website_input = st.text_input(
            "Entrez une URL ou un domaine",
            placeholder="https://example.com ou example.com",
            help="Vous pouvez entrer une URL complète ou juste le domaine"
        )
    
    with col2:
        st.write("")  # Espacement
        st.write("")  # Espacement
        search_button = st.button("🔎 Rechercher", type="primary", use_container_width=True)
    
    # Traitement de la requête
    if search_button and website_input:
        with st.spinner("Récupération des données en cours..."):
            try:
                # Appel à l'API
                result = similar.similarGet(website_input)
                
                if result and not isinstance(result, bool):
                    st.success("✅ Données récupérées avec succès!")
                    display_single_result(result)
                else:
                    st.error("❌ Aucune donnée retournée par l'API")
            
            except Exception as e:
                st.error(f"❌ Erreur lors de la récupération des données : {str(e)}")
                st.info("💡 Vérifiez que le domaine est valide et que vous n'avez pas atteint les limites de l'API.")
    
    elif search_button and not website_input:
        st.warning("⚠️ Veuillez entrer une URL ou un domaine")

# ========== ONGLET 2: TRAITEMENT PAR LOTS ==========
with tab2:
    st.header("📋 Traitement par lots de domaines")
    st.markdown("Téléchargez un fichier CSV ou TXT avec une liste de domaines, ou entrez-les manuellement.")
    
    # Options de configuration
    col_config1, col_config2 = st.columns(2)
    with col_config1:
        delay = st.slider("Délai entre requêtes (secondes)", 1.0, 10.0, 2.0, 0.5)
        use_cache = st.checkbox("Utiliser le cache", value=True, help="Évite de refaire des requêtes pour les domaines déjà analysés")
        chunk_size = st.number_input("Taille des lots (chunks)", 10, 500, 100, help="Traite les domaines par lots pour optimiser les performances")
    with col_config2:
        retry_count = st.number_input("Nombre de tentatives en cas d'erreur", 1, 5, 3)
        max_domains = st.number_input(
            "Nombre maximum de domaines à traiter", 
            1, 10000, 500,
            help="Limite augmentée pour traiter de grandes listes. Recommandé: 500-1000 par session."
        )
    
    # Option d'analyse par période
    st.markdown("---")
    st.subheader("📅 Analyse par période (optionnel)")
    analyze_period = st.checkbox(
        "Analyser les données historiques sur une période",
        value=False,
        help="Activez cette option pour analyser les données déjà collectées sur une période définie"
    )
    
    period_start = None
    period_end = None
    
    if analyze_period:
        col_period1, col_period2 = st.columns(2)
        with col_period1:
            period_start = st.date_input(
                "Date de début",
                value=datetime.now() - timedelta(days=30),
                help="Début de la période d'analyse"
            )
        with col_period2:
            period_end = st.date_input(
                "Date de fin",
                value=datetime.now(),
                help="Fin de la période d'analyse"
            )
        
        if period_start > period_end:
            st.error("⚠️ La date de début doit être antérieure à la date de fin")
            analyze_period = False
    
    # Méthode d'input
    input_method = st.radio(
        "Méthode d'entrée",
        ["📁 Upload fichier", "✍️ Saisie manuelle"],
        horizontal=True
    )
    
    domains_list = []
    
    if input_method == "📁 Upload fichier":
        uploaded_file = st.file_uploader(
            "Choisissez un fichier",
            type=['csv', 'txt'],
            help="CSV avec une colonne de domaines, ou TXT avec un domaine par ligne"
        )
        
        if uploaded_file:
            try:
                if uploaded_file.name.endswith('.csv'):
                    df = pd.read_csv(uploaded_file)
                    # Chercher la colonne avec les domaines
                    domain_col = None
                    for col in df.columns:
                        if any(keyword in col.lower() for keyword in ['domain', 'url', 'site', 'website', 'domaine']):
                            domain_col = col
                            break
                    if domain_col:
                        domains_list = df[domain_col].dropna().tolist()
                    else:
                        # Prendre la première colonne
                        domains_list = df.iloc[:, 0].dropna().tolist()
                else:  # TXT
                    content = uploaded_file.read().decode('utf-8')
                    domains_list = [line.strip() for line in content.split('\n') if line.strip()]
                
                domains_list = [d for d in domains_list if d][:max_domains]
                st.success(f"✅ {len(domains_list)} domaine(s) chargé(s)")
                
            except Exception as e:
                st.error(f"❌ Erreur lors de la lecture du fichier : {str(e)}")
    
    else:  # Saisie manuelle
        manual_input = st.text_area(
            "Entrez les domaines (un par ligne)",
            height=150,
            help="Un domaine par ligne, avec ou sans http://"
        )
        if manual_input:
            domains_list = [line.strip() for line in manual_input.split('\n') if line.strip()][:max_domains]
            st.info(f"📝 {len(domains_list)} domaine(s) détecté(s)")
    
    # Estimation du temps
    if domains_list:
        estimated_time_minutes = (len(domains_list) * delay) / 60
        estimated_time_hours = estimated_time_minutes / 60
        if estimated_time_hours >= 1:
            time_display = f"~{estimated_time_hours:.1f} heure(s)"
        else:
            time_display = f"~{estimated_time_minutes:.1f} minute(s)"
        st.info(f"⏱️ Temps estimé : {time_display} pour {len(domains_list)} domaine(s) (délai: {delay}s)")
    
    # Bouton de traitement
    if domains_list and st.button("🚀 Lancer le traitement", type="primary", use_container_width=True):
        if analyze_period and period_start and period_end:
            # Analyse par période
            analyze_batch_period(domains_list, period_start, period_end)
        else:
            # Traitement normal
            process_batch(domains_list, delay, use_cache, retry_count, chunk_size)

# ========== ONGLET 3: PÉRIODICITÉ & HISTORIQUE ==========
with tab3:
    st.header("📅 Périodicité & Historique")
    st.markdown("Visualisez l'évolution des données dans le temps et comparez différentes périodes.")
    
    # Récupérer la liste des domaines dans l'historique
    all_domains = similar.get_all_domains_in_history()
    
    if not all_domains:
        st.info("📝 Aucun historique disponible. Les données seront automatiquement sauvegardées lors de vos recherches.")
        st.markdown("""
        **Comment ça fonctionne :**
        - Chaque fois que vous récupérez des données (recherche unique ou par lots), elles sont automatiquement sauvegardées dans l'historique
        - Vous pouvez ensuite visualiser l'évolution et comparer les périodes
        - Les données sont stockées avec un timestamp pour suivre les changements dans le temps
        """)
    else:
        # Sélection du domaine
        selected_domain = st.selectbox(
            "Sélectionnez un domaine",
            all_domains,
            help="Choisissez un domaine pour voir son historique"
        )
        
        if selected_domain:
            # Récupérer l'historique
            history_entries = similar.get_history_for_domain(selected_domain)
            
            if history_entries:
                st.success(f"✅ {len(history_entries)} entrée(s) historique(s) trouvée(s) pour {selected_domain}")
                
                # Sous-onglets pour différentes vues
                sub_tabs = st.tabs(["📈 Évolution temporelle", "🔄 Comparaison de périodes", "📊 Données historiques"])
                
                # Onglet 1: Évolution temporelle
                with sub_tabs[0]:
                    st.subheader("Évolution des métriques dans le temps")
                    
                    # Préparer les données pour les graphiques
                    dates = []
                    visits_data = []
                    ranks_data = []
                    bounce_rates = []
                    
                    for entry in history_entries:
                        date_str = entry.get('date', entry['timestamp'][:10])
                        dates.append(date_str)
                        data = entry['data']
                        
                        # Visites
                        if 'EstimatedMonthlyVisits' in data:
                            visits = data['EstimatedMonthlyVisits']
                            if isinstance(visits, dict):
                                latest_visits = list(visits.values())[-1] if visits else 0
                            else:
                                latest_visits = visits
                            visits_data.append(int(latest_visits) if latest_visits else 0)
                        else:
                            visits_data.append(0)
                        
                        # Classement
                        if 'GlobalRank' in data:
                            if isinstance(data['GlobalRank'], dict):
                                rank = data['GlobalRank'].get('Rank', 0)
                            else:
                                rank = data['GlobalRank']
                            ranks_data.append(rank if rank else 0)
                        else:
                            ranks_data.append(0)
                        
                        # Taux de rebond
                        if 'Engagments' in data and isinstance(data['Engagments'], dict):
                            bounce = data['Engagments'].get('BounceRate', 0)
                            bounce_rates.append(float(bounce) * 100 if bounce else 0)
                        else:
                            bounce_rates.append(0)
                    
                    # Créer un DataFrame
                    df_history = pd.DataFrame({
                        'Date': dates,
                        'Visites mensuelles': visits_data,
                        'Classement global': ranks_data,
                        'Taux de rebond (%)': bounce_rates
                    })
                    
                    # Graphique des visites
                    if len(visits_data) > 0 and any(v > 0 for v in visits_data):
                        st.subheader("📊 Évolution des visites mensuelles")
                        st.line_chart(df_history.set_index('Date')['Visites mensuelles'], height=300)
                    
                    # Graphique du classement
                    if len(ranks_data) > 0 and any(r > 0 for r in ranks_data):
                        st.subheader("📊 Évolution du classement global")
                        st.line_chart(df_history.set_index('Date')['Classement global'], height=300)
                    
                    # Graphique du taux de rebond
                    if len(bounce_rates) > 0 and any(b > 0 for b in bounce_rates):
                        st.subheader("📊 Évolution du taux de rebond")
                        st.line_chart(df_history.set_index('Date')['Taux de rebond (%)'], height=300)
                    
                    # Tableau récapitulatif
                    st.subheader("📋 Tableau récapitulatif")
                    st.dataframe(df_history, use_container_width=True, hide_index=True)
                    
                    # Export
                    csv_history = df_history.to_csv(index=False, encoding='utf-8-sig')
                    st.download_button(
                        label="📥 Télécharger l'historique CSV",
                        data=csv_history,
                        file_name=f"similarweb_history_{selected_domain}_{datetime.now().strftime('%Y%m%d')}.csv",
                        mime="text/csv"
                    )
                
                # Onglet 2: Comparaison de périodes
                with sub_tabs[1]:
                    st.subheader("Comparer deux périodes")
                    
                    # Extraire les périodes uniques
                    periods = sorted(set([e.get('period', e['date'][:7]) for e in history_entries]))
                    
                    if len(periods) < 2:
                        st.info("⚠️ Au moins 2 périodes sont nécessaires pour faire une comparaison.")
                    else:
                        col_period1, col_period2 = st.columns(2)
                        
                        with col_period1:
                            period1 = st.selectbox("Période 1", periods, index=0)
                        
                        with col_period2:
                            period2 = st.selectbox("Période 2", periods, index=min(1, len(periods)-1))
                        
                        if period1 != period2:
                            comparison = similar.compare_periods(selected_domain, period1, period2)
                            
                            if comparison:
                                st.markdown("---")
                                st.subheader(f"Comparaison : {period1} vs {period2}")
                                
                                # Afficher les changements
                                if 'visits' in comparison['changes']:
                                    visits_change = comparison['changes']['visits']
                                    col1, col2, col3 = st.columns(3)
                                    
                                    with col1:
                                        st.metric(
                                            f"Visites ({period1})",
                                            f"{int(visits_change['period1']):,}".replace(",", " ")
                                        )
                                    
                                    with col2:
                                        st.metric(
                                            f"Visites ({period2})",
                                            f"{int(visits_change['period2']):,}".replace(",", " ")
                                        )
                                    
                                    with col3:
                                        change_value = visits_change['change']
                                        change_pct = visits_change['change_percent']
                                        delta_color = "normal" if change_value >= 0 else "inverse"
                                        st.metric(
                                            "Évolution",
                                            f"{int(change_value):,}".replace(",", " "),
                                            delta=f"{change_pct:+.2f}%"
                                        )
                                
                                if 'rank' in comparison['changes']:
                                    rank_change = comparison['changes']['rank']
                                    col1, col2, col3 = st.columns(3)
                                    
                                    with col1:
                                        st.metric(f"Classement ({period1})", f"#{rank_change['period1']}")
                                    
                                    with col2:
                                        st.metric(f"Classement ({period2})", f"#{rank_change['period2']}")
                                    
                                    with col3:
                                        rank_diff = rank_change['change']
                                        # Positif = baisse de classement (moins bon)
                                        delta_color = "normal" if rank_diff <= 0 else "inverse"
                                        st.metric(
                                            "Évolution",
                                            f"#{rank_change['period2']}",
                                            delta=f"{rank_diff:+d}" if rank_diff != 0 else "0"
                                        )
                                
                                # Export de la comparaison
                                comparison_json = json.dumps(comparison, indent=2, ensure_ascii=False)
                                st.download_button(
                                    label="📥 Télécharger la comparaison JSON",
                                    data=comparison_json,
                                    file_name=f"similarweb_comparison_{selected_domain}_{period1}_vs_{period2}.json",
                                    mime="application/json"
                                )
                            else:
                                st.warning("Impossible de comparer ces périodes. Vérifiez que les données existent pour les deux périodes.")
                
                # Onglet 3: Données historiques brutes
                with sub_tabs[2]:
                    st.subheader("Données historiques complètes")
                    
                    # Filtres
                    col_filter1, col_filter2 = st.columns(2)
                    
                    with col_filter1:
                        filter_start = st.date_input(
                            "Date de début",
                            value=datetime.now() - timedelta(days=30),
                            help="Filtrer les données à partir de cette date"
                        )
                    
                    with col_filter2:
                        filter_end = st.date_input(
                            "Date de fin",
                            value=datetime.now(),
                            help="Filtrer les données jusqu'à cette date"
                        )
                    
                    # Filtrer l'historique
                    filtered_history = [
                        e for e in history_entries
                        if filter_start <= datetime.fromisoformat(e['timestamp']).date() <= filter_end
                    ]
                    
                    st.info(f"📊 {len(filtered_history)} entrée(s) trouvée(s) pour la période sélectionnée")
                    
                    # Afficher les entrées
                    for idx, entry in enumerate(reversed(filtered_history), 1):
                        with st.expander(f"📅 {entry['date']} - {entry.get('period', 'N/A')} - {entry['timestamp'][:19]}"):
                            st.json(entry['data'])
                    
                    # Export de toutes les données historiques
                    if filtered_history:
                        history_json = json.dumps(filtered_history, indent=2, ensure_ascii=False)
                        st.download_button(
                            label="📥 Télécharger toutes les données historiques JSON",
                            data=history_json,
                            file_name=f"similarweb_full_history_{selected_domain}_{datetime.now().strftime('%Y%m%d')}.json",
                            mime="application/json"
                        )
            else:
                st.warning(f"⚠️ Aucune donnée historique trouvée pour {selected_domain}")

# Instructions
st.markdown("---")
with st.expander("📖 Comment utiliser cette application"):
    st.markdown("""
    ### Recherche unique
    1. **Entrez une URL ou un domaine** dans le champ de recherche
    2. **Cliquez sur "Rechercher"** pour obtenir les données
    3. **Explorez les résultats** dans les différents onglets
    
    ### Traitement par lots
    1. **Choisissez votre méthode d'entrée** (fichier ou saisie manuelle)
    2. **Configurez les paramètres** (délai, cache, etc.)
    3. **Lancez le traitement** et suivez la progression
    4. **Téléchargez les résultats** en CSV ou JSON
    
    ### Périodicité & Historique
    1. **Sélectionnez un domaine** dans la liste des domaines suivis
    2. **Visualisez l'évolution** des métriques dans le temps (visites, classement, taux de rebond)
    3. **Comparez deux périodes** pour analyser les changements
    4. **Exportez les données historiques** pour analyse approfondie
    
    **Fonctionnalités de périodicité :**
    - Sauvegarde automatique de toutes les données récupérées
    - Suivi de l'évolution temporelle avec graphiques
    - Comparaison entre périodes (mensuelles, trimestrielles, etc.)
    - Export des données historiques
    
    **Optimisations incluses :**
    - Rotation automatique des User-Agents
    - Cache des résultats (24h)
    - Délais intelligents entre requêtes
    - Retry automatique en cas d'erreur 403/429
    - Historique automatique de toutes les récupérations
    
    **Note importante :** Limitez vos requêtes pour éviter d'atteindre les limites de l'API Similarweb.
    """)
