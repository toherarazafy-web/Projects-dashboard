import unicodedata
import pandas as pd
import plotly.express as px
import streamlit as st
from sqlalchemy import inspect, text
from connections import DATABASES

st.set_page_config(
    page_title="Dashboard Projet 137",
    page_icon="📊",
    layout="wide",
    initial_sidebar_state="expanded",
)

PROJECT = "137"
AGRO_TABLE = "da_137"
MAX_ROWS = 100_000

DISTRIBUTION_TABLE = "distribution_137"
DISTRIBUTION_QUANTITIES = {
    "Semences agricoles": [
        ("riz_x265_kg", "Riz X265", "kg"),
        ("arachide_kg", "Arachide", "kg"),
    ],
    "Semences maraîchères": [
        ("brede_mafana_sachet", "Brède mafana", "sachets"),
        ("concombre_sachet", "Concombre", "sachets"),
        ("courgette_sachet", "Courgette", "sachets"),
        ("petsai_sachet", "Petsai", "sachets"),
        ("tomate_sachet", "Tomate", "sachets"),
    ],
    "Petit matériel agricole": [
        ("arrosoire_piece", "Arrosoir", "pièces"),
        ("beche_piece", "Bêche", "pièces"),
        ("pulverisateur_piece", "Pulvérisateur", "pièces"),
        ("livret_recu", "Livret reçu", "unités"),
    ],
}
VOLET_CONFIG = {
    "Semences / intrants agricoles": {"date_col": "agri_date", "type_col": "agri_input_type", "qty_cols": [("mais_weight_kg", "kg de maïs"), ("rice_weight_kg", "kg de riz"), ("groundnut_weight_kg", "kg d'arachide"), ("cassava_qty", "tiges de manioc"), ("swpotato_qty", "lianes de patate douce")]},
    "CUMA (cultures maraîchères)": {"date_col": "cuma_date", "type_col": "cuma_type", "qty_cols": [("cuma_weight_kg", "sachets")]},
    "Kit PMA (petit matériel)": {"date_col": "pma_date", "type_col": "pma_type", "qty_cols": [("arrosoir_nb", "arrosoirs"), ("beche_nb", "bêches")]},
}

CRS_COLORS = {
    "bold_blue": "#00A2C7", "crs_blue": "#00468B",
    "bold_purple": "#9053A1", "bold_teal": "#0099A9",
    "bold_green": "#79A02C", "bold_orange": "#EF6E0B",
    "humble_gray": "#9D9385", "humble_blue": "#7A99AC",
    "humble_green": "#9B9455", "humble_gold": "#B48F4B",
}
px.defaults.color_discrete_sequence = list(CRS_COLORS.values())
px.defaults.template = "plotly_white"

st.markdown(
    f"""
    <style>
    section[data-testid="stSidebar"] {{background:#F4F8FA;border-right:3px solid {CRS_COLORS['crs_blue']};}}
    div[data-testid="stMetric"] {{background:#FFF;border:1px solid #E4EBEE;border-left:5px solid {CRS_COLORS['bold_blue']};border-radius:8px;padding:.75rem 1rem;box-shadow:0 1px 3px rgba(0,0,0,.06);}}
    div[data-testid="stMetricValue"] {{color:{CRS_COLORS['crs_blue']};}}
    .crs-banner {{background:{CRS_COLORS['crs_blue']};padding:1.1rem 1.5rem;border-radius:10px;margin-bottom:1.2rem;color:white;}}
    .crs-banner h1 {{margin:0;font-size:1.7rem;}}
    .crs-banner p {{color:#CCE4F5;margin:.2rem 0 0;}}
    .crs-section-title {{color:{CRS_COLORS['crs_blue']};border-bottom:3px solid {CRS_COLORS['bold_orange']};display:inline-block;}}
    </style>
    <div class="crs-banner"><h1>📊 Dashboard Projet 137</h1>
    <p>Bénéficiaires, distributions et suivi de production agricole</p></div>
    """,
    unsafe_allow_html=True,
)


