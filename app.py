import unicodedata
import pandas as pd
import plotly.express as px
import streamlit as st
from sqlalchemy import inspect, text
from connections import DATABASES

st.set_page_config(page_title="Dashboard multi-projets", page_icon="📊", layout="wide", initial_sidebar_state="expanded")
CRS_COLORS={"bold_blue":"#00A2C7","crs_blue":"#00468B","bold_purple":"#9053A1","bold_teal":"#0099A9","bold_green":"#79A02C","bold_orange":"#EF6E0B","humble_gray":"#9D9385","humble_blue":"#7A99AC","humble_green":"#9B9455","humble_gold":"#B48F4B"}
px.defaults.color_discrete_sequence=list(CRS_COLORS.values()); px.defaults.template="plotly_white"
st.markdown(f"""<style>section[data-testid="stSidebar"]{{background:#F4F8FA;border-right:3px solid {CRS_COLORS['crs_blue']}}}div[data-testid="stMetric"]{{background:#FFF;border:1px solid #E4EBEE;border-left:5px solid {CRS_COLORS['bold_blue']};border-radius:8px;padding:.75rem 1rem}}.crs-banner{{background:{CRS_COLORS['crs_blue']};padding:1.1rem 1.5rem;border-radius:10px;color:white}}.crs-section-title{{color:{CRS_COLORS['crs_blue']};border-bottom:3px solid {CRS_COLORS['bold_orange']};display:inline-block}}</style><div class="crs-banner"><h1>📊 Dashboard 137 • 137EST • 4101</h1><p>Bases PostgreSQL : 137, 137est et 4101</p></div>""",unsafe_allow_html=True)
MAX_ROWS=50000
PRESENT_VALUES={"yes","true","t","1","oui","o"}
AGRI_CATEGORIES={p:{"farming"} for p in ["137","137est","4101"]}
VOLET_CONFIG={
 "Semences / intrants agricoles":{"date_col":"agri_date","type_col":"agri_input_type","qty_cols":[("mais_weight_kg","kg de maïs"),("rice_weight_kg","kg de riz"),("groundnut_weight_kg","kg d'arachide"),("swpotato_qty","lianes de patate douce")]},
 "CUMA (cultures maraîchères)":{"date_col":"cuma_date","type_col":"cuma_type","qty_cols":[("cuma_weight_kg","sachets")]},
 "Kit PMA (petit matériel)":{"date_col":"pma_date","type_col":"pma_type","qty_cols":[("arrosoir_nb","arrosoirs"),("beche_nb","bêches")]}}

def normalize_text(v):
 if pd.isna(v): return ""
 v=unicodedata.normalize("NFKD",str(v).strip().lower()); return "".join(c for c in v if not unicodedata.combining(c))
def make_unique_key(df,cin_col,name_col,age_col=None):
 cin=df[cin_col].fillna("").astype(str).str.strip() if cin_col in df else pd.Series("",index=df.index)
 name=df[name_col].fillna("").astype(str).str.strip().str.upper() if name_col in df else pd.Series("",index=df.index)
 age=pd.to_numeric(df[age_col],errors="coerce").apply(lambda x:"" if pd.isna(x) else str(int(x))) if age_col in df else pd.Series("",index=df.index)
 return (name+"|"+cin+"|"+age).mask((cin=="")&(name=="")&(age==""))
def table_exists(project,table): return table in inspect(DATABASES[project]).get_table_names(schema="public")
def columns(project,table): return [c["name"] for c in inspect(DATABASES[project]).get_columns(table,schema="public")] if table_exists(project,table) else []
def sorted_options(df,col):
 if df.empty or col not in df: return []
 v=df[col].dropna().astype(str).str.strip(); return sorted(v[v!=""].unique())
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
 table="beneficiary_registration"; wanted=["ben_cin","ben_full_name","ben_sex","ben_age","hh_size","project_outcome","region","district","commune","fokontany"]
 selected=[c for c in wanted if c in columns(project,table)]
 if not selected:return pd.DataFrame()
 with DATABASES[project].connect() as con: df=pd.read_sql(text("SELECT "+",".join(f'"{c}"' for c in selected)+f' FROM public."{table}"'),con)
 df["unique_key"]=make_unique_key(df,"ben_cin","ben_full_name","ben_age"); return df

