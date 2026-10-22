import streamlit as st
from datetime import datetime
import time
import re
import pandas as pd
from streamlit_folium import st_folium
import plotly.express as px
import os

# Імпорт модулів системи
from engine import DomainContextEngine
from validation import is_valid_input_text
from matcher import load_system_core, search_similar_petitions
from ui_components import render_petition_card
from reports import export_to_csv, export_to_pdf
from mapping import build_petition_map

# 1. Ініціалізація конфігурації сторінки
st.set_page_config(
    page_title="Муніципальний моніторинг електронних петицій",
    page_icon="🏛️",
    layout="wide",
    initial_sidebar_state="expanded"
)

css_path = os.path.join(os.path.dirname(__file__), "assets", "style.css")
with open(css_path, "r", encoding="utf-8") as f:
    st.markdown(f"<style>{f.read()}</style>", unsafe_allow_html=True)

# 2. Кешоване завантаження ML-ядра та даних
@st.cache_resource
def get_cached_core():
    return load_system_core()

df_corpus, model, corpus_embeddings = get_cached_core()

# --- 3. САЙДБАР КЕРУВАННЯ ---
with st.sidebar:
    st.subheader("Панель ОМС")
    st.markdown("---")
    
    # 1. Юрисдикція / Рада
    authority_list = ["Всі юрисдикції (Національний рівень)"] + sorted([str(a) for a in df_corpus['authority'].dropna().unique()])
    selected_authority = st.selectbox("Юрисдикція / Рада:", authority_list)
    
    strict_authority_mode = st.toggle("Сувора ізоляція громади", value=True)
    
    # 2. Кількість схожих для аналізу
    top_k = st.slider("Кількість схожих для аналізу:", min_value=3, max_value=10, value=5)
    
    # 3. Фільтрація статусів
    if 'status' in df_corpus.columns:
        raw_statuses = [str(s).strip() for s in df_corpus['status'].dropna().unique()]
        valid_statuses = sorted([
            s for s in raw_statuses 
            if s and not s.startswith("http") and not s.startswith("www") and len(s) < 50
        ])
        
        if 'selected_statuses_set' not in st.session_state:
            st.session_state['selected_statuses_set'] = set(valid_statuses)

        st.write("**Статус петицій:**")
        col_btn1, col_btn2, col_btn3 = st.columns(3)
        with col_btn1:
            if st.button("Всі", use_container_width=True):
                st.session_state['selected_statuses_set'] = set(valid_statuses)
                st.rerun()
        with col_btn2:
            if st.button("Активні", use_container_width=True):
                active_only = {s for s in valid_statuses if "збір" in s.lower() or "актив" in s.lower()}
                st.session_state['selected_statuses_set'] = active_only if active_only else set(valid_statuses)
                st.rerun()
        with col_btn3:
            if st.button("Reset", use_container_width=True):
                st.session_state['selected_statuses_set'] = set()
                st.rerun()

        selected_count = len(st.session_state['selected_statuses_set'])
        with st.expander(f"Налаштувати статуси ({selected_count} з {len(valid_statuses)})", expanded=False):
            updated_selection = set()
            for st_name in valid_statuses:
                is_checked = st_name in st.session_state['selected_statuses_set']
                if st.checkbox(st_name, value=is_checked, key=f"status_cb_{st_name}"):
                    updated_selection.add(st_name)
            st.session_state['selected_statuses_set'] = updated_selection

        selected_statuses = list(st.session_state['selected_statuses_set'])
    else:
        selected_statuses = None

    # 4. Динамічні пороги прийняття рішень
    with st.expander("Поріг чутливості системи", expanded=False):
        threshold_duplicate = st.slider(
            "Поріг дублікату (DUPLICATE):",
            min_value=0.80, 
            max_value=0.98, 
            value=0.88, 
            step=0.01,
            help="Ініціативи з балом вище цього значення вважаються прямими дублікатами."
        )
        threshold_review = st.slider(
            "Поріг модерації (REVIEW):",
            min_value=0.65, 
            max_value=round(threshold_duplicate - 0.01, 2), 
            value=0.76, 
            step=0.01,
            help="Ініціативи у діапазоні між порогом модерації та дублікату потребують ручного рев'ю."
        )
        confidence_floor = st.slider(
            "Поріг фонового шуму (FLOOR):",
            min_value=0.45, 
            max_value=round(threshold_review - 0.01, 2), 
            value=0.60, 
            step=0.01,
            help="Кандидати з балом нижче цього порогу ігноруються як семантичний шум."
        )

    st.markdown("---")
    st.caption("База активних ініціатив підключена успішно.")

