import unicodedata
import pandas as pd
import plotly.express as px
import streamlit as st
from sqlalchemy import inspect, text
from connections import DATABASES

st.set_page_config(page_title="Dashboard multi-projets", page_icon="📊", layout="wide", initial_sidebar_state="expanded")

CRS_COLORS = {"bold_blue":"#00A2C7","crs_blue":"#00468B","bold_purple":"#9053A1","bold_teal":"#0099A9","bold_green":"#79A02C","bold_orange":"#EF6E0B","humble_gray":"#9D9385","humble_blue":"#7A99AC","humble_green":"#9B9455","humble_gold":"#B48F4B"}
px.defaults.color_discrete_sequence = list(CRS_COLORS.values())
px.defaults.template = "plotly_white"

st.markdown(f"""<style>
section[data-testid="stSidebar"]{{background:#F4F8FA;border-right:3px solid {CRS_COLORS['crs_blue']}}}
div[data-testid="stMetric"]{{background:#FFF;border:1px solid #E4EBEE;border-left:5px solid {CRS_COLORS['bold_blue']};border-radius:8px;padding:.75rem 1rem;box-shadow:0 1px 3px rgba(0,0,0,.06)}}
div[data-testid="stMetricValue"]{{color:{CRS_COLORS['crs_blue']}}}
.crs-banner{{background:{CRS_COLORS['crs_blue']};padding:1.1rem 1.5rem;border-radius:10px;margin-bottom:1.2rem;color:white}}
.crs-banner h1{{margin:0;font-size:1.7rem}} .crs-banner p{{color:#CCE4F5;margin:.2rem 0 0}}
.crs-section-title{{color:{CRS_COLORS['crs_blue']};border-bottom:3px solid {CRS_COLORS['bold_orange']};display:inline-block}}
</style><div class="crs-banner"><h1>📊 Dashboard 137 • 137EST • 4101</h1><p>Bases PostgreSQL : 137, 137est et 4101</p></div>""", unsafe_allow_html=True)

MAX_ROWS = 50000
PRESENT_VALUES = {"yes","true","t","1","oui","o"}
AGRI_CATEGORIES = {"4101":{"farming"},"137est":{"farming"},"137":{"farming"}}
VOLET_CONFIG = {
 "Semences / intrants agricoles":{"date_col":"agri_date","type_col":"agri_input_type","qty_cols":[("mais_weight_kg","kg de maïs"),("rice_weight_kg","kg de riz"),("swpotato_qty","lianes de patate douce")]},
 "CUMA (cultures maraîchères)":{"date_col":"cuma_date","type_col":"cuma_type","qty_cols":[("cuma_weight_kg","sachets")]},
 "Kit PMA (petit matériel)":{"date_col":"pma_date","type_col":"pma_type","qty_cols":[("arrosoir_nb","arrosoirs"),("beche_nb","bêches")]},
}

def normalize_text(value):
    if pd.isna(value): return ""
    value = unicodedata.normalize("NFKD", str(value).strip().lower())
    return "".join(c for c in value if not unicodedata.combining(c))

def make_unique_key(df, cin_col, name_col, age_col=None):
    cin = df[cin_col].fillna("").astype(str).str.strip() if cin_col in df else pd.Series("",index=df.index)
    name = df[name_col].fillna("").astype(str).str.strip().str.upper() if name_col in df else pd.Series("",index=df.index)
    if age_col and age_col in df:
        age = pd.to_numeric(df[age_col],errors="coerce").apply(lambda x:"" if pd.isna(x) else str(int(x)))
    else: age = pd.Series("",index=df.index)
    return (name+"|"+cin+"|"+age).mask((cin=="")&(name=="")&(age==""))

def table_exists(project, table): return table in inspect(DATABASES[project]).get_table_names(schema="public")
def columns(project, table):
    return [c["name"] for c in inspect(DATABASES[project]).get_columns(table,schema="public")] if table_exists(project,table) else []
def sorted_options(df,col):
    if df.empty or col not in df: return []
    x=df[col].dropna().astype(str).str.strip(); return sorted(x[x!=""].unique())
