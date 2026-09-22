# -*- coding: utf-8 -*-
"""Page d'accueil Streamlit des dashboards multi-projets."""

import unicodedata
import pandas as pd
import plotly.express as px
import streamlit as st
from sqlalchemy import inspect, text

from connections import DATABASES


# =============================================================================
# CONFIGURATION
# =============================================================================
st.set_page_config(
    page_title="Dashboard multi-projets",
    page_icon="📊",
    layout="wide",
    initial_sidebar_state="expanded",
)

SCHEMA = "public"
PROJECTS = ["137est", "137", "4101", "124"]
PROJECT_LABELS = {
    "137est": "Projet 137est",
    "137": "Projet 137",
    "4101": "Projet 4101",
    "124": "Projet 124",
}
PAGE_LINKS = {
    "137est": "pages/1_Dashboard_137est.py",
    "137": "pages/2_Dashboard_137.py",
    "4101": "pages/3_Dashboard_4101.py",
    "124": "pages/4_Dashboard_124.py",
}
PROJECT_ICONS = {
    "137est": "🌾",
    "137": "🌱",
    "4101": "🌾",
    "124": "🌱",
}
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

px.defaults.color_discrete_sequence = list(CRS_COLORS.values())
px.defaults.template = "plotly_white"

st.markdown(
    f"""
    <style>
    section[data-testid="stSidebar"] {{
        background: #F4F8FA;
        border-right: 3px solid {CRS_COLORS['crs_blue']};
    }}
    div[data-testid="stMetric"] {{
        background: #FFFFFF;
        border: 1px solid #E4EBEE;
        border-left: 5px solid {CRS_COLORS['bold_blue']};
        border-radius: 10px;
        padding: .75rem 1rem;
        box-shadow: 0 1px 4px rgba(0,0,0,.06);
    }}
    div[data-testid="stMetricValue"] {{
        color: {CRS_COLORS['crs_blue']};
    }}
    .crs-banner {{
        background: linear-gradient(90deg, {CRS_COLORS['crs_blue']}, {CRS_COLORS['bold_blue']});
        padding: 1.25rem 1.6rem;
        border-radius: 12px;
        margin-bottom: 1.2rem;
        color: white;
    }}
    .crs-banner h1 {{margin: 0; font-size: 1.85rem;}}
    .crs-banner p {{color: #E3F4FA; margin: .25rem 0 0;}}
    .crs-section-title {{
        color: {CRS_COLORS['crs_blue']};
        border-bottom: 3px solid {CRS_COLORS['bold_orange']};
        display: inline-block;
        margin-top: .5rem;
    }}
    .project-card {{
        background: white;
        border: 1px solid #DDE7EC;
        border-top: 5px solid {CRS_COLORS['crs_blue']};
        border-radius: 12px;
        padding: 1rem;
        min-height: 120px;
        box-shadow: 0 2px 6px rgba(0,0,0,.05);
        margin-bottom: .5rem;
    }}
    .project-card h3 {{color: {CRS_COLORS['crs_blue']}; margin: 0 0 .35rem;}}
    .project-card p {{color: #52636D; margin: 0;}}
    </style>
    <div class="crs-banner">
        <h1>📊 Dashboard multi-projets</h1>
        <p>Portail central des projets 137est, 137, 4101 et 124</p>
    </div>
    """,
    unsafe_allow_html=True,
)


# =============================================================================
# FONCTIONS
# =============================================================================
def normalize_text(value):
    if pd.isna(value):
        return ""
    normalized = unicodedata.normalize("NFKD", str(value).strip().lower())
    return "".join(char for char in normalized if not unicodedata.combining(char))


def get_engine(project):
    return DATABASES.get(project)


def table_exists(project, table):
    engine = get_engine(project)
    if engine is None:
        return False
    try:
        return table in inspect(engine).get_table_names(schema=SCHEMA)
    except Exception:
        return False


def table_columns(project, table):
    engine = get_engine(project)
    if engine is None or not table_exists(project, table):
        return []
    try:
        return [
            column["name"]
            for column in inspect(engine).get_columns(table, schema=SCHEMA)
        ]
    except Exception:
        return []


def first_existing(available, candidates):
    return next((column for column in candidates if column in available), None)


def make_unique_key(df, cin_col=None, name_col=None, age_col=None):
    cin = (
        df[cin_col].fillna("").astype("string").str.strip()
        if cin_col and cin_col in df.columns
        else pd.Series("", index=df.index, dtype="string")
    )
    name = (
        df[name_col].fillna("").astype("string").str.strip().str.upper()
        if name_col and name_col in df.columns
        else pd.Series("", index=df.index, dtype="string")
    )
    age = (
        pd.to_numeric(df[age_col], errors="coerce")
        .apply(lambda value: "" if pd.isna(value) else str(int(value)))
        .astype("string")
        if age_col and age_col in df.columns
        else pd.Series("", index=df.index, dtype="string")
    )
    key = name + "|" + cin + "|" + age
    return key.mask((cin == "") & (name == "") & (age == ""))