def normalize_text(value):
    if pd.isna(value):
        return ""
    value = unicodedata.normalize("NFKD", str(value).strip().lower())
    return "".join(c for c in value if not unicodedata.combining(c))


def table_exists(table_name):
    return table_name in inspect(DATABASES[PROJECT]).get_table_names(schema="public")


def table_columns(table_name):
    if not table_exists(table_name):
        return []
    return [c["name"] for c in inspect(DATABASES[PROJECT]).get_columns(table_name, schema="public")]


def read_table(table_name, selected=None):
    if not table_exists(table_name):
        return pd.DataFrame()
    available = table_columns(table_name)
    selected = [c for c in (selected or available) if c in available]
    if not selected:
        return pd.DataFrame()
    sql = "SELECT " + ", ".join(f'"{c}"' for c in selected)
    sql += f' FROM public."{table_name}" LIMIT {MAX_ROWS}'
    with DATABASES[PROJECT].connect() as con:
        return pd.read_sql(text(sql), con)


def first_existing(df, names):
    return next((c for c in names if c in df.columns), None)


def household_key(df):
    if df.empty:
        return pd.Series(dtype="string")
    col = first_existing(df, ["nom_code_menage_pms", "nom_code_menage", "code_benef", "ben_cin", "ben_full_name"])
    if not col:
        return pd.Series(pd.NA, index=df.index, dtype="string")
    key = df[col].fillna("").astype("string").str.strip()
    return key.mask(key.eq(""))


def sorted_options(df, col):
    if df.empty or col not in df.columns:
        return []
    values = df[col].dropna().astype(str).str.strip()
    return sorted(values[values.ne("")].unique().tolist())


def apply_filters(df, region, district, commune, fokontany):
    filters = [
        ("region", region, "Toutes les régions"),
        ("district", district, "Tous les districts"),
        ("commune", commune, "Toutes les communes"),
        ("fokontany", fokontany, "Tous les fokontany"),
    ]
    out = df.copy()
    for col, value, default in filters:
        if value != default and col in out.columns:
            out = out[out[col].fillna("").astype(str).str.strip().eq(value)]
    return out


def filter_caption(region, district, commune, fokontany):
    values = []
    if region != "Toutes les régions": values.append(f"Région : {region}")
    if district != "Tous les districts": values.append(f"District : {district}")
    if commune != "Toutes les communes": values.append(f"Commune : {commune}")
    if fokontany != "Tous les fokontany": values.append(f"Fokontany : {fokontany}")
    return " • ".join(values) if values else "Aucun filtre géographique actif"


def numeric_sum(df, col):
    if df.empty or not col or col not in df.columns:
        return 0.0
    return float(pd.to_numeric(df[col], errors="coerce").fillna(0).sum())


@st.cache_data(ttl=1800)
def load_beneficiaries():
    wanted = ["ben_cin", "ben_full_name", "ben_sex", "ben_age", "hh_size", "project_outcome", "region", "district", "commune", "fokontany"]
    df = read_table("beneficiary_registration", wanted)
    if not df.empty:
        cin = df.get("ben_cin", pd.Series("", index=df.index)).fillna("").astype("string").str.strip()
        name = df.get("ben_full_name", pd.Series("", index=df.index)).fillna("").astype("string").str.strip().str.upper()
        age = pd.to_numeric(df.get("ben_age", pd.Series(index=df.index, dtype=float)), errors="coerce").apply(
            lambda value: "" if pd.isna(value) else str(int(value))
        ).astype("string")
        df["beneficiary_key"] = (name + "|" + cin + "|" + age).mask(
            name.eq("") & cin.eq("") & age.eq("")
        )
    return df


@st.cache_data(ttl=1800)
def load_distribution(table_name):
    df = read_table(table_name)
    if df.empty:
        return df
    quantity = first_existing(df, ["quantite_distribuee", "quantite", "quantity"])
    date_col = first_existing(df, ["date_distribution", "distribution_date"])
    if quantity:
        df[quantity] = pd.to_numeric(df[quantity], errors="coerce")
    if date_col:
        df[date_col] = pd.to_datetime(df[date_col], errors="coerce")
    df["beneficiary_key"] = household_key(df)
    return df



