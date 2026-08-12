import unicodedata

import pandas as pd
import plotly.express as px
import streamlit as st
from sqlalchemy import inspect, text

from connections import DATABASES

st.set_page_config(
    page_title="Dashboard multi-projets",
    page_icon="📊",
    layout="wide",
    initial_sidebar_state="expanded",
)

# ---------------------------------------------------------------------------
# Charte graphique CRS
# ---------------------------------------------------------------------------
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
    "web_footer": "#001F4E",
    "emergency_red": "#DA291C",
}

# Palette qualitative utilisée par défaut pour tous les graphiques Plotly.
CRS_PALETTE = [
    CRS_COLORS["crs_blue"],
    CRS_COLORS["bold_orange"],
    CRS_COLORS["bold_teal"],
    CRS_COLORS["bold_purple"],
    CRS_COLORS["bold_green"],
    CRS_COLORS["humble_gold"],
    CRS_COLORS["humble_blue"],
    CRS_COLORS["bold_blue"],
    CRS_COLORS["humble_green"],
    CRS_COLORS["humble_gray"],
]
px.defaults.color_discrete_sequence = CRS_PALETTE
px.defaults.template = "plotly_white"

st.markdown(
    f"""
    <style>
    section[data-testid="stSidebar"] {{
        background-color: #F4F8FA;
        border-right: 3px solid {CRS_COLORS['crs_blue']};
    }}
    div[data-testid="stMetric"] {{
        background-color: #FFFFFF;
        border: 1px solid #E4EBEE;
        border-left: 5px solid {CRS_COLORS['bold_blue']};
        border-radius: 8px;
        padding: 0.75rem 1rem 0.5rem 1rem;
        box-shadow: 0 1px 3px rgba(0,0,0,0.06);
    }}
    div[data-testid="stMetricValue"] {{
        color: {CRS_COLORS['crs_blue']};
    }}
    div[data-testid="stMetricLabel"] {{
        color: {CRS_COLORS['humble_gray']};
    }}
    .crs-banner {{
        background-color: {CRS_COLORS['crs_blue']};
        padding: 1.1rem 1.5rem;
        border-radius: 10px;
        margin-bottom: 1.2rem;
    }}
    .crs-banner h1 {{
        color: #FFFFFF;
        margin: 0;
        font-size: 1.7rem;
    }}
    .crs-banner p {{
        color: #CCE4F5;
        margin: 0.2rem 0 0 0;
        font-size: 0.9rem;
    }}
    .crs-section-title {{
        color: {CRS_COLORS['crs_blue']};
        border-bottom: 3px solid {CRS_COLORS['bold_orange']};
        display: inline-block;
        padding-bottom: 0.15rem;
        margin-top: 0.5rem;
    }}
    </style>
    <div class="crs-banner">
        <h1>📊 Dashboard multi-projets</h1>
        <p>Bases PostgreSQL : 137, 137est et 4101</p>
    </div>
    """,
    unsafe_allow_html=True,
)

MAX_ROWS = 50000
PRESENT_VALUES = {"yes", "true", "t", "1", "oui", "o"}
AGRI_CATEGORIES = {
    "4101": {"farming", "elevage"},
    "137est": {"farming"},
    "137": {"farming"},
}

VOLET_CONFIG = {
    "Semences / intrants agricoles": {
        "date_col": "agri_date",
        "type_col": "agri_input_type",
        "qty_cols": [
            ("mais_weight_kg", "kg de maïs"),
            ("rice_weight_kg", "kg de riz"),
            ("swpotato_qty", "unités de patate douce"),
        ],
    },
    "CUMA (cultures maraîchères)": {
        "date_col": "cuma_date",
        "type_col": "cuma_type",
        "qty_cols": [("cuma_weight_kg", "sachets")],
    },
    "Kit PMA (petit matériel)": {
        "date_col": "pma_date",
        "type_col": "pma_type",
        "qty_cols": [("arrosoir_nb", "arrosoirs"), ("beche_nb", "bêches")],
    },
}


def normalize_text(value):
    if pd.isna(value):
        return ""
    value = unicodedata.normalize("NFKD", str(value).strip().lower())
    return "".join(char for char in value if not unicodedata.combining(char))