def apply_location_filters(df,region,district,commune):
    for col,val,default in [("region",region,"Toutes les régions"),("district",district,"Tous les districts"),("commune",commune,"Toutes les communes")]:
        if val!=default and col in df: df=df[df[col].astype(str).str.strip()==val]
    return df
def filter_caption(r,d,c):
    p=[]
    if r!="Toutes les régions": p.append(f"Région : {r}")
    if d!="Tous les districts": p.append(f"District : {d}")
    if c!="Toutes les communes": p.append(f"Commune : {c}")
    return " • ".join(p) if p else "Aucun filtre géographique actif"

@st.cache_data(ttl=1800)
def load_registration(project):
    table="beneficiary_registration"
    wanted=["ben_cin","ben_full_name","ben_sex","ben_age","hh_size","project_outcome","region","district","commune","fokontany"]
    selected=[c for c in wanted if c in columns(project,table)]
    if not selected:return pd.DataFrame()
    sql='SELECT '+','.join(f'"{c}"' for c in selected)+f' FROM public."{table}"'
    with DATABASES[project].connect() as con: df=pd.read_sql(text(sql),con)
    df["unique_key"]=make_unique_key(df,"ben_cin","ben_full_name","ben_age")
    return df

@st.cache_data(ttl=1800)
def load_distribution_joined(project):
    if not(table_exists(project,"distribution_submission") and table_exists(project,"distribution_beneficiary")): return pd.DataFrame()
    ws=["kobo_uuid","submission_time","submitted_by","region","district","commune","fokontany","project_code","sector","cuma_date","cuma_type","cuma_weight_kg","agri_date","agri_input_type","mais_weight_kg","rice_weight_kg","swpotato_qty","swpotato_unit","pma_date","pma_type","arrosoir_nb","beche_nb","nb_beneficiaries"]
    wb=["id","seq_num","present","village","full_name","sex","age","cin","ben_id_raw","submission_uuid"]
    ss=[c for c in ws if c in columns(project,"distribution_submission")]; sb=[c for c in wb if c in columns(project,"distribution_beneficiary")]
    parts=[f'ds."{c}"' for c in ss]+[f'db."{c}" AS "{"beneficiary_row_id" if c=="id" else c}"' for c in sb]
    sql='SELECT '+','.join(parts)+' FROM public.distribution_submission ds JOIN public.distribution_beneficiary db ON db.submission_uuid=ds.kobo_uuid'
    with DATABASES[project].connect() as con: df=pd.read_sql(text(sql),con)
    df["unique_key"]=make_unique_key(df,"cin","full_name","age")
    return df.drop(columns=[c for c in ["cin","full_name","sex","age"] if c in df])

def project_kpis(project,region="Toutes les régions",district="Tous les districts",commune="Toutes les communes"):
    reg=apply_location_filters(load_registration(project),region,district,commune)
    dist=apply_location_filters(load_distribution_joined(project),region,district,commune)
    unique=int(reg["unique_key"].nunique(dropna=True)) if not reg.empty else 0
    categories=AGRI_CATEGORIES.get(project,{"farming"})
    if not reg.empty and "project_outcome" in reg:
        outcome=reg["project_outcome"].map(normalize_text)
        farming_keys=set(reg.loc[outcome.isin(categories),"unique_key"].dropna().unique())
    else: farming_keys=set()
    farming=len(farming_keys)
    if not dist.empty and "present" in dist:
        present_mask=dist["present"].map(normalize_text).isin(PRESENT_VALUES)
        present=int(dist.loc[present_mask,"unique_key"].nunique(dropna=True))
    else:
        present=0
    absent=max(0, farming-present)
    rate=present/farming*100 if farming else 0.0
    return {"registration":reg,"distribution":dist,"unique_beneficiaries":unique,"agriculture_beneficiaries":farming,"present_beneficiaries":present,"absent_beneficiaries":absent,"presence_rate":rate}