@st.cache_data(ttl=1800)
def load_distribution_joined():
    """Charge directement public.distribution_137."""
    df = read_table(DISTRIBUTION_TABLE)
    if df.empty:
        return df

    numeric_cols = [
        col
        for volet in DISTRIBUTION_QUANTITIES.values()
        for col, _, _ in volet
    ]
    numeric_cols.append("age")
    for col in numeric_cols:
        if col in df.columns:
            df[col] = pd.to_numeric(df[col], errors="coerce")

    cin = df.get("cin", pd.Series("", index=df.index)).fillna("").astype("string").str.strip()
    code = df.get("code_beneficiaire", pd.Series("", index=df.index)).fillna("").astype("string").str.strip()
    name = df.get("nom_complet", pd.Series("", index=df.index)).fillna("").astype("string").str.strip().str.upper()
    age = pd.to_numeric(
        df.get("age", pd.Series(index=df.index, dtype=float)), errors="coerce"
    ).apply(lambda value: "" if pd.isna(value) else str(int(value))).astype("string")

    # Priorité au code bénéficiaire, puis concaténation nom/CIN/âge.
    fallback = name + "|" + cin + "|" + age
    df["unique_key"] = code.mask(code.eq(""), fallback)
    df["unique_key"] = df["unique_key"].mask(
        code.eq("") & name.eq("") & cin.eq("") & age.eq("")
    )
    return df


def diagnose_distribution():
    info = {"table_exists": table_exists(DISTRIBUTION_TABLE)}
    if not info["table_exists"]:
        return info
    info["columns"] = table_columns(DISTRIBUTION_TABLE)
    with DATABASES[PROJECT].connect() as con:
        info["rows"] = con.execute(
            text(f'SELECT COUNT(*) FROM public."{DISTRIBUTION_TABLE}"')
        ).scalar()
    return info


def compute_volet_metrics(df, name):
    quantity_config = DISTRIBUTION_QUANTITIES[name]
    rows = []
    debug_rows = []

    for quantity_col, label, unit in quantity_config:
        if quantity_col not in df.columns:
            debug_rows.append(
                {"Quantité": label, "Colonne": quantity_col, "Présente": False}
            )
            continue

        parsed = pd.to_numeric(df[quantity_col], errors="coerce")
        positive = df.assign(_quantity=parsed)
        positive = positive[positive["_quantity"].gt(0)]
        beneficiaries = int(positive["unique_key"].nunique(dropna=True))
        total = float(positive["_quantity"].sum())

        debug_rows.append(
            {
                "Quantité": label,
                "Colonne": quantity_col,
                "Présente": True,
                "Lignes analysées": len(df),
                "Valeurs non nulles": int(df[quantity_col].notna().sum()),
                "Valeurs numériques": int(parsed.notna().sum()),
                "Valeurs > 0": len(positive),
                "Bénéficiaires uniques": beneficiaries,
                "Total calculé": total,
            }
        )
        if not positive.empty:
            rows.append(
                {
                    "Quantité": label,
                    "Nombre bénéficiaires": beneficiaries,
                    "Total distribué": round(total, 2),
                    "Unité": unit,
                }
            )

    return {
        "qty_summary": pd.DataFrame(rows),
        "detail_df": df.copy(),
        "debug": pd.DataFrame(debug_rows),
    }


@st.cache_data(ttl=1800)
def load_agro():
    df = read_table(AGRO_TABLE)
    if df.empty:
        return df
    numeric_candidates = [
        "quantite_semences_kg", "superficie_prevue_are", "superficie_emblavee_are",
        "superficie_emblavee_ha", "production_estimee", "production_estimee_kg",
        "production_reelle_kg", "rendement_t_ha", "quantite_stockee_kg", "consomme",
        "semence", "vente_consomme_pct", "consomme_pct", "vente_semence_pct", "semence_pct",
    ]
    for col in numeric_candidates:
        if col in df.columns:
            df[col] = pd.to_numeric(df[col], errors="coerce")
    for col in ["date_suivi", "date_semis", "date_recolte"]:
        if col in df.columns:
            df[col] = pd.to_datetime(df[col], errors="coerce", dayfirst=True)
    if "categorie_semence" in df.columns:
        df["categorie_semence"] = (
            df["categorie_semence"].astype("string").str.strip()
        )
    df["beneficiary_key"] = household_key(df)
    return df