# --- 4. ГОЛОВНИЙ ЕКРАН ТА СТРУКТУРА ВКЛАДОК ---
st.title("🏛️ Муніципальний моніторинг електронних петицій")
st.markdown("Інтелектуальна система семантичного зіставлення, дедуплікації та верифікації локацій")

tab1, tab2, tab3 = st.tabs(["Перевірка петиції", "Карта звернень громади", "Аналітика"])

# ==============================================================================
# ВКЛАДКА 1: ДЕДУПЛІКАЦІЯ ТА ВЕРИФІКАЦІЯ
# ==============================================================================
with tab1:
    col1, col2 = st.columns([3, 1])
    with col1:
        query_title = st.text_input("Заголовок нової петиції:", placeholder="Введіть заголовок...")
    with col2:
        st.write("")
        st.write("")
        check_btn = st.button("🔍 Перевірити петицію", use_container_width=True)

    query_body = st.text_area("Повний текст звернення (опціонально):", placeholder="Деталі звернення...", height=90)

    if check_btn:
        if not query_title.strip():
            st.warning("Будь ласка, введіть заголовок петиції для перевірки.")
        elif selected_statuses is not None and len(selected_statuses) == 0:
            st.warning("Будь ласка, оберіть хоча б один статус петицій у бічній панелі.")
        else:
            is_valid, validation_msg = is_valid_input_text(query_title)
            if not is_valid:
                st.error(f"⚠️ **Помилка валідації:** {validation_msg}")
            else:
                with st.spinner("Виконується семантичний та географічний аналіз..."):
                    full_query = f"{query_title.strip()}. {query_body.strip()}".strip()
                    
                    start_time = time.perf_counter()
                    results = search_similar_petitions(
                        query_text=full_query,
                        df_corpus=df_corpus,
                        model=model,
                        corpus_embeddings=corpus_embeddings,
                        selected_authority=selected_authority,
                        strict_mode=strict_authority_mode,
                        top_k=top_k,
                        selected_statuses=selected_statuses,
                        threshold_duplicate=threshold_duplicate,
                        threshold_review=threshold_review
                    )
                    execution_time_ms = round((time.perf_counter() - start_time) * 1000, 1)

                    # Розрахунок розміру відфільтрованої вибірки
                    df_filtered_scope = df_corpus.copy()
                    if strict_authority_mode and selected_authority != "Всі юрисдикції (Національний рівень)":
                        df_filtered_scope = df_filtered_scope[df_filtered_scope['authority'] == selected_authority]
                    if selected_statuses and 'status' in df_filtered_scope.columns:
                        df_filtered_scope = df_filtered_scope[df_filtered_scope['status'].isin(selected_statuses)]
                    candidates_evaluated = len(df_filtered_scope)

                    st.session_state['search_results'] = {
                        'results': results,
                        'query_title': query_title,
                        'query_body': query_body,
                        'authority': selected_authority,
                        'confidence_floor': confidence_floor,
                        'latency_ms': execution_time_ms,
                        'corpus_total': len(df_corpus),
                        'candidates_evaluated': candidates_evaluated
                    }

    # Відображення результатів із session_state
    if 'search_results' in st.session_state:
        data = st.session_state['search_results']
        results = data['results']
        q_title = data['query_title']
        q_body = data['query_body']
        q_auth = data['authority']
        current_floor = data.get('confidence_floor', confidence_floor)
        latency_ms = data.get('latency_ms', 0.0)
        corpus_total = data.get('corpus_total', len(df_corpus))
        candidates_evaluated = data.get('candidates_evaluated', len(df_corpus))

        # Блок телеметрії
        st.markdown("#### Телеметрія обробки запиту")
        m_col1, m_col2, m_col3 = st.columns(3)
        with m_col1:
            st.metric("Час інференсу та аналізу", f"{latency_ms} мс")
        with m_col2:
            st.metric("Активний корпус петицій", f"{corpus_total:,} записів".replace(",", " "))
        with m_col3:
            st.metric("Перевірено кандидатів", f"{candidates_evaluated:,} записів".replace(",", " "), delta=f"топ-{len(results)}")

        st.markdown("---")

        if not results.empty:
            top_record = results.iloc[0]
            st.markdown("### Висновок системи")
            
            if top_record['final_score'] < current_floor:
                st.success("✅ **Петиція повністю унікальна:** Схожих чи дублюючих ініціатив у базі не виявлено (всі знайдені збіги нижче порогу значущості).")
            elif top_record['verdict'] == "DUPLICATE":
                st.error(f"❌ **Реєстрацію відхилено:** Виявлено прямий дублікат із балом {top_record['final_score']}")
            elif top_record['verdict'] == "REVIEW":
                st.warning(f"⚠️ **Потрібна увага модератора:** Знайдено споріднену ініціативу ({top_record['final_score']})")
            else:
                st.success("✅ **Петиція унікальна:** Схожих ініціатив не виявлено")
                
            st.markdown("---")
            
            meaningful_results = results[results['final_score'] >= current_floor]
            
            # Експорт протоколів
            st.markdown("#### Експорт результатів аудиту")
            col_dl1, col_dl2 = st.columns(2)
            with col_dl1:
                csv_data = export_to_csv(results)
                st.download_button(
                    label="Завантажити звіт у CSV",
                    data=csv_data,
                    file_name=f"petition_audit_{top_record['final_score']}.csv",
                    mime="text/csv",
                    use_container_width=True
                )
            with col_dl2:
                pdf_data = export_to_pdf(
                    query_title=q_title,
                    query_body=q_body,
                    authority=q_auth,
                    results_df=meaningful_results if not meaningful_results.empty else results.head(3),
                    top_verdict=f"{top_record['status_text']} (Бал: {top_record['final_score']})"
                )
                st.download_button(
                    label="Завантажити протокол у PDF",
                    data=pdf_data,
                    file_name=f"petition_protocol_{datetime.now().strftime('%Y%m%d_%H%M')}.pdf",
                    mime="application/pdf",
                    use_container_width=True
                )
                
            st.markdown("---")
            
            if not meaningful_results.empty:
                st.subheader(f"Топ-{len(meaningful_results)} найбільш релевантних петицій у базі")
                for _, row in meaningful_results.iterrows():
                    st.markdown(render_petition_card(row), unsafe_allow_html=True)
            else:
                st.info("Жодна з наявних петицій не досягла мінімального порогу релевантності.")
        else:
            st.info("У вибраній раді петицій не знайдено.")