def make_unique_key(dataframe, cin_col, name_col, age_col=None):
    """Clé bénéficiaire = NOM EN MAJUSCULES | CIN | ÂGE.

    Les doublons sont identifiés par la concaténation du nom complet, du CIN
    et de l'âge. Les lignes où ces trois champs sont vides sont exclues des
    comptages.
    """
    cin = (
        dataframe[cin_col].fillna("").astype(str).str.strip()
        if cin_col in dataframe.columns
        else pd.Series("", index=dataframe.index)
    )
    name = (
        dataframe[name_col].fillna("").astype(str).str.strip().str.upper()
        if name_col in dataframe.columns
        else pd.Series("", index=dataframe.index)
    )
    if age_col is not None and age_col in dataframe.columns:
        age_numeric = pd.to_numeric(dataframe[age_col], errors="coerce")
        age = age_numeric.apply(
            lambda value: "" if pd.isna(value) else str(int(value))
        )
    else:
        age = pd.Series("", index=dataframe.index)

    key = name + "|" + cin + "|" + age
    return key.mask((cin == "") & (name == "") & (age == ""))


def sorted_options(dataframe, column):
    """Valeurs uniques triées d'une colonne, en ignorant les vides/NaN."""
    if dataframe.empty or column not in dataframe.columns:
        return []
    values = dataframe[column].dropna().astype(str).str.strip()
    values = values[values != ""]
    return sorted(values.unique().tolist())


def apply_location_filters(dataframe, region, district, commune):
    """Filtre un DataFrame par Région / District / Commune si les colonnes existent."""
    if dataframe.empty:
        return dataframe
    filtered = dataframe
    if region != "Toutes les régions" and "region" in filtered.columns:
        filtered = filtered[
            filtered["region"].astype(str).str.strip() == region
        ]
    if district != "Tous les districts" and "district" in filtered.columns:
        filtered = filtered[
            filtered["district"].astype(str).str.strip() == district
        ]
    if commune != "Toutes les communes" and "commune" in filtered.columns:
        filtered = filtered[
            filtered["commune"].astype(str).str.strip() == commune
        ]
    return filtered


def filter_caption(region, district, commune):
    """Résumé textuel des filtres géographiques actifs."""
    parts = []
    if region != "Toutes les régions":
        parts.append(f"Région : {region}")
    if district != "Tous les districts":
        parts.append(f"District : {district}")
    if commune != "Toutes les communes":
        parts.append(f"Commune : {commune}")
    return " • ".join(parts) if parts else "Aucun filtre géographique actif"


def table_exists(project_name, table_name):
    inspector = inspect(DATABASES[project_name])
    return table_name in inspector.get_table_names(schema="public")


def get_available_columns(project_name, table_name):
    inspector = inspect(DATABASES[project_name])
    if table_name not in inspector.get_table_names(schema="public"):
        return []
    return [
        column["name"]
        for column in inspector.get_columns(table_name, schema="public")
    ]


@st.cache_data(ttl=1800)
def load_registration(project_name):
    if not table_exists(project_name, "beneficiary_registration"):
        return pd.DataFrame()

    available = get_available_columns(project_name, "beneficiary_registration")
    wanted = [
        "ben_cin", "ben_full_name", "ben_sex", "ben_age", "hh_size",
        "project_outcome", "region", "district", "commune", "fokontany",
    ]
    selected = [column for column in wanted if column in available]
    if not selected:
        return pd.DataFrame()

    select_sql = ", ".join(f'"{column}"' for column in selected)
    query = text(
        f'SELECT {select_sql} FROM public."beneficiary_registration"'
    )
    with DATABASES[project_name].connect() as connection:
        dataframe = pd.read_sql(query, connection)

    dataframe["unique_key"] = make_unique_key(
        dataframe, "ben_cin", "ben_full_name", "ben_age"
    )
    return dataframe