@st.cache_data(ttl=1800, show_spinner=False)
def load_beneficiaries(project):
    """Charge beneficiary_registration en détectant les variantes de colonnes."""
    table = "beneficiary_registration"
    engine = get_engine(project)
    if engine is None:
        return pd.DataFrame(), f'Connexion DATABASES["{project}"] absente'
    available = table_columns(project, table)
    if not available:
        return pd.DataFrame(), f"Table public.{table} absente ou inaccessible"

    aliases = {
        "cin": ["ben_cin", "cin", "beneficiary_cin", "cin_beneficiaire"],
        "name": ["ben_full_name", "full_name", "nom_complet", "nom_beneficiaire", "name"],
        "sex": ["ben_sex", "sex", "sexe", "beneficiary_sex"],
        "age": ["ben_age", "age", "beneficiary_age"],
        "household_size": ["hh_size", "household_size", "taille_menage", "nombre_menage"],
        "outcome": ["project_outcome", "outcome", "secteur_activite", "sector"],
        "region": ["region"],
        "district": ["district"],
        "commune": ["commune"],
        "fokontany": ["fokontany"],
        "id": ["ben_unique_id", "code_beneficiaire", "code_benef", "beneficiary_id", "id"],
    }
    detected = {key: first_existing(available, candidates) for key, candidates in aliases.items()}
    selected = list(dict.fromkeys(column for column in detected.values() if column))
    if not selected:
        return pd.DataFrame(), "Aucune colonne bénéficiaire reconnue"

    query = "SELECT " + ", ".join(f'"{column}"' for column in selected)
    query += f' FROM public."{table}"'
    try:
        with engine.connect() as connection:
            df = pd.read_sql(text(query), connection)
    except Exception as exc:
        return pd.DataFrame(), f"Erreur de lecture : {exc}"

    rename_map = {column: logical for logical, column in detected.items() if column}
    df = df.rename(columns=rename_map)
    df["unique_key"] = make_unique_key(
        df,
        cin_col="cin" if "cin" in df.columns else None,
        name_col="name" if "name" in df.columns else None,
        age_col="age" if "age" in df.columns else None,
    )
    if df["unique_key"].notna().sum() == 0 and "id" in df.columns:
        df["unique_key"] = df["id"].astype("string").str.strip().replace("", pd.NA)
    return df, "OK"


def project_summary(project):
    df, status = load_beneficiaries(project)
    result = {
        "Projet": PROJECT_LABELS[project],
        "Code": project,
        "Bénéficiaires uniques": 0,
        "Hommes": 0,
        "Femmes": 0,
        "Sexe non renseigné": 0,
        "Âge moyen": None,
        "Taille moyenne du ménage": None,
        "Régions": 0,
        "Districts": 0,
        "Communes": 0,
        "Statut": status,
    }
    if df.empty:
        return result, df

    result["Bénéficiaires uniques"] = int(df["unique_key"].nunique(dropna=True))
    if "sex" in df.columns:
        sex = df["sex"].map(normalize_text)
        male_values = {"male", "m", "homme", "masculin"}
        female_values = {"female", "f", "femme", "feminin"}
        result["Hommes"] = int(sex.isin(male_values).sum())
        result["Femmes"] = int(sex.isin(female_values).sum())
        result["Sexe non renseigné"] = int((~sex.isin(male_values | female_values)).sum())
    if "age" in df.columns:
        age = pd.to_numeric(df["age"], errors="coerce")
        result["Âge moyen"] = round(float(age.mean()), 1) if age.notna().any() else None
    if "household_size" in df.columns:
        household = pd.to_numeric(df["household_size"], errors="coerce")
        result["Taille moyenne du ménage"] = round(float(household.mean()), 1) if household.notna().any() else None
    for column, label in [("region", "Régions"), ("district", "Districts"), ("commune", "Communes")]:
        if column in df.columns:
            result[label] = int(df[column].dropna().astype(str).str.strip().replace("", pd.NA).nunique())
    return result, df


def navigate_to(page_path, label, icon):
    """Affiche un lien interne Streamlit avec repli compatible anciennes versions."""
    try:
        st.page_link(page_path, label=label, icon=icon, use_container_width=True)
    except TypeError:
        st.page_link(page_path, label=label, icon=icon)
    except AttributeError:
        st.info(f"Ouvrez la page {label} dans le menu Pages de Streamlit.")


# =============================================================================
# BARRE LATÉRALE
# =============================================================================
st.sidebar.markdown("### 🏠 Accueil")
st.sidebar.caption("Vue consolidée des bénéficiaires")
st.sidebar.divider()
st.sidebar.markdown("### 📁 Pages des projets")
for project in PROJECTS:
    navigate_to(PAGE_LINKS[project], PROJECT_LABELS[project], PROJECT_ICONS[project])

if st.sidebar.button("↺ Actualiser les données", use_container_width=True):
    st.cache_data.clear()
    st.rerun()