# ==============================================================================
# ВКЛАДКА 2: ГЕОПРОСТОРОВА КАРТА ТА HEATMAP
# ==============================================================================
with tab2:
    st.subheader("🗺️ Геопросторовий моніторинг звернень громади")
    st.caption("Відображення локацій поданих петицій та зон концентрації скарг інфраструктури")

    col_map_ctrl1, col_map_ctrl2 = st.columns([2, 1])
    with col_map_ctrl1:
        st.info(f" Поточна юрисдикція перегляду: **{selected_authority}**")
    with col_map_ctrl2:
        enable_heat = st.toggle("Увімкнути теплову карту (Heatmap)", value=True)

    with st.spinner("Генерація картографічного шару..."):
        petition_map = build_petition_map(
            df_corpus=df_corpus,
            selected_authority=selected_authority,
            show_heatmap=enable_heat
        )
        st_folium(petition_map, width="100%", height=550, returned_objects=[])


# ==============================================================================
# ВКЛАДКА 3: АНАЛІТИЧНИЙ ДАШБОРД (PLOTLY CHARTS)
# ==============================================================================
with tab3:
    st.subheader("📊 Аналітичний дашборд корпусу електронних петицій")
    st.markdown("Комплексна візуалізація структурного, тематичного та просторового розподілу звернень громадян.")

    # Фільтрація під вибірку сайдбару
    df_analytics = df_corpus.copy()
    if selected_authority != "Всі юрисдикції (Національний рівень)":
        df_analytics = df_analytics[df_analytics['authority'] == selected_authority]
        st.info(f" Вибірка даних: **{selected_authority}** ({len(df_analytics)} звернень)")

    # 1. KPI-плашки ключових метрик
    kpi1, kpi2, kpi3, kpi4 = st.columns(4)
    with kpi1:
        st.metric("Загалом звернень", f"{len(df_analytics):,}".replace(",", " "))
    with kpi2:
        num_auth = df_analytics['authority'].nunique() if 'authority' in df_analytics.columns else 1
        st.metric("Охоплено ОМС", num_auth)
    with kpi3:
        if 'status' in df_analytics.columns:
            active_cnt = sum(df_analytics['status'].astype(str).str.lower().str.contains("збір|актив", na=False))
            st.metric("Активні збори", active_cnt)
        else:
            st.metric("Активні збори", "Н/Д")
    with kpi4:
        authors_cnt = df_analytics['author'].nunique() if 'author' in df_analytics.columns else len(df_analytics)
        st.metric("Унікальних авторів", f"{authors_cnt:,}".replace(",", " "))

    st.markdown("---")

    # --------------------------------------------------------------------------
    # ДІАГРАМА 1: ТЕМАТИЧНІ КАТЕГОРІЇ (На всю ширину, акуратна легенда)
    # --------------------------------------------------------------------------
    st.markdown("#### 1. Розподіл петицій за тематичними категоріями")
    
    titles_sample = df_analytics['title'].dropna().astype(str).tolist()
    raw_domains = [DomainContextEngine.detect_domain(t) for t in titles_sample]
    
    domain_labels = {
        "ROADS_INFRA": "Дороги та дорожня інфраструктура",
        "EDUCATION": "Освіта і навчальні заклади",
        "TRANSPORT": "Громадський транспорт та перевезення",
        "ANIMALS": "Захист і притулки для тварин",
        "ECOLOGY_PARKS": "Екологія, сквери, благоустрій парків",
        "HOUSING": "ЖКГ, теплопостачання та будинки",
        "GENERAL": "Інші муніципальні ініціативи"
    }
    
    category_counts = pd.Series([domain_labels.get(d, d) for d in raw_domains]).value_counts().reset_index()
    category_counts.columns = ['Категорія', 'Кількість']

    if not category_counts.empty:
        fig_category = px.pie(
            category_counts,
            names='Категорія',
            values='Кількість',
            hole=0.45,
            color_discrete_sequence=px.colors.qualitative.Prism
        )
        fig_category.update_traces(
            textposition='inside',
            textinfo='percent',
            hovertemplate="<b>%{label}</b><br>Петицій: %{value}<br>Частка: %{percent}<extra></extra>"
        )
        fig_category.update_layout(
            margin=dict(t=20, b=20, l=20, r=20),
            height=380,
            legend=dict(orientation="v", yanchor="middle", y=0.5, xanchor="left", x=1.02)
        )
        st.plotly_chart(fig_category, use_container_width=True)
    else:
        st.caption("Дані для класифікації відсутні.")

    st.markdown("---")

    # --------------------------------------------------------------------------
    # ДІАГРАМА 2: РЕЙТИНГ ГРОМАД (З очищенням довгих канцеляризмів)
    # --------------------------------------------------------------------------
    st.markdown("#### 2. Рейтинг активності органів місцевого самоврядування")
    
    if 'authority' in df_corpus.columns:
        auth_raw = df_corpus['authority'].dropna().astype(str)
        
        # Функція скорочення бюрократичних назв рад
        def clean_auth_name(name: str) -> str:
            n = name.replace("Виконавчий комітет ", "").replace(" Кременчуцького району Полтавської області", "")
            n = n.replace(" Селищна", " селищна").strip()
            return n

        auth_cleaned = auth_raw.apply(clean_auth_name).value_counts().head(8).reset_index()
        auth_cleaned.columns = ['Громада / Рада', 'Кількість петицій']

        fig_auth = px.bar(
            auth_cleaned,
            x='Кількість петицій',
            y='Громада / Рада',
            orientation='h',
            text='Кількість петицій',
            color='Кількість петицій',
            color_continuous_scale="Purples"
        )
        fig_auth.update_traces(textposition='outside', cliponaxis=False)
        fig_auth.update_layout(
            margin=dict(t=20, b=20, l=20, r=40),
            height=380,
            yaxis=dict(autorange="reversed", title=""),
            xaxis=dict(title="Кількість зареєстрованих звернень", showgrid=True),
            coloraxis_showscale=False
        )
        st.plotly_chart(fig_auth, use_container_width=True)

    st.markdown("---")

    # --------------------------------------------------------------------------
    # ДІАГРАМА 3: ДИНАМІКА АБО РОЗПОДІЛ СТАТУСІВ (БЕЗ ДРОБОВИХ ЧИСЕЛ ТА СПЛЮЩУВАННЯ)
    # --------------------------------------------------------------------------
    date_col = None
    for candidate in ['created_at', 'date', 'created', 'start_date', 'datetime']:
        if candidate in df_analytics.columns:
            date_col = candidate
            break

    timeline_built = False

    if date_col:
        try:
            df_analytics['parsed_date'] = pd.to_datetime(df_analytics[date_col], errors='coerce')
            df_timeline = df_analytics.dropna(subset=['parsed_date']).copy()
            
            # Якщо є достатня кількість валідних дат (хоча б > 15 записів)
            if len(df_timeline) >= 15:
                st.markdown("#### 3. Хронологічний розподіл реєстрації петицій за місяцями")
                df_timeline['period'] = df_timeline['parsed_date'].dt.to_period('M').dt.to_timestamp()
                timeline_counts = df_timeline.groupby('period').size().reset_index(name='Кількість')
                timeline_counts = timeline_counts.sort_values(by='period')

                fig_time = px.bar(
                    timeline_counts,
                    x='period',
                    y='Кількість',
                    text='Кількість',
                    labels={'period': 'Місяць реєстрації', 'Кількість': 'Подано звернень'},
                    color_discrete_sequence=['#7C3AED']
                )
                fig_time.update_traces(textposition='outside')
                fig_time.update_layout(
                    margin=dict(t=20, b=20, l=20, r=20),
                    height=360,
                    xaxis=dict(tickformat="%b %Y", showgrid=True),
                    yaxis=dict(showgrid=True, nticks=6)
                )
                st.plotly_chart(fig_time, use_container_width=True)
                timeline_built = True
        except Exception:
            timeline_built = False

    # Якщо дат немає або їх 2-3 штуки — показуємо красиву стовпчасту діаграму статусів розгляду
    if not timeline_built:
        st.markdown("#### 3. Структура розгляду петицій за офіційними статусами")
        if 'status' in df_analytics.columns:
            clean_status = df_analytics['status'].dropna().astype(str).str.strip()
            clean_status = clean_status[~clean_status.str.startswith("http") & (clean_status.str.len() < 45)]
            status_summary = clean_status.value_counts().reset_index()
            status_summary.columns = ['Офіційний статус', 'Кількість петицій']

            fig_status = px.bar(
                status_summary,
                x='Офіційний статус',
                y='Кількість петицій',
                text='Кількість петицій',
                color='Офіційний статус',
                color_discrete_sequence=px.colors.qualitative.Pastel
            )
            fig_status.update_traces(textposition='outside')
            fig_status.update_layout(
                margin=dict(t=25, b=30, l=20, r=20),
                height=380,
                showlegend=False,
                xaxis=dict(tickangle=-15, title=""),
                yaxis=dict(showgrid=True, title="Кількість петицій")
            )
            st.plotly_chart(fig_status, use_container_width=True)
        else:
            st.caption("Дані про статуси відсутні.")

        st.markdown("---")

   # --------------------------------------------------------------------------
    # ЧАСОВИЙ АНАЛІЗ: СЕЗОННІСТЬ ТА АКТИВНІСТЬ ГРОМАДЯН У ЧАСІ
    # --------------------------------------------------------------------------
    st.markdown("#### 4. Часовий аналіз та сезонність активності громадян")
    st.caption("Дослідження динаміки реєстрації ініціатив: дні тижня, місяці та інтенсивність подання.")

    # 1. Надійне парсування дати з офіційної колонки (start_date / date / created)
    date_series = None
    for col in df_analytics.columns:
        if any(k in col.lower() for k in ['start_date', 'date', 'created', 'start', 'дата']):
            # format='mixed' коректно розпізнає формати ISO (2024-08-13) і UA (11.01.2016 15:40)
            parsed = pd.to_datetime(df_analytics[col], format='mixed', errors='coerce')
            if parsed.notna().sum() >= 10:
                date_series = parsed
                break

    # 2. Фільтрація аномалій: електронні петиції в Україні існують лише з осені 2015 року
    if date_series is not None:
        # Відсікаємо дати народження (до 2015) та випадкові помилкові майбутні роки
        now_ts = pd.Timestamp.now()
        valid_mask = (date_series >= '2015-01-01') & (date_series <= now_ts + pd.DateOffset(years=1))
        valid_dates = date_series[valid_mask].dropna()
    else:
        valid_dates = pd.Series(dtype='datetime64[ns]')

    # 3. Побудова часових діаграм, якщо є валідні дати
    if len(valid_dates) >= 15:
        valid_dates_df = pd.DataFrame({"datetime": valid_dates})

        # Додаємо часові ознаки
        valid_dates_df['day_name'] = valid_dates_df['datetime'].dt.day_name()
        valid_dates_df['month_name'] = valid_dates_df['datetime'].dt.strftime('%m - %B')
        valid_dates_df['year_month'] = valid_dates_df['datetime'].dt.to_period('M').dt.to_timestamp()

        ua_days = {
            'Monday': '1. Понеділок',
            'Tuesday': '2. Вівторок',
            'Wednesday': '3. Середа',
            'Thursday': '4. Четвер',
            'Friday': "5. П'ятниця",
            'Saturday': '6. Субота',
            'Sunday': '7. Неділя'
        }
        valid_dates_df['ua_day'] = valid_dates_df['day_name'].map(ua_days)

        col_t1, col_t2 = st.columns(2)

        with col_t1:
            st.markdown("##### Активність за днями тижня")
            dow_counts = valid_dates_df['ua_day'].value_counts().sort_index().reset_index()
            dow_counts.columns = ['День тижня', 'Петицій']

            fig_dow = px.bar(
                dow_counts,
                x='День тижня',
                y='Петицій',
                text='Петицій',
                color='Петицій',
                color_continuous_scale="Purples"
            )
            fig_dow.update_traces(textposition='outside')
            fig_dow.update_layout(
                margin=dict(t=20, b=20, l=10, r=10),
                height=340,
                xaxis=dict(title="", tickangle=-20),
                yaxis=dict(title="Кількість поданих звернень", showgrid=True, nticks=6),
                coloraxis_showscale=False
            )
            st.plotly_chart(fig_dow, use_container_width=True)

        with col_t2:
            st.markdown("##### Щомісячна інтенсивність подання")
            ym_counts = valid_dates_df.groupby('year_month').size().reset_index(name='Петицій')
            ym_counts = ym_counts.sort_values(by='year_month')

            fig_ym = px.bar(
                ym_counts,
                x='year_month',
                y='Петицій',
                text='Петицій',
                color_discrete_sequence=['#7C3AED']
            )
            fig_ym.update_traces(textposition='outside')
            fig_ym.update_layout(
                margin=dict(t=20, b=20, l=10, r=10),
                height=340,
                xaxis=dict(title="", tickformat="%b %Y"),
                yaxis=dict(title="Кількість звернень", dtick=5)
            )
            st.plotly_chart(fig_ym, use_container_width=True)

        # Кумулятивний графік зростання бази (Cumulative Growth)
        st.markdown("##### Кумулятивне зростання обсягу електронних ініціатив")
        valid_dates_df_sorted = valid_dates_df.sort_values(by='datetime').reset_index(drop=True)
        valid_dates_df_sorted['cumulative_count'] = range(1, len(valid_dates_df_sorted) + 1)

        fig_cum = px.area(
            valid_dates_df_sorted,
            x='datetime',
            y='cumulative_count',
            labels={'datetime': 'Час реєстрації', 'cumulative_count': 'Загальна кількість петицій'},
            color_discrete_sequence=['#2563EB']
        )
        fig_cum.update_traces(line=dict(width=3), fillcolor='rgba(37, 99, 235, 0.15)')
        fig_cum.update_layout(
            margin=dict(t=15, b=20, l=10, r=10),
            height=320,
            xaxis=dict(title="Дата", showgrid=True),
            yaxis=dict(title="Накопичена кількість звернень", showgrid=True)
        )
        st.plotly_chart(fig_cum, use_container_width=True)

    else:
        st.warning("⚠️ У корпусі петицій відсутні розпізнані дати створення (2015–2026 рр.).")