@st.cache_data(ttl=1800)
def load_distribution_joined(project_name):
    """Joint parent/repeat group, sans modifier la logique des quantités."""
    if not (
        table_exists(project_name, "distribution_submission")
        and table_exists(project_name, "distribution_beneficiary")
    ):
        return pd.DataFrame()

    sub_columns = get_available_columns(project_name, "distribution_submission")
    ben_columns = get_available_columns(project_name, "distribution_beneficiary")

    wanted_sub = [
        "kobo_uuid", "submission_time", "submitted_by", "region", "district",
        "commune", "fokontany", "project_code", "sector", "cuma_date",
        "cuma_type", "cuma_weight_kg", "agri_date", "agri_input_type",
        "mais_weight_kg", "rice_weight_kg", "swpotato_qty", "swpotato_unit",
        "pma_date", "pma_type", "arrosoir_nb", "beche_nb", "nb_beneficiaries",
    ]
    wanted_ben = [
        "id", "seq_num", "present", "village",
        # PII chargées uniquement pour calculer unique_key, puis supprimées.
        "full_name", "sex", "age", "cin",
        "ben_id_raw", "submission_uuid",
    ]

    selected_sub = [column for column in wanted_sub if column in sub_columns]
    selected_ben = [column for column in wanted_ben if column in ben_columns]

    select_parts = [f'ds."{column}"' for column in selected_sub]
    for column in selected_ben:
        alias = "beneficiary_row_id" if column == "id" else column
        select_parts.append(f'db."{column}" AS "{alias}"')

    query = text(f"""
        SELECT {", ".join(select_parts)}
        FROM public.distribution_submission ds
        JOIN public.distribution_beneficiary db
          ON db.submission_uuid = ds.kobo_uuid
    """)
    with DATABASES[project_name].connect() as connection:
        dataframe = pd.read_sql(query, connection)

    dataframe["unique_key"] = make_unique_key(dataframe, "cin", "full_name", "age")

    # Avant tout affichage, supprimer les données nominatives du DataFrame.
    sensitive_columns = [
        column for column in ["cin", "full_name", "sex", "age"]
        if column in dataframe.columns
    ]
    dataframe = dataframe.drop(columns=sensitive_columns)
    return dataframe


@st.cache_data(ttl=1800)
def get_seed_quality_issues(project_name):
    """Contrôle informatif Maïs/Riz enregistrés dans cuma_type."""
    if not table_exists(project_name, "distribution_submission"):
        return pd.DataFrame()

    available = get_available_columns(project_name, "distribution_submission")
    if "cuma_type" not in available:
        return pd.DataFrame()

    wanted = [
        "kobo_uuid", "submission_time", "submitted_by", "region", "district",
        "commune", "fokontany", "cuma_type", "cuma_weight_kg",
        "mais_weight_kg", "rice_weight_kg",
    ]
    selected = [column for column in wanted if column in available]
    select_sql = ", ".join(f'"{column}"' for column in selected)

    query = text(
        f'SELECT {select_sql} FROM public."distribution_submission"'
    )
    with DATABASES[project_name].connect() as connection:
        issues = pd.read_sql(query, connection)

    issues["cuma_type_normalise"] = issues["cuma_type"].map(normalize_text)
    issues = issues[
        issues["cuma_type_normalise"].isin(["mais", "riz"])
    ].copy()
    issues["Semence mal catégorisée"] = issues["cuma_type_normalise"].map(
        {"mais": "Maïs", "riz": "Riz"}
    )
    return issues


def compute_volet_metrics(dataframe, volet_key):
    """Logique originale : filtre par date et somme les quantités individuelles."""
    config = VOLET_CONFIG[volet_key]
    date_column = config["date_col"]

    if date_column not in dataframe.columns:
        return None

    volet = dataframe[dataframe[date_column].notna()].copy()
    if volet.empty:
        return None

    participants = int(volet["unique_key"].nunique(dropna=True))

    absent = None
    if "present" in volet.columns:
        present_normalized = volet["present"].map(normalize_text)
        absent = int(
            volet.loc[~present_normalized.isin(PRESENT_VALUES), "unique_key"]
            .nunique(dropna=True)
        )

    quantity_rows = []
    detail_quantity_columns = []
    for quantity_column, label in config["qty_cols"]:
        if quantity_column not in volet.columns:
            continue
        quantity = pd.to_numeric(volet[quantity_column], errors="coerce")
        total = quantity.sum()
        if quantity.notna().sum() == 0 or pd.isna(total) or total == 0:
            continue

        beneficiary_count = int(
            volet.loc[
                quantity.notna() & quantity.gt(0),
                "unique_key",
            ].nunique(dropna=True)
        )

        quantity_rows.append({
            "Quantité": label,
            "Total distribué": round(float(total), 2),
            "Nombre bénéficiaires": beneficiary_count,
        })
        detail_column = f"_est_{quantity_column}"
        volet[detail_column] = quantity
        detail_quantity_columns.append(detail_column)

    return {
        "n_participants": participants,
        "n_absent": absent,
        "qty_summary": pd.DataFrame(quantity_rows),
        "detail_df": volet,
        "est_cols": detail_quantity_columns,
        "type_col": config["type_col"],
    }