@st.cache_data(ttl=1800)
def load_distribution_joined(project):
 stbl,btbl="distribution_submission","distribution_beneficiary"
 if not(table_exists(project,stbl) and table_exists(project,btbl)):return pd.DataFrame()
 sc,bc=columns(project,stbl),columns(project,btbl)
 sw=["id","kobo_uuid","submission_time","submitted_by","region","district","commune","fokontany","project_code","sector","cuma_date","cuma_type","cuma_weight_kg","agri_date","agri_input_type","mais_weight_kg","rice_weight_kg","groundnut_weight_kg","swpotato_qty","swpotato_unit","pma_date","pma_type","arrosoir_nb","beche_nb","nb_beneficiaries","distribution_date","agri_input_codes","rice_weight","groundnut_weight","declared_beneficiary_count","repeat_beneficiary_count","registration_number","enumerator_name","enumerator_org","agri_type"]
 bw=["id","parent_id","seq_num","present","village","full_name","sex","age","cin","ben_id_raw","submission_uuid","distribution_uuid","repeat_index","sequence_number","beneficiary_presence","beneficiary_id_raw","beneficiary_location","beneficiary_name","beneficiary_code","beneficiary_sex","beneficiary_age","beneficiary_cin","c3_raw"]
 sp=[('ds."id" AS "submission_id"' if c=="id" else f'ds."{c}"') for c in sw if c in sc]
 sp += [('db."id" AS "beneficiary_row_id"' if c=="id" else f'db."{c}"') for c in bw if c in bc]
 if "parent_id" in bc and "id" in sc: join='db."parent_id"=ds."id"'
 elif "distribution_uuid" in bc and "kobo_uuid" in sc: join='db."distribution_uuid"=ds."kobo_uuid"'
 elif "submission_uuid" in bc and "kobo_uuid" in sc: join='db."submission_uuid"=ds."kobo_uuid"'
 else:return pd.DataFrame()
 sql=f'SELECT {",".join(sp)} FROM public."{stbl}" ds INNER JOIN public."{btbl}" db ON {join}'
 with DATABASES[project].connect() as con: df=pd.read_sql(text(sql),con)
 mp={"distribution_uuid":"submission_uuid","repeat_index":"seq_num","beneficiary_presence":"present","beneficiary_id_raw":"ben_id_raw","beneficiary_location":"village","beneficiary_name":"full_name","beneficiary_sex":"sex","beneficiary_age":"age","beneficiary_cin":"cin","distribution_date":"agri_date","agri_input_codes":"agri_input_type","rice_weight":"rice_weight_kg","groundnut_weight":"groundnut_weight_kg"}
 df=df.rename(columns={s:t for s,t in mp.items() if s in df and t not in df})
 for c in ["submission_id","parent_id","submission_uuid","kobo_uuid"]:
  if c in df: df["submission_group_id"]=df[c]; break
 df["unique_key"]=make_unique_key(df,"cin","full_name","age"); return df

@st.cache_data(ttl=1800)
def load_agro_data(project):
 if project!="137est" or not table_exists(project,"da"):return pd.DataFrame()
 with DATABASES[project].connect() as con:return pd.read_sql(text(f'SELECT * FROM public."da" LIMIT {MAX_ROWS}'),con)

def project_kpis(project,r="Toutes les régions",d="Tous les districts",c="Toutes les communes"):
 reg=apply_location_filters(load_registration(project),r,d,c); dist=apply_location_filters(load_distribution_joined(project),r,d,c)
 unique=int(reg["unique_key"].nunique()) if not reg.empty else 0
 farming=set(reg.loc[reg["project_outcome"].map(normalize_text).isin(AGRI_CATEGORIES[project]),"unique_key"].dropna()) if "project_outcome" in reg else set()
 present=int(dist.loc[dist["present"].map(normalize_text).isin(PRESENT_VALUES),"unique_key"].nunique()) if "present" in dist else 0
 return {"registration":reg,"unique_beneficiaries":unique,"agriculture_beneficiaries":len(farming),"present_beneficiaries":present,"absent_beneficiaries":max(0,len(farming)-present),"presence_rate":present/len(farming)*100 if farming else 0}

def compute_volet_metrics(df,name):
 cfg=VOLET_CONFIG[name]; date=cfg["date_col"]
 if date not in df:return None
 volet=df[df[date].notna()].copy()
 if volet.empty:return None
 group=next((c for c in ["submission_group_id","submission_id","parent_id","submission_uuid","kobo_uuid"] if c in volet),None)
 bid=next((c for c in ["beneficiary_row_id","unique_key"] if c in volet),None); rows=[]
 for q,label in cfg["qty_cols"]:
  if q not in volet:continue
  a=volet.assign(_q=pd.to_numeric(volet[q],errors="coerce")); a=a[a._q.gt(0)]
  if a.empty:continue
  if group and bid:
   s=a.groupby(group,dropna=False).agg(q=("_q","first"),n=(bid,"nunique")); total=(s.q*s.n).sum(); n=int(s.n.sum())
  else: total=a._q.sum(); n=int(a["unique_key"].nunique())
  rows.append({"Quantité":label,"Nombre bénéficiaires":n,"Total distribué":round(float(total),2)})
 return {"qty_summary":pd.DataFrame(rows),"detail_df":volet,"type_col":cfg["type_col"]}

