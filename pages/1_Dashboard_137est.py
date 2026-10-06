# -*- coding: utf-8 -*-
"""Page Streamlit dédiée au projet 137est."""

import unicodedata

import pandas as pd
import plotly.express as px
import streamlit as st
from sqlalchemy import inspect, text

import sys
from pathlib import Path

ROOT_DIR = Path(__file__).resolve().parents[1]
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from connections import DATABASES


st.set_page_config(
    page_title="Dashboard 137est",
    page_icon="📊",
    layout="wide",
    initial_sidebar_state="expanded",
)

PROJECT = "137est"
SCHEMA = "public"
MAX_ROWS = 50_000
PRESENT_VALUES = {"yes", "true", "t", "1", "oui", "o"}
AGRI_CATEGORIES = {"farming"}

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

VOLET_CONFIG = {
    "Semences / intrants agricoles": {
        "date_col": "agri_date",
        "type_col": "agri_input_type",
        "qty_cols": [
            ("mais_weight_kg", "kg de maïs"),
            ("rice_weight_kg", "kg de riz"),
            ("groundnut_weight_kg", "kg d'arachide"),
            ("cassava_qty", "tiges de manioc"),
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
        "qty_cols": [("arrosoir_nb", "arrosoirs"), ("beche_nb", "bêches")],
    },
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
        border-radius: 8px;
        padding: .75rem 1rem;
        box-shadow: 0 1px 3px rgba(0,0,0,.06);
    }}
    div[data-testid="stMetricValue"] {{color: {CRS_COLORS['crs_blue']};}}
    .crs-banner {{
        background: {CRS_COLORS['crs_blue']};
        padding: 1.1rem 1.5rem;
        border-radius: 10px;
        margin-bottom: 1.2rem;
        color: white;
    }}
    .crs-banner h1 {{margin: 0; font-size: 1.7rem;}}
    .crs-banner p {{color: #CCE4F5; margin: .2rem 0 0;}}
    .crs-section-title {{
        color: {CRS_COLORS['crs_blue']};
        border-bottom: 3px solid {CRS_COLORS['bold_orange']};
        display: inline-block;
    }}
    </style>
    <div class="crs-banner">
        <h1>📊 Dashboard 137est</h1>
        <p>Bénéficiaires, distributions et suivi des données agro</p>
    </div>
    """,
    unsafe_allow_html=True,
)


def get_engine():
    if PROJECT not in DATABASES:
        st.error('La connexion DATABASES["137est"] est absente de connections.py.')
        st.stop()
    return DATABASES[PROJECT]


def normalize_text(value):
    if pd.isna(value):
        return ""
    value = unicodedata.normalize("NFKD", str(value).strip().lower())
    return "".join(char for char in value if not unicodedata.combining(char))


def make_unique_key(df, cin_col, name_col, age_col=None):
    cin = (
        df[cin_col].fillna("").astype("string").str.strip()
        if cin_col in df.columns
        else pd.Series("", index=df.index, dtype="string")
    )
    name = (
        df[name_col].fillna("").astype("string").str.strip().str.upper()
        if name_col in df.columns
        else pd.Series("", index=df.index, dtype="string")
    )
    if age_col and age_col in df.columns:
        age = pd.to_numeric(df[age_col], errors="coerce").apply(
            lambda value: "" if pd.isna(value) else str(int(value))
        ).astype("string")
    else:
        age = pd.Series("", index=df.index, dtype="string")
    key = name.fillna("") + "|" + cin.fillna("") + "|" + age.fillna("")
    return key.mask((cin == "") & (name == "") & (age == ""))


def table_exists(table):
    return table in inspect(get_engine()).get_table_names(schema=SCHEMA)


def table_columns(table):
    if not table_exists(table):
        return []
    return [
        column["name"]
        for column in inspect(get_engine()).get_columns(table, schema=SCHEMA)
    ]


def sorted_options(df, column):
    if df.empty or column not in df.columns:
        return []
    values = df[column].dropna().astype(str).str.strip()
    return sorted(values[values != ""].unique().tolist())


def apply_location_filters(df, region, district, commune):
    result = df.copy()
    filters = [
        ("region", region, "Toutes les régions"),
        ("district", district, "Tous les districts"),
        ("commune", commune, "Toutes les communes"),
    ]
    for column, value, default in filters:
        if value != default and column in result.columns:
            result = result[result[column].astype(str).str.strip() == value]
    return result


def filter_caption(region, district, commune):
    parts = []
    if region != "Toutes les régions":
        parts.append(f"Région : {region}")
    if district != "Tous les districts":
        parts.append(f"District : {district}")
    if commune != "Toutes les communes":
        parts.append(f"Commune : {commune}")
    return " • ".join(parts) if parts else "Aucun filtre géographique actif"


@st.cache_data(ttl=1800, show_spinner=False)
def load_registration():
    table = "beneficiary_registration"
    wanted = [
        "ben_cin", "ben_full_name", "ben_sex", "ben_age", "hh_size",
        "project_outcome", "region", "district", "commune", "fokontany",
    ]
    selected = [column for column in wanted if column in table_columns(table)]
    if not selected:
        return pd.DataFrame()
    query = "SELECT " + ",".join(f'"{column}"' for column in selected)
    query += f' FROM public."{table}"'
    with get_engine().connect() as connection:
        df = pd.read_sql(text(query), connection)
    df["unique_key"] = make_unique_key(df, "ben_cin", "ben_full_name", "ben_age")
    return df


@st.cache_data(ttl=1800, show_spinner=False)
def load_distribution_joined():
    submission_table = "distribution_submission"
    beneficiary_table = "distribution_beneficiary"
    if not (table_exists(submission_table) and table_exists(beneficiary_table)):
        return pd.DataFrame()

    submission_columns = table_columns(submission_table)
    beneficiary_columns = table_columns(beneficiary_table)
    submission_wanted = [
        "id", "kobo_uuid", "submission_time", "submitted_by", "region",
        "district", "commune", "fokontany", "project_code", "sector",
        "cuma_date", "cuma_type", "cuma_weight_kg", "agri_date",
        "agri_input_type", "mais_weight_kg", "rice_weight_kg",
        "groundnut_weight_kg", "cassava_qty", "cassava_unit",
        "swpotato_qty", "swpotato_unit", "pma_date", "pma_type",
        "arrosoir_nb", "beche_nb", "nb_beneficiaries", "distribution_date",
        "agri_input_codes", "rice_weight", "groundnut_weight",
    ]
    beneficiary_wanted = [
        "id", "parent_id", "seq_num", "present", "village", "full_name",
        "sex", "age", "cin", "ben_id_raw", "submission_uuid",
        "distribution_uuid", "repeat_index", "sequence_number",
        "beneficiary_presence", "beneficiary_id_raw", "beneficiary_location",
        "beneficiary_name", "beneficiary_code", "beneficiary_sex",
        "beneficiary_age", "beneficiary_cin", "c3_raw",
    ]
    fields = [
        'ds."id" AS "submission_id"' if column == "id" else f'ds."{column}"'
        for column in submission_wanted if column in submission_columns
    ]
    fields += [
        'db."id" AS "beneficiary_row_id"' if column == "id" else f'db."{column}"'
        for column in beneficiary_wanted if column in beneficiary_columns
    ]

    if "parent_id" in beneficiary_columns and "id" in submission_columns:
        join = 'db."parent_id"::text = ds."id"::text'
    elif "distribution_uuid" in beneficiary_columns and "kobo_uuid" in submission_columns:
        join = 'db."distribution_uuid"::text = ds."kobo_uuid"::text'
    elif "submission_uuid" in beneficiary_columns and "kobo_uuid" in submission_columns:
        join = 'db."submission_uuid"::text = ds."kobo_uuid"::text'
    else:
        return pd.DataFrame()

    query = (
        f'SELECT {",".join(fields)} FROM public."{submission_table}" ds '
        f'INNER JOIN public."{beneficiary_table}" db ON {join}'
    )
    with get_engine().connect() as connection:
        df = pd.read_sql(text(query), connection)

    aliases = {
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
    df = df.rename(columns={old: new for old, new in aliases.items() if old in df and new not in df})
    for column in ["submission_id", "parent_id", "submission_uuid", "kobo_uuid"]:
        if column in df.columns:
            df["submission_group_id"] = df[column]
            break
    if "submission_uuid" in df.columns and "seq_num" in df.columns:
        df["beneficiary_seq_key"] = df["submission_uuid"].astype(str) + "|" + df["seq_num"].astype(str)
    df["unique_key"] = make_unique_key(df, "cin", "full_name", "age")
    return df


@st.cache_data(ttl=1800, show_spinner=False)
def load_agro_data():
    if not table_exists("da"):
        return pd.DataFrame()
    with get_engine().connect() as connection:
        return pd.read_sql(
            text(f'SELECT * FROM public."da" LIMIT {MAX_ROWS}'), connection
        )


def project_kpis(region, district, commune):
    registration = apply_location_filters(load_registration(), region, district, commune)
    distribution = apply_location_filters(load_distribution_joined(), region, district, commune)
    unique = int(registration["unique_key"].nunique(dropna=True)) if not registration.empty else 0
    farming = (
        set(registration.loc[
            registration["project_outcome"].map(normalize_text).isin(AGRI_CATEGORIES),
            "unique_key",
        ].dropna())
        if "project_outcome" in registration.columns else set()
    )
    present = (
        int(distribution.loc[
            distribution["present"].map(normalize_text).isin(PRESENT_VALUES),
            "unique_key",
        ].nunique(dropna=True))
        if "present" in distribution.columns else 0
    )
    return {
        "registration": registration,
        "distribution": distribution,
        "unique_beneficiaries": unique,
        "agriculture_beneficiaries": len(farming),
        "present_beneficiaries": present,
        "absent_beneficiaries": max(0, len(farming) - present),
        "presence_rate": present / len(farming) * 100 if farming else 0,
    }


def compute_volet_metrics(df, name):
    """Calcule bénéficiaires et quantités après déduplication par district/produit."""
    config = VOLET_CONFIG[name]
    date_column = config["date_col"]
    type_column = config.get("type_col")

    if date_column not in df.columns:
        return None

    volet = df[df[date_column].notna()].copy()
    if volet.empty:
        return None

    if "present" in volet.columns:
        presence = volet["present"].map(normalize_text)
        if presence.isin(PRESENT_VALUES).any():
            volet = volet[presence.isin(PRESENT_VALUES)].copy()
    if volet.empty:
        return None

    if "unique_key" not in volet.columns:
        volet["unique_key"] = make_unique_key(volet, "cin", "full_name", "age")

    beneficiary_id_candidates = [
        "unique_key", "ben_id_raw", "beneficiary_code",
        "beneficiary_row_id", "beneficiary_seq_key",
    ]
    available_ids = [column for column in beneficiary_id_candidates if column in volet.columns]
    volet["_beneficiary_id"] = pd.Series(pd.NA, index=volet.index, dtype="string")
    for column in available_ids:
        candidate = volet[column].astype("string").str.strip().replace("", pd.NA)
        volet["_beneficiary_id"] = volet["_beneficiary_id"].fillna(candidate)
    missing_id = volet["_beneficiary_id"].isna()
    volet.loc[missing_id, "_beneficiary_id"] = "ROW_" + volet.index[missing_id].astype(str)

    if "district" in volet.columns:
        volet["_district"] = (
            volet["district"].fillna("Non renseigné").astype(str).str.strip()
            .replace("", "Non renseigné")
        )
    else:
        volet["_district"] = "Tous les districts"

    product_keywords = {
        "mais_weight_kg": ["mais", "maize"],
        "rice_weight_kg": ["riz", "rice", "x265", "x266"],
        "groundnut_weight_kg": ["arachide", "groundnut", "peanut"],
        "cassava_qty": ["manioc", "cassava"],
        "swpotato_qty": ["patate douce", "sweet potato", "swpotato"],
        "cuma_weight_kg": [],
        "arrosoir_nb": ["arrosoir"],
        "beche_nb": ["beche", "bêche"],
    }
    unit_map = {
        "mais_weight_kg": "kg", "rice_weight_kg": "kg",
        "groundnut_weight_kg": "kg", "cassava_qty": "tiges",
        "swpotato_qty": "lianes", "cuma_weight_kg": "sachets",
        "arrosoir_nb": "arrosoirs", "beche_nb": "bêches",
    }

    summary_rows = []
    district_rows = []
    debug_rows = []
    deduplicated_details = []

    for quantity_column, label in config["qty_cols"]:
        if quantity_column not in volet.columns:
            debug_rows.append({
                "Quantité": label, "Colonne": quantity_column, "Présente": False,
                "Lignes avant déduplication": 0, "Lignes après déduplication": 0,
                "Doublons supprimés": 0, "Bénéficiaires uniques": 0,
                "Total calculé": 0,
            })
            continue

        product = volet.copy()
        product["_quantity"] = pd.to_numeric(product[quantity_column], errors="coerce")
        product = product[product["_quantity"].notna() & product["_quantity"].gt(0)].copy()

        keywords = product_keywords.get(quantity_column, [])
        if keywords and type_column and type_column in product.columns:
            normalized_type = product[type_column].fillna("").map(normalize_text)
            type_mask = pd.Series(False, index=product.index)
            for keyword in keywords:
                type_mask = type_mask | normalized_type.str.contains(
                    normalize_text(keyword), case=False, regex=False, na=False
                )
            if type_mask.any():
                product = product[type_mask].copy()

        rows_before = len(product)
        if product.empty:
            debug_rows.append({
                "Quantité": label, "Colonne": quantity_column, "Présente": True,
                "Lignes avant déduplication": rows_before,
                "Lignes après déduplication": 0, "Doublons supprimés": 0,
                "Bénéficiaires uniques": 0, "Total calculé": 0,
            })
            continue

        sort_columns = [
            column for column in [
                date_column, "submission_time", "submission_id", "beneficiary_row_id"
            ] if column in product.columns
        ]
        if sort_columns:
            product = product.sort_values(sort_columns, na_position="last")

        deduplicated = product.drop_duplicates(
            subset=["_district", "_beneficiary_id"], keep="first"
        ).copy()
        rows_after = len(deduplicated)
        beneficiaries = int(deduplicated["_beneficiary_id"].nunique())
        total_quantity = float(deduplicated["_quantity"].sum())

        summary_rows.append({
            "Quantité": label,
            "Nombre bénéficiaires": beneficiaries,
            "Total distribué": round(total_quantity, 2),
            "Unité": unit_map.get(quantity_column, "unités"),
        })

        district_summary = (
            deduplicated.groupby("_district", dropna=False)
            .agg(
                beneficiaries=("_beneficiary_id", "nunique"),
                total_quantity=("_quantity", "sum"),
            )
            .reset_index()
        )
        for _, district_row in district_summary.iterrows():
            district_rows.append({
                "District": district_row["_district"],
                "Quantité": label,
                "Nombre bénéficiaires": int(district_row["beneficiaries"]),
                "Total distribué": round(float(district_row["total_quantity"]), 2),
                "Unité": unit_map.get(quantity_column, "unités"),
            })

        debug_rows.append({
            "Quantité": label,
            "Colonne": quantity_column,
            "Présente": True,
            "Lignes avant déduplication": rows_before,
            "Lignes après déduplication": rows_after,
            "Doublons supprimés": rows_before - rows_after,
            "Bénéficiaires uniques": beneficiaries,
            "Total calculé": round(total_quantity, 2),
        })

        detail_copy = deduplicated.copy()
        detail_copy["_produit"] = label
        detail_copy["_unite"] = unit_map.get(quantity_column, "unités")
        deduplicated_details.append(detail_copy)

    return {
        "qty_summary": pd.DataFrame(summary_rows),
        "district_summary": pd.DataFrame(district_rows),
        "detail_df": (
            pd.concat(deduplicated_details, ignore_index=True)
            if deduplicated_details else volet.iloc[0:0].copy()
        ),
        "debug": pd.DataFrame(debug_rows),
    }


# Navigation
st.sidebar.markdown("### 🧭 Navigation")
page = st.sidebar.radio(
    "Choisir une page",
    ["Vue globale", "Suivi des distributions", "Suivi données agro", "Qualité des données"],
    label_visibility="collapsed",
)
st.sidebar.divider()
st.sidebar.markdown("### 📁 Projet")
st.sidebar.info("137est")

source = load_agro_data() if page == "Suivi données agro" else load_registration()
if source.empty and page != "Suivi données agro":
    source = load_distribution_joined()

region = st.sidebar.selectbox("Région", ["Toutes les régions"] + sorted_options(source, "region"))
region_source = source if region == "Toutes les régions" or "region" not in source.columns else source[source["region"].astype(str).str.strip() == region]
district = st.sidebar.selectbox("District", ["Tous les districts"] + sorted_options(region_source, "district"))
district_source = region_source if district == "Tous les districts" or "district" not in region_source.columns else region_source[region_source["district"].astype(str).str.strip() == district]
commune = st.sidebar.selectbox("Commune", ["Toutes les communes"] + sorted_options(district_source, "commune"))

if st.sidebar.button("↺ Réinitialiser les filtres", use_container_width=True):
    st.cache_data.clear()
    st.session_state.clear()
    st.rerun()


if page == "Vue globale":
    metrics = project_kpis(region, district, commune)
    registration = metrics["registration"]
    st.markdown('<h2 class="crs-section-title">Vue globale — 137est</h2>', unsafe_allow_html=True)
    st.caption(filter_caption(region, district, commune))
    if registration.empty:
        st.warning("Aucune donnée bénéficiaire avec les filtres sélectionnés.")
        st.stop()

    sex = registration.get("ben_sex", pd.Series(index=registration.index, dtype="object")).map(normalize_text)
    men = int(sex.isin(["male", "m", "homme", "masculin"]).sum())
    women = int(sex.isin(["female", "f", "femme", "feminin"]).sum())
    household_size = pd.to_numeric(registration.get("hh_size", pd.Series(dtype=float)), errors="coerce")

    labels = ["Bénéficiaires uniques", "Hommes", "Femmes", "Taille moyenne du ménage"]
    values = [metrics["unique_beneficiaries"], men, women, household_size.mean() if household_size.notna().any() else 0]
    for box, label, value in zip(st.columns(4), labels, values):
        box.metric(label, f"{value:,.1f}" if label.startswith("Taille") else f"{value:,}")

    labels = ["Bénéficiaires Agriculture/Farming", "Présents aux distributions", "Absents aux distributions", "Taux de présence"]
    keys = ["agriculture_beneficiaries", "present_beneficiaries", "absent_beneficiaries", "presence_rate"]
    for box, label, key in zip(st.columns(4), labels, keys):
        box.metric(label, f'{metrics[key]:.1f}%' if key == "presence_rate" else f'{metrics[key]:,}')

    if "project_outcome" in registration.columns:
        outcome = registration.assign(
            Catégorie=registration["project_outcome"].fillna("Non renseigné")
        ).groupby("Catégorie")["unique_key"].nunique().reset_index(name="Bénéficiaires uniques")
        st.dataframe(outcome, use_container_width=True, hide_index=True)
        st.plotly_chart(
            px.bar(outcome, x="Catégorie", y="Bénéficiaires uniques", color="Catégorie", text="Bénéficiaires uniques"),
            use_container_width=True,
        )

elif page == "Suivi des distributions":
    distribution = apply_location_filters(load_distribution_joined(), region, district, commune)
    st.markdown('<h2 class="crs-section-title">Suivi des distributions — 137est</h2>', unsafe_allow_html=True)
    st.caption(filter_caption(region, district, commune))
    if distribution.empty:
        st.info("Aucune donnée de distribution.")
        st.stop()

    available = [
        name for name, config in VOLET_CONFIG.items()
        if config["date_col"] in distribution.columns
        and distribution[config["date_col"]].notna().any()
    ]
    if not available:
        st.info("Aucun volet de distribution ne contient de données.")
        st.stop()

    selected_type = st.selectbox("Type de distribution", available)
    volet_metrics = compute_volet_metrics(distribution, selected_type)
    if volet_metrics is None:
        st.info("Aucune donnée exploitable pour ce type de distribution.")
        st.stop()

    detail = volet_metrics["detail_df"]
    qty_summary = volet_metrics["qty_summary"]
    district_summary = volet_metrics["district_summary"]

    st.subheader("Résumé général sans doublons")
    if qty_summary.empty:
        st.info("Aucune quantité positive disponible pour ce volet.")
    else:
        st.dataframe(qty_summary, use_container_width=True, hide_index=True)
        st.plotly_chart(
            px.bar(
                qty_summary,
                x="Quantité",
                y="Total distribué",
                color="Quantité",
                text="Total distribué",
                hover_data=["Nombre bénéficiaires", "Unité"],
                title="Quantités distribuées après déduplication des bénéficiaires",
            ),
            use_container_width=True,
        )

    st.subheader("Résumé par district sans doublons")
    if district_summary.empty:
        st.info("Aucun résumé par district disponible.")
    else:
        district_summary = district_summary.sort_values(["District", "Quantité"])
        st.dataframe(district_summary, use_container_width=True, hide_index=True)
        st.plotly_chart(
            px.bar(
                district_summary,
                x="District",
                y="Nombre bénéficiaires",
                color="Quantité",
                barmode="group",
                text="Nombre bénéficiaires",
                hover_data=["Total distribué", "Unité"],
                title="Bénéficiaires uniques par district et par produit",
            ),
            use_container_width=True,
        )
        st.plotly_chart(
            px.bar(
                district_summary,
                x="District",
                y="Total distribué",
                color="Quantité",
                barmode="group",
                text="Total distribué",
                hover_data=["Nombre bénéficiaires", "Unité"],
                title="Quantités distribuées par district après déduplication",
            ),
            use_container_width=True,
        )

    with st.expander("🔍 Diagnostic du calcul"):
        st.dataframe(volet_metrics["debug"], use_container_width=True, hide_index=True)

    detail_columns = [column for column in [
        "_district", "_produit", "_quantity", "_unite", "_beneficiary_id",
        "submission_id", "parent_id", "submission_uuid", "beneficiary_row_id",
        "seq_num", "sequence_number", "present", "village", "full_name",
        "beneficiary_code", "sex", "age", "cin", "agri_date",
        "agri_input_type", "mais_weight_kg", "rice_weight_kg",
        "groundnut_weight_kg", "cassava_qty", "cassava_unit",
        "swpotato_qty", "swpotato_unit", "cuma_type", "cuma_weight_kg",
        "pma_type", "arrosoir_nb", "beche_nb",
    ] if column in detail.columns]
    st.subheader("Détail des bénéficiaires sans doublons")
    st.dataframe(detail[detail_columns], use_container_width=True, hide_index=True)

elif page == "Suivi données agro":
    st.markdown('<h2 class="crs-section-title">Suivi données agro — 137est</h2>', unsafe_allow_html=True)
    st.caption(filter_caption(region, district, commune))
    agro = apply_location_filters(load_agro_data(), region, district, commune)
    if agro.empty:
        st.info("Pas de données disponibles dans public.da.")
        st.stop()

    if "speculation" in agro.columns:
        agro["speculation"] = agro["speculation"].astype("string").str.strip()
        mask = agro["speculation"].str.upper().eq("RIZ X266").fillna(False)
        agro.loc[mask, "speculation"] = "Riz X265"

    numeric_columns = [
        "quantite_semences_kg", "superficie_prevue_are",
        "superficie_emblavee_are", "superficie_emblavee_ha",
        "production_estimee_kg",
    ]
    for column in numeric_columns:
        if column in agro.columns:
            agro[column] = pd.to_numeric(agro[column], errors="coerce")

    household_count = (
        int(agro["nom_code_menage"].dropna().astype(str).str.strip().nunique())
        if "nom_code_menage" in agro.columns else len(agro)
    )
    speculation_count = (
        int(agro["speculation"].dropna().astype(str).str.strip().nunique())
        if "speculation" in agro.columns else 0
    )
    production = agro["production_estimee_kg"].fillna(0).sum() if "production_estimee_kg" in agro.columns else 0
    area = agro["superficie_emblavee_ha"].fillna(0).sum() if "superficie_emblavee_ha" in agro.columns else 0

    labels = ["Ménages suivis", "Spéculations", "Production estimée (kg)", "Superficie emblavée (ha)"]
    values = [household_count, speculation_count, production, area]
    formats = [",", ",", ",.0f", ",.2f"]
    for box, label, value, number_format in zip(st.columns(4), labels, values, formats):
        box.metric(label, format(value, number_format))

    if "speculation" in agro.columns:
        aggregations = {"nb_beneficiaires": ("speculation", "size")}
        for column in ["quantite_semences_kg", "superficie_emblavee_ha", "production_estimee_kg"]:
            if column in agro.columns:
                aggregations[column] = (column, "sum")
        summary = agro.groupby("speculation", dropna=False).agg(**aggregations).reset_index().fillna(0)
        for column in ["quantite_semences_kg", "superficie_emblavee_ha", "production_estimee_kg"]:
            if column not in summary.columns:
                summary[column] = 0
        summary["unite_qte"] = summary["speculation"].astype(str).str.lower().str.contains(
            "manioc|cassava", na=False
        ).map({True: "tiges", False: "kg"})

        display_summary = summary.rename(columns={
            "speculation": "Spéculation",
            "nb_beneficiaires": "Bénéficiaires",
            "quantite_semences_kg": "Qté distribuée",
            "unite_qte": "Unité qté distribuée",
            "superficie_emblavee_ha": "Superficie emblavée (ha)",
            "production_estimee_kg": "Production estimée (kg)",
        })
        st.subheader("Résumé par spéculation")
        st.dataframe(
            display_summary[[
                "Spéculation", "Bénéficiaires", "Qté distribuée",
                "Unité qté distribuée", "Production estimée (kg)",
                "Superficie emblavée (ha)",
            ]],
            use_container_width=True,
            hide_index=True,
        )

        comparison = summary.melt(
            id_vars="speculation",
            value_vars=["quantite_semences_kg", "production_estimee_kg"],
            var_name="Indicateur",
            value_name="Valeur",
        )
        comparison["Indicateur"] = comparison["Indicateur"].replace({
            "quantite_semences_kg": "Qté distribuée",
            "production_estimee_kg": "Production estimée (kg)",
        })
        st.subheader("Quantité distribuée et production estimée")
        st.plotly_chart(
            px.bar(comparison, x="speculation", y="Valeur", color="Indicateur", barmode="group", text="Valeur"),
            use_container_width=True,
        )
        st.caption("La quantité distribuée est en tiges pour le manioc et en kg pour les autres cultures. La production estimée est en kg.")

        left, right = st.columns(2)
        left.plotly_chart(
            px.bar(summary, x="speculation", y="superficie_emblavee_ha", color="speculation", text="superficie_emblavee_ha", title="Superficie emblavée (ha)"),
            use_container_width=True,
        )
        right.plotly_chart(
            px.bar(summary, x="speculation", y="nb_beneficiaires", color="speculation", text="nb_beneficiaires", title="Nombre de bénéficiaires"),
            use_container_width=True,
        )

    st.subheader("Détail des données agro")
    public_agro = agro.drop(columns=["nom_code_menage"], errors="ignore")
    st.dataframe(public_agro, use_container_width=True, hide_index=True)
    st.download_button(
        "Télécharger les données agro filtrées",
        public_agro.to_csv(index=False).encode("utf-8-sig"),
        "137est_donnees_agro_filtrees.csv",
        "text/csv",
    )

else:
    st.markdown('<h2 class="crs-section-title">Qualité des données — 137est</h2>', unsafe_allow_html=True)
    available_tables = inspect(get_engine()).get_table_names(schema=SCHEMA)
    if not available_tables:
        st.info("Aucune table disponible dans le schéma public.")
        st.stop()
    selected_table = st.selectbox("Table à contrôler", available_tables)
    with get_engine().connect() as connection:
        quality = pd.read_sql(
            text(f'SELECT * FROM public."{selected_table}" LIMIT {MAX_ROWS}'),
            connection,
        )
    first_box, second_box, third_box = st.columns(3)
    first_box.metric("Lignes analysées", len(quality))
    second_box.metric("Colonnes", len(quality.columns))
    third_box.metric("Doublons complets", int(quality.duplicated().sum()))

    missing = pd.DataFrame({
        "Colonne": quality.columns,
        "Valeurs manquantes": quality.isna().sum().values,
        "% manquant": quality.isna().mean().mul(100).round(1).values,
        "Valeurs distinctes": quality.nunique(dropna=True).values,
    }).sort_values("% manquant", ascending=False)
    st.dataframe(missing, use_container_width=True, hide_index=True)

    numeric = quality.select_dtypes(include="number").columns.tolist()
    if numeric:
        selected_numeric = st.selectbox("Variable numérique", numeric)
        st.plotly_chart(
            px.box(quality, y=selected_numeric, points="outliers", title=f"Valeurs aberrantes : {selected_numeric}"),
            use_container_width=True,
        )

st.caption("Dashboard 137est | Les résultats reflètent les filtres géographiques actifs.")