def project_kpis(
    project_name,
    region="Toutes les régions",
    district="Tous les districts",
    commune="Toutes les communes",
):
    registration = apply_location_filters(
        load_registration(project_name), region, district, commune
    )
    distribution = apply_location_filters(
        load_distribution_joined(project_name), region, district, commune
    )

    unique_beneficiaries = int(registration["unique_key"].nunique(dropna=True)) if not registration.empty else 0

    categories = AGRI_CATEGORIES.get(project_name, {"farming"})
    if not registration.empty and "project_outcome" in registration.columns:
        outcome = registration["project_outcome"].map(normalize_text)
        agriculture_keys = registration.loc[
            outcome.isin(categories), "unique_key"
        ]
        agriculture_beneficiaries = int(agriculture_keys.nunique(dropna=True))
    else:
        agriculture_beneficiaries = 0

    if not distribution.empty and "present" in distribution.columns:
        present_mask = distribution["present"].map(normalize_text).isin(PRESENT_VALUES)
        present_beneficiaries = int(
            distribution.loc[present_mask, "unique_key"].nunique(dropna=True)
        )
    else:
        present_beneficiaries = 0

    absent_beneficiaries = max(
        0, agriculture_beneficiaries - present_beneficiaries
    )
    presence_rate = (
        present_beneficiaries / agriculture_beneficiaries * 100
        if agriculture_beneficiaries > 0
        else 0.0
    )

    return {
        "registration": registration,
        "distribution": distribution,
        "unique_beneficiaries": unique_beneficiaries,
        "agriculture_beneficiaries": agriculture_beneficiaries,
        "present_beneficiaries": present_beneficiaries,
        "absent_beneficiaries": absent_beneficiaries,
        "presence_rate": presence_rate,
    }


st.sidebar.markdown("### 🧭 Navigation")
page = st.sidebar.radio(
    "Choisir une page",
    ["Vue globale", "Suivi des distributions", "Qualité des données"],
    label_visibility="collapsed",
)

st.sidebar.divider()
st.sidebar.markdown("### 📁 Projet")
selected_project = st.sidebar.selectbox(
    "Projet", list(DATABASES.keys()), label_visibility="collapsed"
)

st.sidebar.divider()
st.sidebar.markdown("### 🗺️ Filtres géographiques")

# Source de référence pour peupler les listes déroulantes en cascade.
_location_source = load_registration(selected_project)
if _location_source.empty:
    _location_source = load_distribution_joined(selected_project)

selected_region = st.sidebar.selectbox(
    "Région",
    ["Toutes les régions"] + sorted_options(_location_source, "region"),
)

_district_source = (
    _location_source
    if selected_region == "Toutes les régions"
    else _location_source[
        _location_source.get("region", pd.Series(dtype="object"))
        .astype(str).str.strip() == selected_region
    ]
)
selected_district = st.sidebar.selectbox(
    "District",
    ["Tous les districts"] + sorted_options(_district_source, "district"),
)

_commune_source = (
    _district_source
    if selected_district == "Tous les districts"
    else _district_source[
        _district_source.get("district", pd.Series(dtype="object"))
        .astype(str).str.strip() == selected_district
    ]
)
selected_commune = st.sidebar.selectbox(
    "Commune",
    ["Toutes les communes"] + sorted_options(_commune_source, "commune"),
)

if st.sidebar.button("↺ Réinitialiser les filtres"):
    st.session_state.clear()
    st.rerun()