def compute_volet_metrics(df,name):
    cfg=VOLET_CONFIG[name]; col=cfg["date_col"]
    if col not in df:return None
    v=df[df[col].notna()].copy()
    if v.empty:return None
    rows=[]
    for q,label in cfg["qty_cols"]:
        if q not in v:continue
        x=pd.to_numeric(v[q],errors="coerce"); total=x.sum()
        if x.notna().any() and total!=0: rows.append({"Quantité":label,"Total distribué":round(float(total),2),"Nombre bénéficiaires":int(v.loc[x.gt(0),"unique_key"].nunique())})
    absent=None
    if "present" in v: absent=int(v.loc[~v["present"].map(normalize_text).isin(PRESENT_VALUES),"unique_key"].nunique())
    return {"n_participants":int(v["unique_key"].nunique()),"n_absent":absent,"qty_summary":pd.DataFrame(rows),"detail_df":v,"type_col":cfg["type_col"]}

st.sidebar.markdown("### 🧭 Navigation")
page=st.sidebar.radio("Choisir une page",["Vue globale","Suivi des distributions","Qualité des données"],label_visibility="collapsed")
st.sidebar.divider(); st.sidebar.markdown("### 📁 Projet")
project=st.sidebar.selectbox("Projet",["137","137est","4101"],label_visibility="collapsed")
source=load_registration(project)
if source.empty:source=load_distribution_joined(project)
r=st.sidebar.selectbox("Région",["Toutes les régions"]+sorted_options(source,"region"))
ds=source if r=="Toutes les régions" or "region" not in source else source[source["region"].astype(str).str.strip()==r]
d=st.sidebar.selectbox("District",["Tous les districts"]+sorted_options(ds,"district"))
cs=ds if d=="Tous les districts" or "district" not in ds else ds[ds["district"].astype(str).str.strip()==d]
c=st.sidebar.selectbox("Commune",["Toutes les communes"]+sorted_options(cs,"commune"))
if st.sidebar.button("↺ Réinitialiser les filtres"):st.session_state.clear();st.rerun()

if page=="Vue globale":
    m=project_kpis(project,r,d,c); reg=m["registration"]
    st.markdown(f'<h2 class="crs-section-title">Vue globale — {project}</h2>',unsafe_allow_html=True);st.caption(filter_caption(r,d,c))
    if reg.empty:st.warning("Aucune donnée bénéficiaire avec les filtres sélectionnés.");st.stop()
    sex=reg.get("ben_sex",pd.Series(index=reg.index,dtype="object")).map(normalize_text)
    men=int(sex.isin(["male","m","homme","masculin"]).sum());women=int(sex.isin(["female","f","femme","feminin"]).sum())
    hh=pd.to_numeric(reg.get("hh_size",pd.Series(dtype=float)),errors="coerce");hhmean=hh.mean() if hh.notna().any() else 0
    st.markdown("##### 👥 Démographie"); a=st.columns(4)
    for box,label,val in zip(a,["Bénéficiaires uniques","Hommes","Femmes","Taille moyenne du ménage"],[f'{m["unique_beneficiaries"]:,}',f"{men:,}",f"{women:,}",f"{hhmean:.1f}"]):box.metric(label,val)
    st.markdown("##### 🌾 Agriculture & distribution"); b=st.columns(4)
    b[0].metric("Bénéficiaires Agriculture/Farming",f'{m["agriculture_beneficiaries"]:,}')
    b[1].metric("Présents aux distributions",f'{m["present_beneficiaries"]:,}')
    b[2].metric("Absents aux distributions",f'{m["absent_beneficiaries"]:,}')
    b[3].metric("Taux de présence",f'{m["presence_rate"]:.1f}%')
    if "project_outcome" in reg:
        out=reg.assign(Catégorie=reg["project_outcome"].fillna("Non renseigné")).groupby("Catégorie")["unique_key"].nunique().reset_index(name="Bénéficiaires uniques")
        st.dataframe(out,use_container_width=True,hide_index=True);st.plotly_chart(px.bar(out,x="Catégorie",y="Bénéficiaires uniques",color="Catégorie",text="Bénéficiaires uniques"),use_container_width=True)

