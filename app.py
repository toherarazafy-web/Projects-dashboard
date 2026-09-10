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
        background: #FFF;
        border: 1px solid #E4EBEE;
        border-left: 5px solid {CRS_COLORS['bold_blue']};
        border-radius: 8px;
        padding: .75rem 1rem;
        box-shadow: 0 1px 3px rgba(0,0,0,.06);
    }}
    div[data-testid="stMetricValue"] {{
        color: {CRS_COLORS['crs_blue']};
    }}
    .crs-banner {{
        background: {CRS_COLORS['crs_blue']};
        padding: 1.1rem 1.5rem;
        border-radius: 10px;
        margin-bottom: 1.2rem;
        color: white;
    }}
    .crs-banner h1 {{
        margin: 0;
        font-size: 1.7rem;
    }}
    .crs-banner p {{
        color: #CCE4F5;
        margin: .2rem 0 0;
    }}
    .crs-section-title {{
        color: {CRS_COLORS['crs_blue']};
        border-bottom: 3px solid {CRS_COLORS['bold_orange']};
        display: inline-block;
    }}
    </style>
    <div class="crs-banner">
        <h1>📊 Dashboard 137 • 137EST • 4101</h1>
        <p>Bases PostgreSQL : 137, 137est et 4101</p>
    </div>
    """,
    unsafe_allow_html=True,
)

MAX_ROWS = 50000
PRESENT_VALUES = {"yes", "true", "t", "1", "oui", "o"}
AGRI_CATEGORIES = {
    "4101": {"farming"},
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
            ("groundnut_weight_kg", "kg d'arachide"),
            ("swpotato_qty", "lianes de patate douce"),
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
        "qty_cols": [
            ("arrosoir_nb", "arrosoirs"),
            ("beche_nb", "bêches"),
        ],
    },
}


def normalize_text(value):
    if pd.isna(value):
        return ""
    value = unicodedata.normalize("NFKD", str(value).strip().lower())
    return "".join(c for c in value if not unicodedata.combining(c))


def make_unique_key(df, cin_col, name_col, age_col=None):
    cin = (
        df[cin_col].fillna("").astype(str).str.strip()
        if cin_col in df.columns
        else pd.Series("", index=df.index, dtype="object")
    )
    name = (
        df[name_col].fillna("").astype(str).str.strip().str.upper()
        if name_col in df.columns
        else pd.Series("", index=df.index, dtype="object")
    )

    if age_col and age_col in df.columns:
        age = pd.to_numeric(df[age_col], errors="coerce").apply(
            lambda x: "" if pd.isna(x) else str(int(x))
        )
    else:
        age = pd.Series("", index=df.index, dtype="object")

    return (name + "|" + cin + "|" + age).mask(
        (cin == "") & (name == "") & (age == "")
    )


def table_exists(project, table):
    return table in inspect(DATABASES[project]).get_table_names(schema="public")


def columns(project, table):
    if not table_exists(project, table):
        return []
    return [
        col["name"]
        for col in inspect(DATABASES[project]).get_columns(
            table,
            schema="public",
        )
    ]


def sorted_options(df, col):
    if df.empty or col not in df.columns:
        return []
    values = df[col].dropna().astype(str).str.strip()
    return sorted(values[values != ""].unique())


def apply_location_filters(df, region, district, commune):
    filters = [
        ("region", region, "Toutes les régions"),
        ("district", district, "Tous les districts"),
        ("commune", commune, "Toutes les communes"),
    ]
    for col, value, default in filters:
        if value != default and col in df.columns:
            df = df[df[col].astype(str).str.strip() == value]
    return df


def filter_caption(region, district, commune):
    parts = []
    if region != "Toutes les régions":
        parts.append(f"Région : {region}")
    if district != "Tous les districts":
        parts.append(f"District : {district}")
    if commune != "Toutes les communes":
        parts.append(f"Commune : {commune}")
    return " • ".join(parts) if parts else "Aucun filtre géographique actif"


@st.cache_data(ttl=1800)
def load_registration(project):
    table = "beneficiary_registration"
    wanted = [
        "ben_cin",
        "ben_full_name",
        "ben_sex",
        "ben_age",
        "hh_size",
        "project_outcome",
        "region",
        "district",
        "commune",
        "fokontany",
    ]
    selected = [col for col in wanted if col in columns(project, table)]
    if not selected:
        return pd.DataFrame()

    sql = (
        "SELECT "
        + ", ".join(f'"{col}"' for col in selected)
        + f' FROM public."{table}"'
    )
    with DATABASES[project].connect() as connection:
        df = pd.read_sql(text(sql), connection)

    df["unique_key"] = make_unique_key(
        df,
        "ben_cin",
        "ben_full_name",
        "ben_age",
    )
    return df


@st.cache_data(ttl=1800)
def load_distribution_joined(project):
    submission_table = "distribution_submission"
    beneficiary_table = "distribution_beneficiary"

    if not (
        table_exists(project, submission_table)
        and table_exists(project, beneficiary_table)
    ):
        return pd.DataFrame()

    submission_columns = columns(project, submission_table)
    beneficiary_columns = columns(project, beneficiary_table)

    standard_submission_columns = [
        "kobo_uuid",
        "submission_time",
        "submitted_by",
        "region",
        "district",
        "commune",
        "fokontany",
        "project_code",
        "sector",
        "cuma_date",
        "cuma_type",
        "cuma_weight_kg",
        "agri_date",
        "agri_input_type",
        "mais_weight_kg",
        "rice_weight_kg",
        "swpotato_qty",
        "swpotato_unit",
        "pma_date",
        "pma_type",
        "arrosoir_nb",
        "beche_nb",
        "nb_beneficiaries",
    ]

    project_137_submission_columns = [
        "distribution_date",
        "agri_input_codes",
        "rice_weight",
        "groundnut_weight",
        "declared_beneficiary_count",
        "repeat_beneficiary_count",
        "registration_number",
        "enumerator_name",
        "enumerator_org",
        "agri_type",
    ]

    selected_submission_columns = list(
        dict.fromkeys(
            col
            for col in (
                standard_submission_columns
                + project_137_submission_columns
            )
            if col in submission_columns
        )
    )

    old_beneficiary_columns = [
        "id",
        "seq_num",
        "present",
        "village",
        "full_name",
        "sex",
        "age",
        "cin",
        "ben_id_raw",
        "submission_uuid",
    ]

    new_beneficiary_columns = [
        "id",
        "distribution_uuid",
        "repeat_index",
        "sequence_number",
        "beneficiary_presence",
        "beneficiary_id_raw",
        "beneficiary_location",
        "beneficiary_name",
        "beneficiary_code",
        "beneficiary_sex",
        "beneficiary_age",
        "beneficiary_cin",
        "c3_raw",
    ]

    selected_beneficiary_columns = list(
        dict.fromkeys(
            col
            for col in (
                old_beneficiary_columns
                + new_beneficiary_columns
            )
            if col in beneficiary_columns
        )
    )

    select_parts = [
        f'ds."{col}"'
        for col in selected_submission_columns
    ]
    select_parts.extend(
        f'db."{col}" AS "beneficiary_row_id"'
        if col == "id"
        else f'db."{col}"'
        for col in selected_beneficiary_columns
    )

    if "distribution_uuid" in beneficiary_columns:
        join_condition = 'db."distribution_uuid" = ds."kobo_uuid"'
    elif "submission_uuid" in beneficiary_columns:
        join_condition = 'db."submission_uuid" = ds."kobo_uuid"'
    else:
        return pd.DataFrame()

    sql = f"""
        SELECT {", ".join(select_parts)}
        FROM public."{submission_table}" ds
        INNER JOIN public."{beneficiary_table}" db
            ON {join_condition}
    """

    with DATABASES[project].connect() as connection:
        df = pd.read_sql(text(sql), connection)

    rename_mapping = {
        "distribution_uuid": "submission_uuid",
        "repeat_index": "seq_num",
        "beneficiary_presence": "present",
        "beneficiary_id_raw": "ben_id_raw",
        "beneficiary_location": "village",
        "beneficiary_name": "full_name",
        "beneficiary_sex": "sex",
        "beneficiary_age": "age",
        "beneficiary_cin": "cin",
        "distribution_date": "agri_date",
        "agri_input_codes": "agri_input_type",
        "rice_weight": "rice_weight_kg",
        "groundnut_weight": "groundnut_weight_kg",
    }

    applicable_mapping = {
        source: target
        for source, target in rename_mapping.items()
        if source in df.columns and target not in df.columns
    }
    df = df.rename(columns=applicable_mapping)

    df["unique_key"] = make_unique_key(
        df,
        "cin",
        "full_name",
        "age",
    )
    return df



@st.cache_data(ttl=1800)
def load_agro_data(project):
    """Charge public.da uniquement pour le projet 137est."""
    if project != "137est":
        return pd.DataFrame()

    if not table_exists(project, "da"):
        return pd.DataFrame()

    with DATABASES[project].connect() as connection:
        return pd.read_sql(
            text(
                f'SELECT * FROM public."da" LIMIT {MAX_ROWS}'
            ),
            connection,
        )

def project_kpis(
    project,
    region="Toutes les régions",
    district="Tous les districts",
    commune="Toutes les communes",
):
    registration = apply_location_filters(
        load_registration(project),
        region,
        district,
        commune,
    )
    distribution = apply_location_filters(
        load_distribution_joined(project),
        region,
        district,
        commune,
    )

    unique = (
        int(registration["unique_key"].nunique(dropna=True))
        if not registration.empty
        else 0
    )

    categories = AGRI_CATEGORIES.get(project, {"farming"})
    if not registration.empty and "project_outcome" in registration.columns:
        outcome = registration["project_outcome"].map(normalize_text)
        farming_keys = set(
            registration.loc[
                outcome.isin(categories),
                "unique_key",
            ].dropna().unique()
        )
    else:
        farming_keys = set()

    farming = len(farming_keys)

    if not distribution.empty and "present" in distribution.columns:
        present_mask = distribution["present"].map(normalize_text).isin(
            PRESENT_VALUES
        )
        present = int(
            distribution.loc[present_mask, "unique_key"].nunique(dropna=True)
        )
    else:
        present = 0

    absent = max(0, farming - present)
    rate = present / farming * 100 if farming else 0.0

    return {
        "registration": registration,
        "distribution": distribution,
        "unique_beneficiaries": unique,
        "agriculture_beneficiaries": farming,
        "present_beneficiaries": present,
        "absent_beneficiaries": absent,
        "presence_rate": rate,
    }


def compute_volet_metrics(df, name):
    config = VOLET_CONFIG[name]
    date_col = config["date_col"]

    if date_col not in df.columns:
        return None

    volet = df[df[date_col].notna()].copy()
    if volet.empty:
        return None

    rows = []
    for quantity_col, label in config["qty_cols"]:
        if quantity_col not in volet.columns:
            continue

        numeric_values = pd.to_numeric(
            volet[quantity_col],
            errors="coerce",
        )

        # Une quantité est enregistrée au niveau de la soumission et se répète
        # après la jointure avec les bénéficiaires. On la compte une seule fois
        # par soumission afin d'éviter de multiplier les quantités distribuées.
        if "submission_uuid" in volet.columns:
            quantity_by_submission = (
                volet.assign(_quantity=numeric_values)
                .groupby("submission_uuid", dropna=False)["_quantity"]
                .first()
            )
            total = quantity_by_submission.sum()
        else:
            total = numeric_values.sum()

        if numeric_values.notna().any() and total != 0:
            beneficiary_count = int(
                volet.loc[numeric_values.gt(0), "unique_key"].nunique(
                    dropna=True
                )
            )
            rows.append(
                {
                    "Quantité": label,
                    "Total distribué": round(float(total), 2),
                    "Nombre bénéficiaires": beneficiary_count,
                }
            )

    absent = None
    if "present" in volet.columns:
        presence_mask = volet["present"].map(normalize_text).isin(
            PRESENT_VALUES
        )
        absent = int(
            volet.loc[~presence_mask, "unique_key"].nunique(dropna=True)
        )

    return {
        "n_participants": int(volet["unique_key"].nunique(dropna=True)),
        "n_absent": absent,
        "qty_summary": pd.DataFrame(rows),
        "detail_df": volet,
        "type_col": config["type_col"],
    }


st.sidebar.markdown("### 🧭 Navigation")
page = st.sidebar.radio(
    "Choisir une page",
    [
        "Vue globale",
        "Suivi des distributions",
        "Suivi données agro",
        "Qualité des données",
    ],
    label_visibility="collapsed",
)

st.sidebar.divider()
st.sidebar.markdown("### 📁 Projet")
project = st.sidebar.selectbox(
    "Projet",
    ["137", "137est", "4101"],
    label_visibility="collapsed",
)

if page == "Suivi données agro":
    source = load_agro_data(project)
else:
    source = load_registration(project)
    if source.empty:
        source = load_distribution_joined(project)

region = st.sidebar.selectbox(
    "Région",
    ["Toutes les régions"] + sorted_options(source, "region"),
)

region_source = (
    source
    if region == "Toutes les régions" or "region" not in source.columns
    else source[source["region"].astype(str).str.strip() == region]
)

district = st.sidebar.selectbox(
    "District",
    ["Tous les districts"] + sorted_options(region_source, "district"),
)

district_source = (
    region_source
    if district == "Tous les districts"
    or "district" not in region_source.columns
    else region_source[
        region_source["district"].astype(str).str.strip() == district
    ]
)

commune = st.sidebar.selectbox(
    "Commune",
    ["Toutes les communes"] + sorted_options(district_source, "commune"),
)

if st.sidebar.button("↺ Réinitialiser les filtres"):
    st.cache_data.clear()
    st.session_state.clear()
    st.rerun()


if page == "Vue globale":
    metrics = project_kpis(project, region, district, commune)
    registration = metrics["registration"]

    st.markdown(
        f'<h2 class="crs-section-title">Vue globale — {project}</h2>',
        unsafe_allow_html=True,
    )
    st.caption(filter_caption(region, district, commune))

    if registration.empty:
        st.warning(
            "Aucune donnée bénéficiaire avec les filtres sélectionnés."
        )
        st.stop()

    sex = registration.get(
        "ben_sex",
        pd.Series(index=registration.index, dtype="object"),
    ).map(normalize_text)

    men = int(sex.isin(["male", "m", "homme", "masculin"]).sum())
    women = int(sex.isin(["female", "f", "femme", "feminin"]).sum())

    household_size = pd.to_numeric(
        registration.get("hh_size", pd.Series(dtype=float)),
        errors="coerce",
    )
    household_mean = (
        household_size.mean() if household_size.notna().any() else 0
    )

    st.markdown("##### 👥 Démographie")
    demographic_columns = st.columns(4)
    labels = [
        "Bénéficiaires uniques",
        "Hommes",
        "Femmes",
        "Taille moyenne du ménage",
    ]
    values = [
        f'{metrics["unique_beneficiaries"]:,}',
        f"{men:,}",
        f"{women:,}",
        f"{household_mean:.1f}",
    ]
    for box, label, value in zip(demographic_columns, labels, values):
        box.metric(label, value)

    st.markdown("##### 🌾 Agriculture & distribution")
    agriculture_columns = st.columns(4)
    agriculture_columns[0].metric(
        "Bénéficiaires Agriculture/Farming",
        f'{metrics["agriculture_beneficiaries"]:,}',
    )
    agriculture_columns[1].metric(
        "Présents aux distributions",
        f'{metrics["present_beneficiaries"]:,}',
    )
    agriculture_columns[2].metric(
        "Absents aux distributions",
        f'{metrics["absent_beneficiaries"]:,}',
    )
    agriculture_columns[3].metric(
        "Taux de présence",
        f'{metrics["presence_rate"]:.1f}%',
    )

    if "project_outcome" in registration.columns:
        outcome_table = (
            registration.assign(
                Catégorie=registration["project_outcome"].fillna(
                    "Non renseigné"
                )
            )
            .groupby("Catégorie")["unique_key"]
            .nunique()
            .reset_index(name="Bénéficiaires uniques")
        )
        st.dataframe(
            outcome_table,
            use_container_width=True,
            hide_index=True,
        )
        st.plotly_chart(
            px.bar(
                outcome_table,
                x="Catégorie",
                y="Bénéficiaires uniques",
                color="Catégorie",
                text="Bénéficiaires uniques",
            ),
            use_container_width=True,
        )

elif page == "Suivi des distributions":
    distribution = apply_location_filters(
        load_distribution_joined(project),
        region,
        district,
        commune,
    )

    st.markdown(
        f'<h2 class="crs-section-title">Suivi des distributions — {project}</h2>',
        unsafe_allow_html=True,
    )
    st.caption(filter_caption(region, district, commune))

    if distribution.empty:
        st.info("Aucune donnée de distribution.")
        st.stop()

    distribution_kpis = project_kpis(
        project,
        region,
        district,
        commune,
    )

    distribution_columns = st.columns(3)
    distribution_columns[0].metric(
        "Bénéficiaires Farming",
        f'{distribution_kpis["agriculture_beneficiaries"]:,}',
    )
    distribution_columns[1].metric(
        "Présents aux distributions",
        f'{distribution_kpis["present_beneficiaries"]:,}',
    )
    distribution_columns[2].metric(
        "Absents aux distributions",
        f'{distribution_kpis["absent_beneficiaries"]:,}',
    )

    available = [
        name
        for name, config in VOLET_CONFIG.items()
        if config["date_col"] in distribution.columns
        and distribution[config["date_col"]].notna().any()
    ]

    if not available:
        st.info("Aucun volet de distribution ne contient de données.")
        st.stop()

    volet_name = st.selectbox("Type de distribution", available)
    volet_metrics = compute_volet_metrics(distribution, volet_name)

    if volet_metrics is None:
        st.info("Aucune donnée pour le volet sélectionné.")
        st.stop()

    volet_detail = volet_metrics["detail_df"]
    if "present" in volet_detail.columns:
        volet_present_mask = volet_detail["present"].map(
            normalize_text
        ).isin(PRESENT_VALUES)
        volet_present_beneficiaries = int(
            volet_detail.loc[
                volet_present_mask,
                "unique_key",
            ].nunique(dropna=True)
        )
    else:
        volet_present_beneficiaries = 0

    volet_absent_beneficiaries = max(
        0,
        distribution_kpis["agriculture_beneficiaries"]
        - volet_present_beneficiaries,
    )

    volet_columns = st.columns(2)
    volet_columns[0].metric(
        "Bénéficiaires présents selon l'article distribué",
        f"{volet_present_beneficiaries:,}",
    )
    volet_columns[1].metric(
        "Bénéficiaires absents",
        f"{volet_absent_beneficiaries:,}",
    )

    if not volet_metrics["qty_summary"].empty:
        st.dataframe(
            volet_metrics["qty_summary"],
            use_container_width=True,
            hide_index=True,
        )
        st.plotly_chart(
            px.bar(
                volet_metrics["qty_summary"],
                x="Quantité",
                y="Total distribué",
                text="Total distribué",
            ),
            use_container_width=True,
        )

    detail_columns = [
        col
        for col in [
            "submission_uuid",
            "seq_num",
            "sequence_number",
            "present",
            "village",
            "full_name",
            "beneficiary_code",
            "sex",
            "age",
            "cin",
            "agri_date",
            "agri_input_type",
            "mais_weight_kg",
            "rice_weight_kg",
            "groundnut_weight_kg",
            "swpotato_qty",
            "cuma_type",
            "cuma_weight_kg",
        ]
        if col in volet_detail.columns
    ]

    st.subheader("Détail des bénéficiaires")
    st.dataframe(
        volet_detail[detail_columns],
        use_container_width=True,
        hide_index=True,
    )

elif page == "Suivi données agro":
    st.markdown(
        f'<h2 class="crs-section-title">Suivi données agro — {project}</h2>',
        unsafe_allow_html=True,
    )
    st.caption(filter_caption(region, district, commune))

    if project in {"137", "4101"}:
        st.info("Pas de données disponibles pour le moment.")
        st.stop()

    agro_df = apply_location_filters(
        load_agro_data(project),
        region,
        district,
        commune,
    )

    if agro_df.empty:
        st.info("Pas de données disponibles pour le moment.")
        st.stop()

    # Harmonisation des noms de spéculation avant les agrégations.
    if "speculation" in agro_df.columns:
        agro_df["speculation"] = (
            agro_df["speculation"]
            .astype("string")
            .str.strip()
        )
        agro_df.loc[
            agro_df["speculation"].str.upper().eq("RIZ X266").fillna(False),
            "speculation",
        ] = "Riz X265"

    numeric_agro_columns = [
        "quantite_semences_kg",
        "superficie_prevue_are",
        "superficie_emblavee_are",
        "superficie_emblavee_ha",
        "production_estimee_kg",
    ]
    for column in numeric_agro_columns:
        if column in agro_df.columns:
            agro_df[column] = pd.to_numeric(
                agro_df[column],
                errors="coerce",
            )

    household_count = (
        int(agro_df["nom_code_menage"].dropna().astype(str).str.strip().nunique())
        if "nom_code_menage" in agro_df.columns
        else len(agro_df)
    )
    speculation_count = (
        int(agro_df["speculation"].dropna().astype(str).str.strip().nunique())
        if "speculation" in agro_df.columns
        else 0
    )
    estimated_production = (
        agro_df["production_estimee_kg"].fillna(0).sum()
        if "production_estimee_kg" in agro_df.columns
        else 0
    )
    planted_area_ha = (
        agro_df["superficie_emblavee_ha"].fillna(0).sum()
        if "superficie_emblavee_ha" in agro_df.columns
        else 0
    )

    agro_kpi_columns = st.columns(4)
    agro_kpi_columns[0].metric("Ménages suivis", f"{household_count:,}")
    agro_kpi_columns[1].metric("Spéculations", f"{speculation_count:,}")
    agro_kpi_columns[2].metric(
        "Production estimée (kg)",
        f"{estimated_production:,.0f}",
    )
    agro_kpi_columns[3].metric(
        "Superficie emblavée (ha)",
        f"{planted_area_ha:,.2f}",
    )

    if "speculation" in agro_df.columns:
        spec_summary = (
            agro_df.groupby("speculation", dropna=False)
            .agg(
                nb_beneficiaires=("speculation", "size"),
                quantite_semences_kg=("quantite_semences_kg", "sum"),
                superficie_emblavee_ha=("superficie_emblavee_ha", "sum"),
                production_estimee_kg=("production_estimee_kg", "sum"),
            )
            .reset_index()
            .fillna(0)
        )

        st.subheader("Résumé par spéculation")
        st.dataframe(
            spec_summary.rename(columns={
                "speculation":"Spéculation",
                "nb_beneficiaires":"Bénéficiaires",
                "quantite_semences_kg":"Qté distribuée (kg)",
                "superficie_emblavee_ha":"Superficie emblavée (ha)",
                "production_estimee_kg":"Production estimée (kg)",
            }),
            use_container_width=True,
            hide_index=True,
        )

        production_chart = spec_summary.melt(
            id_vars="speculation",
            value_vars=[
                "quantite_semences_kg",
                "production_estimee_kg",
            ],
            var_name="Indicateur",
            value_name="Valeur",
        )

        production_chart["Indicateur"] = production_chart["Indicateur"].replace({
            "quantite_semences_kg": "Qté distribuée (kg)",
            "production_estimee_kg": "Production estimée (kg)",
        })

        st.subheader("Quantité distribuée vs production estimée")
        st.plotly_chart(
            px.bar(
                production_chart,
                x="speculation",
                y="Valeur",
                color="Indicateur",
                barmode="group",
                text="Valeur",
            ),
            use_container_width=True,
        )

        st.subheader("Superficie emblavée (ha)")
        st.plotly_chart(
            px.bar(
                spec_summary,
                x="speculation",
                y="superficie_emblavee_ha",
                color="speculation",
                text="superficie_emblavee_ha",
            ),
            use_container_width=True,
        )

        st.subheader("Nombre de bénéficiaires")
        st.plotly_chart(
            px.bar(
                spec_summary,
                x="speculation",
                y="nb_beneficiaires",
                color="speculation",
                text="nb_beneficiaires",
            ),
            use_container_width=True,
        )

    st.subheader("Détail des données agro")
    if "nom_code_menage" in agro_df.columns:
        agro_df = agro_df.drop(columns=["nom_code_menage"])

    st.dataframe(
        agro_df,
        use_container_width=True,
        hide_index=True,
    )

else:
    st.markdown(
        f'<h2 class="crs-section-title">Qualité des données — {project}</h2>',
        unsafe_allow_html=True,
    )

    available_tables = inspect(DATABASES[project]).get_table_names(
        schema="public"
    )
    selected_table = st.selectbox(
        "Table à contrôler",
        available_tables,
    )

    with DATABASES[project].connect() as connection:
        quality_df = pd.read_sql(
            text(
                f'SELECT * FROM public."{selected_table}" '
                f"LIMIT {MAX_ROWS}"
            ),
            connection,
        )

    quality_columns = st.columns(2)
    quality_columns[0].metric("Lignes analysées", len(quality_df))
    quality_columns[1].metric(
        "Doublons complets",
        int(quality_df.duplicated().sum()),
    )

    numeric_columns = quality_df.select_dtypes(
        include="number"
    ).columns.tolist()

    if numeric_columns:
        numeric_column = st.selectbox(
            "Variable numérique",
            numeric_columns,
        )
        st.plotly_chart(
            px.box(
                quality_df,
                y=numeric_column,
                points="outliers",
                title=f"Valeurs aberrantes : {numeric_column}",
            ),
            use_container_width=True,
        )