if page == "Vue globale":
    metrics = project_kpis(
        selected_project, selected_region, selected_district, selected_commune
    )
    registration = metrics["registration"]

    st.markdown(
        f'<h2 class="crs-section-title">Vue globale — {selected_project}</h2>',
        unsafe_allow_html=True,
    )
    st.caption(filter_caption(selected_region, selected_district, selected_commune))

    if registration.empty:
        st.warning(
            f"Aucune donnée bénéficiaire disponible pour {selected_project} "
            "avec les filtres sélectionnés."
        )
        st.stop()

    sex_values = registration.get(
        "ben_sex", pd.Series(index=registration.index, dtype="object")
    ).map(normalize_text)
    men = int(sex_values.isin(["male", "m", "homme", "masculin"]).sum())
    women = int(sex_values.isin(["female", "f", "femme", "feminin"]).sum())

    household_size = (
        pd.to_numeric(registration["hh_size"], errors="coerce")
        if "hh_size" in registration.columns
        else pd.Series(dtype=float)
    )
    household_mean = (
        float(household_size.mean()) if household_size.notna().any() else 0.0
    )

    st.markdown("##### 👥 Démographie")
    row1 = st.columns(4)
    row1[0].metric("Bénéficiaires uniques", f'{metrics["unique_beneficiaries"]:,}')
    row1[1].metric("Hommes", f"{men:,}")
    row1[2].metric("Femmes", f"{women:,}")
    row1[3].metric("Taille moyenne du ménage", f"{household_mean:.1f}")

    st.markdown("##### 🌾 Agriculture &amp; distribution")
    row2 = st.columns(4)
    row2[0].metric("Bénéficiaires Agriculture/Farming", f'{metrics["agriculture_beneficiaries"]:,}')
    row2[1].metric("Présents aux distributions", f'{metrics["present_beneficiaries"]:,}')
    row2[2].metric("Absents aux distributions", f'{metrics["absent_beneficiaries"]:,}')
    row2[3].metric("Taux de présence", f'{metrics["presence_rate"]:.1f}%')

    st.divider()
    left, right = st.columns(2)

    with left:
        sex_labels = pd.Series("Non renseigné", index=registration.index)
        sex_labels.loc[
            sex_values.isin(["male", "m", "homme", "masculin"])
        ] = "Hommes"
        sex_labels.loc[
            sex_values.isin(["female", "f", "femme", "feminin"])
        ] = "Femmes"
        sex_summary = (
            sex_labels[sex_labels != "Non renseigné"]
            .value_counts()
            .rename_axis("Genre")
            .reset_index(name="Bénéficiaires")
        )
        if not sex_summary.empty:
            sex_figure = px.bar(
                sex_summary,
                x="Genre",
                y="Bénéficiaires",
                color="Genre",
                text="Bénéficiaires",
                title="Répartition des bénéficiaires par genre",
            )
            sex_figure.update_layout(showlegend=False)
            sex_figure.update_traces(textposition="outside")
            st.plotly_chart(sex_figure, use_container_width=True)

    with right:
        if "ben_age" in registration.columns:
            age = pd.to_numeric(registration["ben_age"], errors="coerce")
            age_band = pd.cut(
                age,
                bins=[-1, 4, 11, 17, 24, 35, 49, 64, float("inf")],
                labels=[
                    "0-4", "5-11", "12-17", "18-24",
                    "25-35", "36-49", "50-64", "65+",
                ],
                ordered=True,
            )
            age_summary = (
                age_band.dropna()
                .value_counts(sort=False)
                .rename_axis("Tranche d'âge")
                .reset_index(name="Bénéficiaires")
            )
            age_figure = px.bar(
                age_summary,
                x="Tranche d'âge",
                y="Bénéficiaires",
                color="Tranche d'âge",
                text="Bénéficiaires",
                title="Répartition des bénéficiaires par tranche d'âge",
            )
            age_figure.update_layout(showlegend=False)
            age_figure.update_traces(textposition="outside")
            st.plotly_chart(age_figure, use_container_width=True)

    if "project_outcome" in registration.columns:
        outcome_summary = (
            registration.assign(
                Catégorie=registration["project_outcome"].fillna("Non renseigné")
            )
            .groupby("Catégorie")["unique_key"]
            .nunique()
            .reset_index(name="Bénéficiaires uniques")
            .sort_values("Bénéficiaires uniques", ascending=False)
        )
        st.subheader("Bénéficiaires uniques par catégorie")
        st.dataframe(outcome_summary, use_container_width=True, hide_index=True)
        outcome_figure = px.bar(
            outcome_summary,
            x="Catégorie",
            y="Bénéficiaires uniques",
            color="Catégorie",
            text="Bénéficiaires uniques",
        )
        outcome_figure.update_layout(showlegend=False)
        outcome_figure.update_traces(textposition="outside")
        st.plotly_chart(outcome_figure, use_container_width=True)