elif page=="Suivi des distributions":
    df=apply_location_filters(load_distribution_joined(project),r,d,c)
    st.markdown(f'<h2 class="crs-section-title">Suivi des distributions — {project}</h2>',unsafe_allow_html=True);st.caption(filter_caption(r,d,c))
    if df.empty:st.info("Aucune donnée de distribution.");st.stop()
    p=df["present"].map(normalize_text).isin(PRESENT_VALUES) if "present" in df else pd.Series(False,index=df.index)
    # Indicateurs cohérents avec la Vue globale : Farming, Présents et Absents.
    distribution_kpis = project_kpis(project, r, d, c)
    x = st.columns(3)
    x[0].metric(
        "Bénéficiaires Farming",
        f'{distribution_kpis["agriculture_beneficiaries"]:,}',
    )
    x[1].metric(
        "Présents aux distributions",
        f'{distribution_kpis["present_beneficiaries"]:,}',
    )
    x[2].metric(
        "Absents aux distributions",
        f'{distribution_kpis["absent_beneficiaries"]:,}',
    )
    available=[n for n,cfg in VOLET_CONFIG.items() if cfg["date_col"] in df and df[cfg["date_col"]].notna().any()]
    if not available:st.info("Aucun volet de distribution ne contient de données.");st.stop()
    name=st.selectbox("Type de distribution",available);vm=compute_volet_metrics(df,name)
    # Indicateurs propres à l'article/type de distribution sélectionné.
    # Présents = bénéficiaires présents parmi les lignes du volet sélectionné.
    volet_detail = vm["detail_df"]
    if "present" in volet_detail.columns:
        volet_present_mask = (
            volet_detail["present"].map(normalize_text).isin(PRESENT_VALUES)
        )
        volet_present_beneficiaries = int(
            volet_detail.loc[volet_present_mask, "unique_key"]
            .nunique(dropna=True)
        )
    else:
        volet_present_beneficiaries = 0

    # Absents = total Farming de la Vue globale - présents pour l'article sélectionné.
    volet_absent_beneficiaries = max(
        0,
        distribution_kpis["agriculture_beneficiaries"]
        - volet_present_beneficiaries,
    )

    k = st.columns(2)
    k[0].metric(
        "Bénéficiaires présents selon l’article distribué",
        f"{volet_present_beneficiaries:,}",
    )
    k[1].metric(
        "Bénéficiaires absents",
        f"{volet_absent_beneficiaries:,}",
    )
    if not vm["qty_summary"].empty:st.dataframe(vm["qty_summary"],use_container_width=True,hide_index=True);st.plotly_chart(px.bar(vm["qty_summary"],x="Quantité",y="Total distribué",text="Total distribué"),use_container_width=True)
    show=[z for z in ["submission_uuid","present","village","cuma_type","mais_weight_kg","rice_weight_kg","swpotato_qty","cuma_weight_kg"] if z in vm["detail_df"]]
    st.subheader("Détail des bénéficiaires");st.dataframe(vm["detail_df"][show],use_container_width=True,hide_index=True)

else:
    st.markdown(f'<h2 class="crs-section-title">Qualité des données — {project}</h2>',unsafe_allow_html=True)
    tables=inspect(DATABASES[project]).get_table_names(schema="public");selected=st.selectbox("Table à contrôler",tables)
    with DATABASES[project].connect() as con:qdf=pd.read_sql(text(f'SELECT * FROM public."{selected}" LIMIT {MAX_ROWS}'),con)
    q=st.columns(2);q[0].metric("Lignes analysées",len(qdf));q[1].metric("Doublons complets",int(qdf.duplicated().sum()))
    nums=qdf.select_dtypes(include="number").columns.tolist()
    if nums:
        col=st.selectbox("Variable numérique",nums);st.plotly_chart(px.box(qdf,y=col,points="outliers",title=f"Valeurs aberrantes : {col}"),use_container_width=True)
