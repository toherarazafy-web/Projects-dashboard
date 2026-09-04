import pandas as pd
import plotly.express as px
import streamlit as st
from sqlalchemy import text

from connections import DATABASES

engine = DATABASES["124"]

CRS_COLORS = {
    "bold_blue": "#00A2C7",
    "crs_blue": "#00468B",
    "bold_purple": "#9053A1",
    "bold_teal": "#0099A9",
    "bold_green": "#79A02C",
    "bold_orange": "#EF6E0B",
    "humble_gray": "#9D9385",
    "humble_blue": "#7A99AC",
    "humble_green": "#9B9455",
    "humble_gold": "#B48F4B",
}

st.markdown(
    f"""
    <style>

    div[data-testid="stMetric"] {{
        background-color: #FFFFFF;
        border: 1px solid #E4EBEE;
        border-left: 5px solid {CRS_COLORS['bold_blue']};
        border-radius: 8px;
        padding: 0.75rem 1rem;
    }}

    div[data-testid="stMetricValue"] {{
        color: {CRS_COLORS['crs_blue']};
    }}

    .crs-banner {{
        background-color: {CRS_COLORS['crs_blue']};
        padding: 1.2rem;
        border-radius: 10px;
        margin-bottom: 1rem;
    }}

    .crs-banner h1 {{
        color: white;
        margin: 0;
    }}

    .crs-banner p {{
        color: #CCE4F5;
        margin-top: 0.25rem;
    }}

    </style>
    """,
    unsafe_allow_html=True,
)

st.markdown(
    """
    <div class="crs-banner">
        <h1>🌾 Dashboard Projet 124</h1>
        <p>Bénéficiaires • Cultures • Parcelles • Distributions</p>
    </div>
    """,
    unsafe_allow_html=True,
)

# ============================================================
# KPI
# ============================================================

benef = pd.read_sql(
    text("""
    SELECT COUNT(*) nb
    FROM beneficiary_registration
    """),
    engine
)

crop = pd.read_sql(
    text("""
    SELECT COUNT(*) nb
    FROM beneficiary_registration_crop
    """),
    engine
)

plot = pd.read_sql(
    text("""
    SELECT COUNT(*) nb
    FROM beneficiary_registration_plot
    """),
    engine
)

dist = pd.read_sql(
    text("""
    SELECT COUNT(*) nb
    FROM distribution_submission
    """),
    engine
)

pms = pd.read_sql(
    text("""
    SELECT COUNT(DISTINCT pms_id) nb
    FROM distribution_beneficiary
    """),
    engine
)

maize = pd.read_sql(
    text("""
    SELECT COALESCE(SUM(mais_weight_kg),0) kg
    FROM distribution_submission
    """),
    engine
)

row1 = st.columns(6)

row1[0].metric(
    "Bénéficiaires",
    int(benef.iloc[0]["nb"])
)

row1[1].metric(
    "Cultures",
    int(crop.iloc[0]["nb"])
)

row1[2].metric(
    "Parcelles",
    int(plot.iloc[0]["nb"])
)

row1[3].metric(
    "Distributions",
    int(dist.iloc[0]["nb"])
)

row1[4].metric(
    "PMS uniques",
    int(pms.iloc[0]["nb"])
)

row1[5].metric(
    "Kg maïs",
    round(float(maize.iloc[0]["kg"]), 1)
)

st.divider()

# ============================================================
# SEXE
# ============================================================

sex_df = pd.read_sql(
    text("""
    SELECT
        sexe,
        COUNT(*) nb
    FROM beneficiary_registration
    GROUP BY sexe
    """),
    engine
)

col1, col2 = st.columns(2)

with col1:

    fig = px.pie(
        sex_df,
        names="sexe",
        values="nb",
        title="Répartition par sexe"
    )

    st.plotly_chart(
        fig,
        use_container_width=True
    )

# ============================================================
# DISTRICT
# ============================================================

district_df = pd.read_sql(
    text("""
    SELECT
        district,
        COUNT(*) nb
    FROM beneficiary_registration
    GROUP BY district
    ORDER BY nb DESC
    """),
    engine
)

with col2:

    fig = px.bar(
        district_df,
        x="district",
        y="nb",
        text="nb",
        title="Bénéficiaires par district"
    )

    st.plotly_chart(
        fig,
        use_container_width=True
    )

st.divider()

# ============================================================
# CULTURES
# ============================================================

st.subheader("🌱 Cultures")

crop_df = pd.read_sql(
    text("""
    SELECT
        crop_name,
        COUNT(*) nb
    FROM beneficiary_registration_crop
    GROUP BY crop_name
    ORDER BY nb DESC
    """),
    engine
)

fig = px.bar(
    crop_df,
    x="crop_name",
    y="nb",
    text="nb",
    title="Cultures enregistrées"
)