beneficiaries = load_beneficiaries()
distribution = load_distribution_joined()
household_dist = load_distribution("distribution")
group_dist = load_distribution("distribution_groupement")
agro = load_agro()
production = agro

# Les listes géographiques viennent prioritairement de distribution_137.
# Ainsi, les districts présents dans la distribution, notamment Marovoay,
# restent disponibles même s'ils sont absents des autres tables.
source = (
    distribution
    if not distribution.empty and "region" in distribution.columns
    else next(
        (
            df
            for df in [beneficiaries, production]
            if not df.empty and "region" in df.columns
        ),
        pd.DataFrame(),
    )
)

st.sidebar.markdown("### 🧭 Projet 137")
page = st.sidebar.radio(
    "Navigation",
    ["Vue globale", "Suivi des distributions", "Suivi de production", "Qualité des données"],
    label_visibility="collapsed",
)
st.sidebar.divider()
st.sidebar.markdown("### 🌍 Filtres géographiques")
st.sidebar.caption("Districts et localités issus de distribution_137")
region = st.sidebar.selectbox("Région", ["Toutes les régions"] + sorted_options(source, "region"))
region_df = source if region == "Toutes les régions" else apply_filters(source, region, "Tous les districts", "Toutes les communes", "Tous les fokontany")
district = st.sidebar.selectbox("District", ["Tous les districts"] + sorted_options(region_df, "district"))
district_df = apply_filters(region_df, region, district, "Toutes les communes", "Tous les fokontany")
commune = st.sidebar.selectbox("Commune", ["Toutes les communes"] + sorted_options(district_df, "commune"))
commune_df = apply_filters(district_df, region, district, commune, "Tous les fokontany")
fokontany = st.sidebar.selectbox("Fokontany", ["Tous les fokontany"] + sorted_options(commune_df, "fokontany"))
if st.sidebar.button("↺ Actualiser les données"):
    st.cache_data.clear()
    st.rerun()

bf = apply_filters(beneficiaries, region, district, commune, fokontany)
ddf = apply_filters(distribution, region, district, commune, fokontany)
adf = apply_filters(agro, region, district, commune, fokontany)
caption = filter_caption(region, district, commune, fokontany)

prod_est_col = first_existing(adf, ["production_estimee_kg", "production_estimee"])
prod_real_col = first_existing(adf, ["production_reelle_kg", "production_reelle"])
area_col = first_existing(adf, ["superficie_emblavee_ha"])
seed_col = first_existing(adf, ["quantite_semences_kg", "quantite_semences_recues"])

if page == "Vue globale":
    st.markdown('<h2 class="crs-section-title">Vue globale — 137</h2>', unsafe_allow_html=True)
    st.caption(caption)

    # Overview: population de référence = beneficiary_registration.
    registered = int(bf["beneficiary_key"].nunique(dropna=True)) if "beneficiary_key" in bf.columns else len(bf)
    sex = bf.get("ben_sex", pd.Series(index=bf.index, dtype="object")).map(normalize_text)
    men = int(sex.isin(["male", "m", "homme", "masculin"]).sum())
    women = int(sex.isin(["female", "f", "femme", "feminin"]).sum())
    hh = pd.to_numeric(bf.get("hh_size", pd.Series(index=bf.index, dtype=float)), errors="coerce")
    hh_mean = float(hh.mean()) if hh.notna().any() else 0.0

    # Farming vient de beneficiary_registration.
    if "project_outcome" in bf.columns:
        farming_keys = set(
            bf.loc[bf["project_outcome"].map(normalize_text).eq("farming"), "beneficiary_key"].dropna()
        )
    else:
        farming_keys = set()
    agriculture = len(farming_keys)


    for box, label, value in zip(
        st.columns(4),
        ["Bénéficiaires uniques", "Hommes", "Femmes", "Taille moyenne du ménage"],
        [registered, men, women, hh_mean],
    ):
        box.metric(label, f"{value:,.1f}" if label.startswith("Taille") else f"{value:,}")

    c1, _, _, _ = st.columns(4)
    c1.metric("Bénéficiaires Agriculture/Farming", f"{agriculture:,}")

    if "project_outcome" in bf.columns:
        overview = (
            bf.assign(Catégorie=bf["project_outcome"].fillna("Non renseigné"))
            .groupby("Catégorie", dropna=False)["beneficiary_key"]
            .nunique()
            .reset_index(name="Bénéficiaires uniques")
        )
        st.dataframe(overview, use_container_width=True, hide_index=True)

