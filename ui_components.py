import json
import textwrap
from engine import DomainContextEngine

def load_theme_config():
    """Завантажує налаштування теми або повертає значення за замовчуванням."""
    try:
        with open("theme_config.json", "r", encoding="utf-8") as f:
            return json.load(f)
    except FileNotFoundError:
        return {
            "font_family": "'Inter', -apple-system, BlinkMacSystemFont, sans-serif",
            "bg_main": "#F8FAFC",
            "bg_sidebar": "#FFFFFF",
            "bg_card": "#FFFFFF",
            "text_primary": "#0F172A",
            "text_secondary": "#475569",
            "text_sidebar": "#1E293B",
            "accent_color": "#2563EB",
            "accent_hover": "#1D4ED8",
            "border_color": "#CBD5E1"
        }

theme = load_theme_config()

# Формуємо динамічні стилі з примусовим фіолетовим акцентом
CUSTOM_CSS = f"""
<style>
    /* Базові стилі карток результатів (акордеон) */
    details.petition-card {{
        background-color: {theme.get("bg_card", "#FFFFFF")};
        border: 1px solid {theme.get("border_color", "#CBD5E1")};
        border-radius: 10px;
        padding: 1.2rem;
        margin-bottom: 1rem;
        box-shadow: 0 1px 3px 0 rgba(0, 0, 0, 0.05);
        transition: all 0.2s ease-in-out;
    }}
    
    /* Примусово робимо рамку фіолетовою при наведенні або відкритті */
    details.petition-card[open],
    details.petition-card:hover {{
        border-color: #7C3AED !important;
        box-shadow: 0 4px 6px -1px rgba(124, 58, 237, 0.12) !important;
    }}
    
    /* Інтерактивний заголовок */
    details.petition-card summary {{
        list-style: none;
        cursor: pointer;
        outline: none;
    }}
    details.petition-card summary::-webkit-details-marker {{
        display: none;
    }}
    
    /* Тіло картки після розгортання */
    .petition-body {{
        margin-top: 1rem;
        padding-top: 1rem;
        border-top: 1px dashed {theme.get("border_color", "#CBD5E1")};
        color: {theme.get("text_primary", "#0F172A")};
        font-size: 0.95rem;
        line-height: 1.6;
    }}
    
    .expand-hint {{
        color: #7C3AED !important;
        font-size: 0.82rem;
        font-weight: 500;
        margin-top: 6px;
    }}

    /* Бейджі статусів */
    .badge-duplicate {{
        background-color: #FEE2E2;
        color: #991B1B;
        font-weight: 700;
        padding: 4px 10px;
        border-radius: 6px;
        font-size: 0.85rem;
    }}
    .badge-review {{
        background-color: #FEF3C7;
        color: #92400E;
        font-weight: 700;
        padding: 4px 10px;
        border-radius: 6px;
        font-size: 0.85rem;
    }}
    .badge-unique {{
        background-color: #DCFCE7;
        color: #166534;
        font-weight: 700;
        padding: 4px 10px;
        border-radius: 6px;
        font-size: 0.85rem;
    }}
</style>
"""

def render_petition_card(row) -> str:
  """Формує чисту HTML-розмітку для окремої петиції-картки."""
  raw_text = row.get("text", "")
  clean_desc = DomainContextEngine.clean_html(raw_text)
  has_text = (
      clean_desc and not clean_desc.endswith(".txt") and clean_desc != "nan"
  )

  if has_text:
    body_html = f"<b>Повний зміст звернення:</b><br>{clean_desc}"
  else:
    body_html = "<i>Повний текст петиції не було надано автором або він відсутній у первинному вивантаженні.</i>"

  reasons_html = ""
  reasons_data = row.get("reasons", [])
  if reasons_data:
    reasons_list = (
        reasons_data if isinstance(reasons_data, list) else [str(reasons_data)]
    )
    reasons_html = (
        "<br><span style='color: #DC2626; font-size: 0.88rem; font-weight:"
        f" 600;'>ℹ️ <b>Фільтрація NER:</b> {'; '.join(reasons_list)}</span>"
    )

  # --- ФОРМАТУВАННЯ БАЗОВОЇ СЕМАНТИКИ (4 знаки після коми) ---
  base_val = row.get("base_score", 0.0)
  formatted_base_score = f"{float(base_val):.4f}"

  return textwrap.dedent(f"""
    <details class="petition-card">
    <summary>
    <div style="display: flex; justify-content: space-between; align-items: center; margin-bottom: 8px;">
        <span class="{row['badge_class']}">{row['status_text']} | Оцінка: {row['final_score']}</span>
        <span style="color: #6B7280; font-size: 0.85rem;">Базова семантика: {formatted_base_score}</span>
    </div>
    <div style="font-size: 1.15rem; font-weight: 600; color: #111827; margin-bottom: 4px;">{row['title']}</div>
    <div style="font-size: 0.85rem; color: #4B5563;"><b>Розпорядник:</b> {row.get('authority', 'Не вказано')} &nbsp;|&nbsp; <b>Автор:</b> {row.get('author', 'Невідомий')}</div>
    <div class="expand-hint">▼ Натисніть, щоб переглянути деталі та текст звернення</div>
    </summary>
    <div class="petition-body">
        {body_html}
        {reasons_html}
    </div>
    </details>
    """).strip()