st.plotly_chart(
    fig,
    use_container_width=True
)

# ============================================================
# VARIETES
# ============================================================

st.subheader("🌾 Variétés")

variety_df = pd.read_sql(
    text("""
    SELECT
        variety,
        COUNT(*) nb
    FROM beneficiary_registration_crop
    GROUP BY variety
    ORDER BY nb DESC
    """),
    engine
)

st.dataframe(
    variety_df,
    use_container_width=True,
    hide_index=True
)

# ============================================================
# PARCELLES
# ============================================================

st.subheader("🧭 Parcelles")

plot_df = pd.read_sql(
    text("""
    SELECT
        antecedent_culture,
        COUNT(*) nb
    FROM beneficiary_registration_plot
    GROUP BY antecedent_culture
    ORDER BY nb DESC
    """),
    engine
)

fig = px.bar(
    plot_df,
    x="antecedent_culture",
    y="nb",
    text="nb",
    title="Antécédents culturaux"
)

st.plotly_chart(
    fig,
    use_container_width=True
)

surface_df = pd.read_sql(
    text("""
    SELECT
        COUNT(*) nb_parcelles,
        ROUND(SUM(surface_ha)::numeric,2) surface_totale,
        ROUND(AVG(surface_ha)::numeric,4) surface_moyenne
    FROM beneficiary_registration_plot
    """),
    engine
)

st.dataframe(
    surface_df,
    use_container_width=True,
    hide_index=True
)

# ============================================================
# DISTRIBUTIONS
# ============================================================

st.divider()

st.subheader("📦 Résumé des distributions")

resume_distribution = pd.read_sql(
    text("""
    SELECT
        COUNT(*) nb_soumissions,
        SUM(mais_weight_kg) kg_mais
    FROM distribution_submission
    """),
    engine
)

resume_pms = pd.read_sql(
    text("""
    SELECT
        COUNT(DISTINCT pms_id) nb_pms
    FROM distribution_beneficiary
    """),
    engine
)

c1, c2, c3 = st.columns(3)

c1.metric(
    "Soumissions",
    int(resume_distribution.iloc[0]["nb_soumissions"])
)

c2.metric(
    "PMS uniques",
    int(resume_pms.iloc[0]["nb_pms"])
)

c3.metric(
    "Kg maïs distribués",
    round(float(resume_distribution.iloc[0]["kg_mais"]), 1)
)

st.subheader("🚚 Distributions par région, district et commune")

distribution_table = pd.read_sql(
    text("""
    WITH dist AS (
        SELECT
            kobo_uuid,
            region,
            district,
            commune,
            mais_weight_kg
        FROM distribution_submission
    )

    SELECT
        d.region,
        d.district,
        d.commune,
        COUNT(DISTINCT d.kobo_uuid) AS nb_soumissions,
        COUNT(DISTINCT b.pms_id) AS nb_pms,
        ROUND(
            SUM(d.mais_weight_kg)::numeric,
            2
        ) AS kg_mais
    FROM dist d
    LEFT JOIN distribution_beneficiary b
         ON d.kobo_uuid = b.submission_uuid
    GROUP BY
        d.region,
        d.district,
        d.commune
    ORDER BY
        d.region,
        d.district,
        d.commune
    """),
    engine
)

distribution_table.columns = [
    "Région",
    "District",
    "Commune",
    "Soumissions",
    "PMS uniques",
    "Kg maïs"
]

st.dataframe(
    distribution_table,
    use_container_width=True,
    hide_index=True
)

st.download_button(
    "📥 Télécharger distributions",
    distribution_table.to_csv(
        index=False
    ).encode("utf-8-sig"),
    file_name="distribution_124.csv",
    mime="text/csv",
)

# ============================================================
# GPS
# ============================================================

st.divider()

st.subheader("📍 Localisation GPS")

gps = pd.read_sql(
    text("""
    SELECT
        gps_lat,
        gps_lon
    FROM beneficiary_registration
    WHERE gps_lat IS NOT NULL
      AND gps_lon IS NOT NULL
    """),
    engine
)

if not gps.empty:

    gps = gps.rename(
        columns={
            "gps_lat": "lat",
            "gps_lon": "lon"
        }
    )

    st.map(gps)

# ============================================================
# QUALITE DES DONNEES
# ============================================================

st.divider()

st.subheader("✅ Qualité des données")

quality = pd.read_sql(
    text("""
    SELECT
        COUNT(*) total_beneficiaires,
        COUNT(gps_lat) gps_renseignes,
        COUNT(ben_id_number) cin_renseignes
    FROM beneficiary_registration
    """),
    engine
)

st.dataframe(
    quality,
    use_container_width=True,
    hide_index=True
)