elif page == "Suivi des distributions":
    st.markdown('<h2 class="crs-section-title">Suivi des distributions — Projet 137</h2>', unsafe_allow_html=True)
    st.caption(caption)
    if ddf.empty:
        st.info("Aucune donnée de distribution.")
        diag = diagnose_distribution()
        with st.expander("🔍 Diagnostic", expanded=True):
            if not diag.get("table_exists"):
                st.write("❌ La table `distribution_137` est absente dans le schéma public.")
            else:
                st.write(f"Table `distribution_137` : **{diag.get('rows', 0)}** ligne(s).")
                st.write("Colonnes disponibles :")
                st.code(", ".join(diag.get("columns", [])))
        st.stop()
    available = [name for name, items in DISTRIBUTION_QUANTITIES.items() if any(col in ddf.columns and pd.to_numeric(ddf[col], errors="coerce").fillna(0).gt(0).any() for col, _, _ in items)]
    if not available:
        st.info("Aucun volet de distribution ne contient de données.")
        st.stop()
    vm = compute_volet_metrics(ddf, st.selectbox("Type de distribution", available))
    summary, detail = vm["qty_summary"], vm["detail_df"]
    beneficiary_count = int(detail["unique_key"].nunique(dropna=True)) if "unique_key" in detail.columns else len(detail)
    localities = int(detail["fokontany"].nunique(dropna=True)) if "fokontany" in detail.columns else 0
    total_distributed = float(summary["Total distribué"].sum()) if not summary.empty else 0
    for box, label, value in zip(
        st.columns(3),
        ["Bénéficiaires", "Fokontany couverts", "Total distribué"],
        [beneficiary_count, localities, total_distributed],
    ):
        box.metric(label, f"{value:,.0f}")
    st.subheader("Résumé des quantités distribuées")
    st.dataframe(summary, use_container_width=True, hide_index=True)
    if not summary.empty: st.plotly_chart(px.bar(summary,x="Quantité",y="Total distribué",color="Unité",text="Total distribué"),use_container_width=True)
    with st.expander("🔍 Diagnostic du calcul"):
        st.dataframe(vm["debug"],use_container_width=True,hide_index=True)
    cols = [c for c in ["code_beneficiaire", "methode_identifiant", "region", "district", "commune", "fokontany", "type_beneficiaire", "resultat_projet", "code_projet", "nom_complet", "age", "sexe", "riz_x265_kg", "arachide_kg", "brede_mafana_sachet", "concombre_sachet", "courgette_sachet", "petsai_sachet", "tomate_sachet", "arrosoire_piece", "beche_piece", "pulverisateur_piece", "livret_recu", "localite_source"] if c in detail.columns]
    st.subheader("Détail des bénéficiaires")
    st.dataframe(detail[cols],use_container_width=True,hide_index=True)