elif page == "Suivi des distributions":
    st.markdown(
        f'<h2 class="crs-section-title">Suivi des distributions — {selected_project}</h2>',
        unsafe_allow_html=True,
    )
    st.caption(filter_caption(selected_region, selected_district, selected_commune))

    dataframe = apply_location_filters(
        load_distribution_joined(selected_project),
        selected_region, selected_district, selected_commune,
    )

    if dataframe.empty:
        st.info(
            f"Le projet {selected_project} n'a pas de données de distribution "
            "pour les filtres sélectionnés."
        )
        st.stop()

    if st.button("🔄 Rafraîchir les données"):
        load_distribution_joined.clear()
        load_registration.clear()
        get_seed_quality_issues.clear()
        st.rerun()

    unique_beneficiaries = int(dataframe["unique_key"].nunique(dropna=True))
    present_beneficiaries = 0
    if "present" in dataframe.columns:
        present_mask = dataframe["present"].map(normalize_text).isin(PRESENT_VALUES)
        present_beneficiaries = int(
            dataframe.loc[present_mask, "unique_key"].nunique(dropna=True)
        )

    top1, top2 = st.columns(2)
    top1.metric("Bénéficiaires uniques", f"{unique_beneficiaries:,}")
    top2.metric("Présents uniques", f"{present_beneficiaries:,}")

    available_volets = [
        name
        for name, config in VOLET_CONFIG.items()
        if config["date_col"] in dataframe.columns
        and dataframe[config["date_col"]].notna().any()
    ]

    if not available_volets:
        st.info("Aucun volet de distribution ne contient de données.")
        st.stop()

    selected_volet = st.selectbox("Type de distribution", available_volets)
    volet_metrics = compute_volet_metrics(dataframe, selected_volet)

    if volet_metrics is None:
        st.info("Pas de données exploitables pour ce volet.")
        st.stop()

    k1, k2 = st.columns(2)
    k1.metric("Bénéficiaires uniques concernés", f'{volet_metrics["n_participants"]:,}')
    if volet_metrics["n_absent"] is not None:
        k2.metric("Bénéficiaires uniques absents", f'{volet_metrics["n_absent"]:,}')

    if not volet_metrics["qty_summary"].empty:
        st.subheader("Quantités distribuées")
        st.dataframe(
            volet_metrics["qty_summary"], use_container_width=True, hide_index=True
        )
        quantity_figure = px.bar(
            volet_metrics["qty_summary"],
            x="Quantité",
            y="Total distribué",
            text="Total distribué",
            title=f"Quantités distribuées : {selected_volet}",
        )
        quantity_figure.update_traces(textposition="outside")
        st.plotly_chart(quantity_figure, use_container_width=True)

    detail = volet_metrics["detail_df"]
    type_column = volet_metrics["type_col"]

    if type_column in detail.columns and detail[type_column].notna().any():
        if selected_volet.startswith("CUMA"):
            type_values = (
                detail[type_column]
                .dropna()
                .astype(str)
                .str.split(",")
                .explode()
                .str.strip()
            )
            type_values = type_values[type_values != ""]
            type_summary = (
                type_values.value_counts()
                .rename_axis("Culture (CUMA)")
                .reset_index(name="Nombre de lignes")
            )
        else:
            type_summary = (
                detail[type_column]
                .dropna()
                .astype(str)
                .value_counts()
                .rename_axis(type_column)
                .reset_index(name="Nombre de lignes")
            )
        st.dataframe(type_summary, use_container_width=True, hide_index=True)

    display_columns = [
        column
        for column in [
            "submission_uuid", "present", "village",
            "cuma_type", "mais_weight_kg", "rice_weight_kg",
            "swpotato_qty", "cuma_weight_kg",
        ]
        if column in detail.columns
    ]
    st.subheader("Détail des bénéficiaires")
    st.caption(
        "CIN, nom complet, sexe et âge sont masqués pour la publication. "
        "submission_uuid est conservé comme identifiant technique."
    )
    st.dataframe(detail[display_columns], use_container_width=True, hide_index=True)