st.sidebar.markdown("### 🧭 Navigation")
page=st.sidebar.radio("Choisir une page",["Vue globale","Suivi des distributions","Suivi données agro","Qualité des données"],label_visibility="collapsed")
st.sidebar.divider();st.sidebar.markdown("### 📁 Projet");project=st.sidebar.selectbox("Projet",["137","137est","4101"],label_visibility="collapsed")
source=load_agro_data(project) if page=="Suivi données agro" else load_registration(project)
if source.empty and page!="Suivi données agro":source=load_distribution_joined(project)
region=st.sidebar.selectbox("Région",["Toutes les régions"]+sorted_options(source,"region")); rs=source if region=="Toutes les régions" or "region" not in source else source[source.region.astype(str).str.strip()==region]
district=st.sidebar.selectbox("District",["Tous les districts"]+sorted_options(rs,"district")); ds=rs if district=="Tous les districts" or "district" not in rs else rs[rs.district.astype(str).str.strip()==district]
commune=st.sidebar.selectbox("Commune",["Toutes les communes"]+sorted_options(ds,"commune"))
if st.sidebar.button("↺ Réinitialiser les filtres"):st.cache_data.clear();st.session_state.clear();st.rerun()

if page=="Vue globale":
 m=project_kpis(project,region,district,commune); reg=m["registration"]
 st.markdown(f'<h2 class="crs-section-title">Vue globale — {project}</h2>',unsafe_allow_html=True);st.caption(filter_caption(region,district,commune))
 if reg.empty:st.warning("Aucune donnée bénéficiaire avec les filtres sélectionnés.");st.stop()
 sex=reg.get("ben_sex",pd.Series(index=reg.index,dtype="object")).map(normalize_text);men=int(sex.isin(["male","m","homme","masculin"]).sum());women=int(sex.isin(["female","f","femme","feminin"]).sum());hh=pd.to_numeric(reg.get("hh_size",pd.Series(dtype=float)),errors="coerce")
 vals=[m["unique_beneficiaries"],men,women,hh.mean() if hh.notna().any() else 0]
 for b,l,v in zip(st.columns(4),["Bénéficiaires uniques","Hommes","Femmes","Taille moyenne du ménage"],vals):b.metric(l,f"{v:,.1f}" if l.startswith("Taille") else f"{v:,}")
 for b,l,k in zip(st.columns(4),["Bénéficiaires Agriculture/Farming","Présents aux distributions","Absents aux distributions","Taux de présence"],["agriculture_beneficiaries","present_beneficiaries","absent_beneficiaries","presence_rate"]):b.metric(l,f'{m[k]:.1f}%' if k=="presence_rate" else f'{m[k]:,}')

elif page=="Suivi des distributions":
 d=apply_location_filters(load_distribution_joined(project),region,district,commune)
 st.markdown(f'<h2 class="crs-section-title">Suivi des distributions — {project}</h2>',unsafe_allow_html=True);st.caption(filter_caption(region,district,commune))
 if d.empty:st.info("Aucune donnée de distribution.");st.stop()
 available=[n for n,c in VOLET_CONFIG.items() if c["date_col"] in d and d[c["date_col"]].notna().any()]
 if not available:st.info("Aucun volet de distribution ne contient de données.");st.stop()
 vm=compute_volet_metrics(d,st.selectbox("Type de distribution",available));detail=vm["detail_df"]
 st.dataframe(vm["qty_summary"],use_container_width=True,hide_index=True)
 if not vm["qty_summary"].empty:st.plotly_chart(px.bar(vm["qty_summary"],x="Quantité",y="Total distribué",text="Total distribué"),use_container_width=True)
 cols=[c for c in ["submission_id","parent_id","submission_uuid","beneficiary_row_id","seq_num","sequence_number","present","village","full_name","beneficiary_code","sex","age","cin","agri_date","agri_input_type","mais_weight_kg","rice_weight_kg","groundnut_weight_kg","swpotato_qty","cuma_type","cuma_weight_kg"] if c in detail]
 st.subheader("Détail des bénéficiaires");st.dataframe(detail[cols],use_container_width=True,hide_index=True)

elif page=="Suivi données agro":
 agro=apply_location_filters(load_agro_data(project),region,district,commune)
 st.markdown(f'<h2 class="crs-section-title">Suivi données agro — {project}</h2>',unsafe_allow_html=True)
 if agro.empty:st.info("Pas de données disponibles pour le moment.");st.stop()
 if "nom_code_menage" in agro:agro=agro.drop(columns=["nom_code_menage"])
 st.dataframe(agro,use_container_width=True,hide_index=True)
else:
 tables=inspect(DATABASES[project]).get_table_names(schema="public");t=st.selectbox("Table à contrôler",tables)
 with DATABASES[project].connect() as con:q=pd.read_sql(text(f'SELECT * FROM public."{t}" LIMIT {MAX_ROWS}'),con)
 a,b=st.columns(2);a.metric("Lignes analysées",len(q));b.metric("Doublons complets",int(q.duplicated().sum()))
 nums=q.select_dtypes(include="number").columns.tolist()
 if nums:
  n=st.selectbox("Variable numérique",nums);st.plotly_chart(px.box(q,y=n,points="outliers",title=f"Valeurs aberrantes : {n}"),use_container_width=True)