elif page == "Suivi de production":
    st.markdown('<h2 class="crs-section-title">Suivi de production — Projet 137</h2>', unsafe_allow_html=True)
    st.caption(caption)
    if adf.empty:
        st.info(f"Aucune donnée disponible dans public.{AGRO_TABLE} avec ces filtres.")
        st.stop()
    households = int(adf["beneficiary_key"].nunique(dropna=True)) if "beneficiary_key" in adf.columns else len(adf)
    categories = (
        int(adf["categorie_semence"].nunique(dropna=True))
        if "categorie_semence" in adf.columns else 0
    )
    for box, label, value, fmt in zip(st.columns(4), ["Ménages suivis", "Catégories de semences", "Superficie emblavée (ha)", "Production réelle (kg)"], [households, categories, numeric_sum(adf, area_col), numeric_sum(adf, prod_real_col)], [",.0f", ",.0f", ",.2f", ",.0f"]):
        box.metric(label, format(value, fmt))
    if "categorie_semence" in adf.columns:
        summary = adf.groupby("categorie_semence", dropna=False).agg(menages=("beneficiary_key", "nunique")).reset_index()
        metrics = [("semences", seed_col), ("superficie_ha", area_col), ("production_estimee", prod_est_col), ("production_reelle_kg", prod_real_col), ("stockee_kg", first_existing(adf, ["quantite_stockee_kg"])), ("consomme", first_existing(adf, ["consomme"])), ("semence", first_existing(adf, ["semence"]))]
        for output_col, source_col in metrics:
            summary[output_col] = adf.groupby("categorie_semence", dropna=False)[source_col].sum().values if source_col else 0
        summary = summary.rename(
            columns={"categorie_semence": "Catégorie de la semence"}
        )
        st.subheader("Résumé par catégorie de semence")
        st.dataframe(summary, use_container_width=True, hide_index=True)
        chart = summary.melt(id_vars="Catégorie de la semence", value_vars=["production_estimee", "production_reelle_kg"], var_name="Indicateur", value_name="Valeur")
        st.plotly_chart(px.bar(chart, x="Catégorie de la semence", y="Valeur", color="Indicateur", barmode="group"), use_container_width=True)
        destination_cols = [c for c in ["stockee_kg", "consomme", "semence"] if summary[c].fillna(0).ne(0).any()]
        if destination_cols:
            destination = summary.melt(id_vars="Catégorie de la semence", value_vars=destination_cols, var_name="Destination", value_name="Valeur")
            st.subheader("Destination de la production")
            st.plotly_chart(px.bar(destination, x="Catégorie de la semence", y="Valeur", color="Destination", barmode="stack"), use_container_width=True)
    st.subheader("Détail du suivi")
    safe = adf.drop(columns=["beneficiary_key", "nom_code_menage", "nom_code_menage_pms"], errors="ignore")
    st.dataframe(safe, use_container_width=True, hide_index=True)

else:
    st.markdown('<h2 class="crs-section-title">Qualité des données — Projet 137</h2>', unsafe_allow_html=True)
    tables = [t for t in ["beneficiary_registration", "distribution", "distribution_groupement", AGRO_TABLE] if table_exists(t)]
    if not tables:
        st.warning("Aucune table attendue n'est disponible.")
        st.stop()
    selected = st.selectbox("Table à contrôler", tables)
    quality_df = read_table(selected)
    c1, c2, c3 = st.columns(3)
    c1.metric("Lignes analysées", f"{len(quality_df):,}")
    c2.metric("Doublons complets", f"{int(quality_df.duplicated().sum()):,}")
    c3.metric("Cellules vides", f"{int(quality_df.isna().sum().sum()):,}")
    missing = quality_df.isna().sum().reset_index().rename(columns={"index": "Colonne", 0: "Valeurs manquantes"})
    missing["Taux manquant (%)"] = missing["Valeurs manquantes"] / len(quality_df) * 100 if len(quality_df) else 0
    st.dataframe(missing, use_container_width=True, hide_index=True)
    numeric_cols = quality_df.select_dtypes(include="number").columns.tolist()
    if numeric_cols:
        selected_numeric = st.selectbox("Variable numérique", numeric_cols)
        st.plotly_chart(px.box(quality_df, y=selected_numeric, points="outliers", title=f"Valeurs aberrantes : {selected_numeric}"), use_container_width=True)