elif page == "Qualité des données":
    st.markdown(
        f'<h2 class="crs-section-title">Qualité des données — {selected_project}</h2>',
        unsafe_allow_html=True,
    )
    st.caption(filter_caption(selected_region, selected_district, selected_commune))

    st.subheader("⚠️ Semences enregistrées dans CUMA")
    st.caption(
        "Contrôle informatif uniquement : aucun calcul de distribution n'est modifié."
    )

    issues = apply_location_filters(
        get_seed_quality_issues(selected_project),
        selected_region, selected_district, selected_commune,
    )
    if issues.empty:
        st.success("Aucune soumission avec cuma_type = Maïs/Mais ou Riz.")
    else:
        maize_count = int((issues["cuma_type_normalise"] == "mais").sum())
        rice_count = int((issues["cuma_type_normalise"] == "riz").sum())

        q1, q2, q3 = st.columns(3)
        q1.metric("Soumissions concernées", f"{len(issues):,}")
        q2.metric("Maïs enregistré dans CUMA", f"{maize_count:,}")
        q3.metric("Riz enregistré dans CUMA", f"{rice_count:,}")

        issue_summary = (
            issues.groupby("Semence mal catégorisée")
            .size()
            .reset_index(name="Nombre de soumissions")
        )
        issue_figure = px.bar(
            issue_summary,
            x="Semence mal catégorisée",
            y="Nombre de soumissions",
            color="Semence mal catégorisée",
            text="Nombre de soumissions",
            title="Semences enregistrées dans cuma_type",
        )
        issue_figure.update_layout(showlegend=False)
        issue_figure.update_traces(textposition="outside")
        st.plotly_chart(issue_figure, use_container_width=True)

        issue_columns = [
            column
            for column in [
                "kobo_uuid", "submission_time", "submitted_by", "region",
                "district", "commune", "fokontany", "cuma_type",
                "mais_weight_kg", "rice_weight_kg", "cuma_weight_kg",
                "Semence mal catégorisée",
            ]
            if column in issues.columns
        ]
        st.dataframe(issues[issue_columns], use_container_width=True, hide_index=True)
        st.download_button(
            "Télécharger les anomalies",
            data=issues[issue_columns].to_csv(index=False).encode("utf-8-sig"),
            file_name=f"{selected_project}_semences_mal_categorisees.csv",
            mime="text/csv",
        )

    st.divider()
    inspector = inspect(DATABASES[selected_project])
    available_tables = inspector.get_table_names(schema="public")
    selected_table = st.selectbox("Table à contrôler", available_tables)

    query = text(
        f'SELECT * FROM public."{selected_table}" LIMIT {MAX_ROWS}'
    )
    with DATABASES[selected_project].connect() as connection:
        quality_dataframe = pd.read_sql(query, connection)

    duplicates = int(quality_dataframe.duplicated().sum())
    c1, c2 = st.columns(2)
    c1.metric("Lignes analysées", f"{len(quality_dataframe):,}")
    c2.metric("Doublons complets", f"{duplicates:,}")

    numeric_columns = quality_dataframe.select_dtypes(include="number").columns.tolist()
    if numeric_columns:
        numeric_column = st.selectbox("Variable numérique", numeric_columns)
        box_figure = px.box(
            quality_dataframe,
            y=numeric_column,
            points="outliers",
            title=f"Valeurs aberrantes : {numeric_column}",
        )
        box_figure.update_traces(marker_color=CRS_COLORS["bold_blue"])
        st.plotly_chart(box_figure, use_container_width=True)