# =============================================================================
# LIENS VERS LES PAGES
# =============================================================================
st.markdown('<h2 class="crs-section-title">Accès aux projets</h2>', unsafe_allow_html=True)
columns_ui = st.columns(4)
for column, project in zip(columns_ui, PROJECTS):
    with column:
        st.markdown(
            f"""
            <div class="project-card">
                <h3>{PROJECT_ICONS[project]} {PROJECT_LABELS[project]}</h3>
                <p>Ouvrir le dashboard détaillé du projet.</p>
            </div>
            """,
            unsafe_allow_html=True,
        )
        navigate_to(PAGE_LINKS[project], f"Ouvrir {PROJECT_LABELS[project]}", PROJECT_ICONS[project])


# =============================================================================
# OVERVIEW DES BÉNÉFICIAIRES
# =============================================================================
st.markdown('<h2 class="crs-section-title">Overview des bénéficiaires</h2>', unsafe_allow_html=True)
st.caption("Les bénéficiaires uniques sont calculés à partir du CIN, du nom et de l’âge lorsque ces informations existent. Un identifiant bénéficiaire est utilisé en repli lorsqu’il est disponible.")

summaries = []
project_frames = {}
for project in PROJECTS:
    summary, frame = project_summary(project)
    summaries.append(summary)
    project_frames[project] = frame

summary_df = pd.DataFrame(summaries)
available_df = summary_df[summary_df["Statut"] == "OK"].copy()

total_beneficiaries = int(available_df["Bénéficiaires uniques"].sum()) if not available_df.empty else 0
total_men = int(available_df["Hommes"].sum()) if not available_df.empty else 0
total_women = int(available_df["Femmes"].sum()) if not available_df.empty else 0
available_projects = int((summary_df["Statut"] == "OK").sum())

for box, label, value in zip(
    st.columns(4),
    ["Bénéficiaires uniques", "Hommes", "Femmes", "Projets disponibles"],
    [total_beneficiaries, total_men, total_women, available_projects],
):
    box.metric(label, f"{value:,}".replace(",", " "))

left, right = st.columns([1.25, 1])
with left:
    display_columns = [
        "Projet", "Bénéficiaires uniques", "Hommes", "Femmes",
        "Sexe non renseigné", "Âge moyen", "Taille moyenne du ménage",
        "Régions", "Districts", "Communes",
    ]
    st.subheader("Résumé par projet")
    st.dataframe(summary_df[display_columns], use_container_width=True, hide_index=True)

with right:
    if not available_df.empty:
        fig = px.bar(
            available_df,
            x="Projet",
            y="Bénéficiaires uniques",
            color="Projet",
            text="Bénéficiaires uniques",
            title="Bénéficiaires uniques par projet",
        )
        fig.update_layout(showlegend=False, xaxis_title="", yaxis_title="Bénéficiaires uniques")
        st.plotly_chart(fig, use_container_width=True)
    else:
        st.info("Aucune base bénéficiaire n’est actuellement accessible.")

if not available_df.empty:
    gender_df = available_df.melt(
        id_vars="Projet",
        value_vars=["Hommes", "Femmes", "Sexe non renseigné"],
        var_name="Sexe",
        value_name="Bénéficiaires",
    )
    fig = px.bar(
        gender_df,
        x="Projet",
        y="Bénéficiaires",
        color="Sexe",
        barmode="stack",
        text="Bénéficiaires",
        title="Répartition des bénéficiaires par sexe et projet",
    )
    st.plotly_chart(fig, use_container_width=True)

# Répartition géographique consolidée lorsque les colonnes sont disponibles.
geography_rows = []
for project, frame in project_frames.items():
    if frame.empty or "region" not in frame.columns:
        continue
    temp = frame.dropna(subset=["region"]).copy()
    temp["region"] = temp["region"].astype(str).str.strip()
    temp = temp[temp["region"] != ""]
    if temp.empty:
        continue
    grouped = temp.groupby("region")["unique_key"].nunique().reset_index(name="Bénéficiaires uniques")
    grouped["Projet"] = PROJECT_LABELS[project]
    geography_rows.append(grouped)

if geography_rows:
    geography_df = pd.concat(geography_rows, ignore_index=True)
    st.subheader("Répartition régionale")
    fig = px.bar(
        geography_df,
        x="region",
        y="Bénéficiaires uniques",
        color="Projet",
        barmode="group",
        text="Bénéficiaires uniques",
        labels={"region": "Région"},
    )
    st.plotly_chart(fig, use_container_width=True)

# Afficher les problèmes de connexion ou de structure sans bloquer les autres projets.
issues = summary_df[summary_df["Statut"] != "OK"][["Projet", "Statut"]]
if not issues.empty:
    with st.expander("⚠️ Diagnostic des projets non chargés"):
        st.dataframe(issues, use_container_width=True, hide_index=True)
        st.caption("Vérifiez les clés de DATABASES dans connections.py et la présence de public.beneficiary_registration.")

st.caption("Accueil multi-projets | Les données sont actualisées depuis les bases PostgreSQL configurées dans connections.py.")
