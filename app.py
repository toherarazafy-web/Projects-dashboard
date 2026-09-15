import unicodedata
import pandas as pd
import plotly.express as px
import streamlit as st
from sqlalchemy import inspect, text
from connections import DATABASES

st.set_page_config(page_title="Dashboard multi-projets", page_icon="📊", layout="wide", initial_sidebar_state="expanded")
CRS_COLORS={"bold_blue":"#00A2C7","crs_blue":"#00468B","bold_purple":"#9053A1","bold_teal":"#0099A9","bold_green":"#79A02C","bold_orange":"#EF6E0B","humble_gray":"#9D9385","humble_blue":"#7A99AC","humble_green":"#9B9455","humble_gold":"#B48F4B"}
px.defaults.color_discrete_sequence=list(CRS_COLORS.values()); px.defaults.template="plotly_white"
st.markdown(f'''<style>section[data-testid="stSidebar"]{{background:#F4F8FA;border-right:3px solid {CRS_COLORS['crs_blue']};}}div[data-testid="stMetric"]{{background:#FFF;border:1px solid #E4EBEE;border-left:5px solid {CRS_COLORS['bold_blue']};border-radius:8px;padding:.75rem 1rem;box-shadow:0 1px 3px rgba(0,0,0,.06);}}div[data-testid="stMetricValue"]{{color:{CRS_COLORS['crs_blue']};}}.crs-banner{{background:{CRS_COLORS['crs_blue']};padding:1.1rem 1.5rem;border-radius:10px;margin-bottom:1.2rem;color:white;}}.crs-banner h1{{margin:0;font-size:1.7rem;}}.crs-banner p{{color:#CCE4F5;margin:.2rem 0 0;}}.crs-section-title{{color:{CRS_COLORS['crs_blue']};border-bottom:3px solid {CRS_COLORS['bold_orange']};display:inline-block;}}</style><div class="crs-banner"><h1>📊 Dashboard 137 • 137EST • 4101</h1><p>Bases PostgreSQL : 137, 137est et 4101</p></div>''',unsafe_allow_html=True)
MAX_ROWS=50000
PRESENT_VALUES={"yes","true","t","1","oui","o"}
AGRI_CATEGORIES={"4101":{"farming"},"137est":{"farming"},"137":{"farming"}}
VOLET_CONFIG={
 "Semences / intrants agricoles":{"date_col":"agri_date","type_col":"agri_input_type","qty_cols":[("mais_weight_kg","kg de maïs"),("rice_weight_kg","kg de riz"),("groundnut_weight_kg","kg d'arachide"),("cassava_qty","tiges de manioc"),("swpotato_qty","lianes de patate douce")]},
 "CUMA (cultures maraîchères)":{"date_col":"cuma_date","type_col":"cuma_type","qty_cols":[("cuma_weight_kg","sachets")]},
 "Kit PMA (petit matériel)":{"date_col":"pma_date","type_col":"pma_type","qty_cols":[("arrosoir_nb","arrosoirs"),("beche_nb","bêches")]}}

def normalize_text(v):
 if pd.isna(v): return ""
 v=unicodedata.normalize("NFKD",str(v).strip().lower()); return "".join(c for c in v if not unicodedata.combining(c))
def make_unique_key(df, cin_col, name_col, age_col=None):

 cin = (
  df[cin_col]
  .fillna("")
  .astype("string")
  .str.strip()
  if cin_col in df.columns
  else pd.Series("", index=df.index, dtype="string")
 )

 name = (
  df[name_col]
  .fillna("")
  .astype("string")
  .str.strip()
  .str.upper()
  if name_col in df.columns
  else pd.Series("", index=df.index, dtype="string")
 )

 if age_col and age_col in df.columns:

  age = (
   pd.to_numeric(
    df[age_col],
    errors="coerce"
   )
   .apply(
    lambda x: ""
    if pd.isna(x)
    else str(int(x))
   )
   .astype("string")
  )

 else:

  age = pd.Series(
   "",
   index=df.index,
   dtype="string",
  )

 key = (
  name.fillna("")
  + "|"
  + cin.fillna("")
  + "|"
  + age.fillna("")
 )

 return key.mask(
  (cin == "")
  & (name == "")
  & (age == "")
 )
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
 with DATABASES[project].connect() as con: df=pd.read_sql(text("SELECT "+",".join(f'\"{c}\"' for c in selected)+f' FROM public.\"{table}\"'),con)
 df["unique_key"]=make_unique_key(df,"ben_cin","ben_full_name","ben_age"); return df

@st.cache_data(ttl=1800)
def load_distribution_joined(project):
 stbl,btbl="distribution_submission","distribution_beneficiary"
 if not(table_exists(project,stbl) and table_exists(project,btbl)):return pd.DataFrame()
 sc,bc=columns(project,stbl),columns(project,btbl)
 sw=["id","kobo_uuid","submission_time","submitted_by","region","district","commune","fokontany","project_code","sector","cuma_date","cuma_type","cuma_weight_kg","agri_date","agri_input_type","mais_weight_kg","rice_weight_kg","groundnut_weight_kg","cassava_qty","cassava_unit","swpotato_qty","swpotato_unit","pma_date","pma_type","arrosoir_nb","beche_nb","nb_beneficiaries","distribution_date","agri_input_codes","rice_weight","groundnut_weight","declared_beneficiary_count","repeat_beneficiary_count","registration_number","enumerator_name","enumerator_org","agri_type"]
 bw=["id","parent_id","seq_num","present","village","full_name","sex","age","cin","ben_id_raw","submission_uuid","distribution_uuid","repeat_index","sequence_number","beneficiary_presence","beneficiary_id_raw","beneficiary_location","beneficiary_name","beneficiary_code","beneficiary_sex","beneficiary_age","beneficiary_cin","c3_raw"]
 sp=[('ds."id" AS "submission_id"' if c=="id" else f'ds."{c}"') for c in sw if c in sc]
 sp += [('db."id" AS "beneficiary_row_id"' if c=="id" else f'db."{c}"') for c in bw if c in bc]
 if "parent_id" in bc and "id" in sc: join='db."parent_id"::text=ds."id"::text'
 elif "distribution_uuid" in bc and "kobo_uuid" in sc: join='db."distribution_uuid"::text=ds."kobo_uuid"::text'
 elif "submission_uuid" in bc and "kobo_uuid" in sc: join='db."submission_uuid"::text=ds."kobo_uuid"::text'
 else:return pd.DataFrame()
 with DATABASES[project].connect() as con: df=pd.read_sql(text(f'SELECT {",".join(sp)} FROM public."{stbl}" ds INNER JOIN public."{btbl}" db ON {join}'),con)
 mp={"distribution_uuid":"submission_uuid","repeat_index":"seq_num","beneficiary_presence":"present","beneficiary_id_raw":"ben_id_raw","beneficiary_location":"village","beneficiary_name":"full_name","beneficiary_sex":"sex","beneficiary_age":"age","beneficiary_cin":"cin","distribution_date":"agri_date","agri_input_codes":"agri_input_type","rice_weight":"rice_weight_kg","groundnut_weight":"groundnut_weight_kg"}
 df=df.rename(columns={s:t for s,t in mp.items() if s in df and t not in df})
 for c in ["submission_id","parent_id","submission_uuid","kobo_uuid"]:
  if c in df: df["submission_group_id"]=df[c]; break
 if "submission_uuid" in df and "seq_num" in df:
  df["beneficiary_seq_key"]=df["submission_uuid"].astype(str)+"|"+df["seq_num"].astype(str)
 df["unique_key"]=make_unique_key(df,"cin","full_name","age"); return df

@st.cache_data(ttl=1800)
def load_agro_data(project):
 if project!="137est" or not table_exists(project,"da"): return pd.DataFrame()
 with DATABASES[project].connect() as con:return pd.read_sql(text(f'SELECT * FROM public."da" LIMIT {MAX_ROWS}'),con)

def diagnose_distribution(project):
 stbl,btbl="distribution_submission","distribution_beneficiary"
 info={"s_exists":table_exists(project,stbl),"b_exists":table_exists(project,btbl)}
 if not(info["s_exists"] and info["b_exists"]):return info
 sc,bc=columns(project,stbl),columns(project,btbl); info["sc"]=sc; info["bc"]=bc
 with DATABASES[project].connect() as con:
  info["s_rows"]=con.execute(text(f'SELECT COUNT(*) FROM public."{stbl}"')).scalar()
  info["b_rows"]=con.execute(text(f'SELECT COUNT(*) FROM public."{btbl}"')).scalar()
 if "parent_id" in bc and "id" in sc: info["join_key"]='distribution_beneficiary.parent_id = distribution_submission.id'
 elif "distribution_uuid" in bc and "kobo_uuid" in sc: info["join_key"]='distribution_beneficiary.distribution_uuid = distribution_submission.kobo_uuid'
 elif "submission_uuid" in bc and "kobo_uuid" in sc: info["join_key"]='distribution_beneficiary.submission_uuid = distribution_submission.kobo_uuid'
 else: info["join_key"]=None
 if info["join_key"]:
  with DATABASES[project].connect() as con:
   if "parent_id" in bc and "id" in sc: cond='db."parent_id"::text=ds."id"::text'
   elif "distribution_uuid" in bc and "kobo_uuid" in sc: cond='db."distribution_uuid"::text=ds."kobo_uuid"::text'
   else: cond='db."submission_uuid"::text=ds."kobo_uuid"::text'
   info["joined_rows"]=con.execute(text(f'SELECT COUNT(*) FROM public."{stbl}" ds INNER JOIN public."{btbl}" db ON {cond}')).scalar()
 return info

def project_kpis(project,r="Toutes les régions",d="Tous les districts",c="Toutes les communes"):
 reg=apply_location_filters(load_registration(project),r,d,c); dist=apply_location_filters(load_distribution_joined(project),r,d,c)
 unique=int(reg["unique_key"].nunique(dropna=True)) if not reg.empty else 0
 farming=set(reg.loc[reg["project_outcome"].map(normalize_text).isin(AGRI_CATEGORIES.get(project,{"farming"})),"unique_key"].dropna()) if "project_outcome" in reg else set()
 present=int(dist.loc[dist["present"].map(normalize_text).isin(PRESENT_VALUES),"unique_key"].nunique(dropna=True)) if "present" in dist else 0
 return {"registration":reg,"distribution":dist,"unique_beneficiaries":unique,"agriculture_beneficiaries":len(farming),"present_beneficiaries":present,"absent_beneficiaries":max(0,len(farming)-present),"presence_rate":present/len(farming)*100 if farming else 0}

def compute_volet_metrics(df,name):
 cfg=VOLET_CONFIG[name]; date=cfg["date_col"]
 if date not in df:return None
 volet=df[df[date].notna()].copy()
 if volet.empty:return None
 group=next((c for c in ["submission_group_id","submission_id","parent_id","submission_uuid","kobo_uuid"] if c in volet),None)
 bid=next((c for c in ["beneficiary_seq_key","beneficiary_row_id","unique_key"] if c in volet),None); rows=[]; debug=[]
 for q,label in cfg["qty_cols"]:
  if q not in volet:
   debug.append({"Quantité":label,"Colonne":q,"Présente":False});continue
  raw=volet[q]; parsed=pd.to_numeric(raw,errors="coerce")
  a=volet.assign(_q=parsed); a=a[a._q.gt(0)]
  d={"Quantité":label,"Colonne":q,"Présente":True,"Lignes volet":len(volet),
     "Non-null brut":int(raw.notna().sum()),"Numérique valide":int(parsed.notna().sum()),
     "Valeurs > 0":len(a),"Groupe utilisé":group,"Id bénéficiaire utilisé":bid,
     "bid non-null (>0)":int(a[bid].notna().sum()) if bid and not a.empty else 0}
  if a.empty:debug.append(d);continue
  if group and bid:
   s=a.groupby(group,dropna=False).agg(q=("_q","first"),n=(bid,"nunique")); total=(s.q*s.n).sum(); n=int(s.n.sum())
   d["Nb groupes distincts"]=a[group].nunique(dropna=True)
  else: total=a._q.sum(); n=int(a["unique_key"].nunique(dropna=True))
  d["n calculé"]=n; d["total calculé"]=float(total); debug.append(d)
  UNIT_MAP={"mais_weight_kg":"kg","rice_weight_kg":"kg","groundnut_weight_kg":"kg","cassava_qty":"tiges","swpotato_qty":"lianes"}
  unit = UNIT_MAP.get(q, "unités")
  rows.append({"Quantité":label,"Nombre bénéficiaires":n,"Total distribué":round(float(total),2),"Unité":unit})
 return {"qty_summary":pd.DataFrame(rows),"detail_df":volet,"type_col":cfg["type_col"],"debug":pd.DataFrame(debug)}

st.sidebar.markdown("### 🧭 Navigation")
page=st.sidebar.radio("Choisir une page",["Vue globale","Suivi des distributions","Suivi données agro","Qualité des données"],label_visibility="collapsed")
st.sidebar.divider();st.sidebar.markdown("### 📁 Projet");project=st.sidebar.selectbox("Projet",["137","137est","4101"],label_visibility="collapsed")
source=load_agro_data(project) if page=="Suivi données agro" else load_registration(project)
if source.empty and page!="Suivi données agro":source=load_distribution_joined(project)
region=st.sidebar.selectbox("Région",["Toutes les régions"]+sorted_options(source,"region")); rs=source if region=="Toutes les régions" or "region" not in source else source[source["region"].astype(str).str.strip()==region]
district=st.sidebar.selectbox("District",["Tous les districts"]+sorted_options(rs,"district")); ds=rs if district=="Tous les districts" or "district" not in rs else rs[rs["district"].astype(str).str.strip()==district]
commune=st.sidebar.selectbox("Commune",["Toutes les communes"]+sorted_options(ds,"commune"))
if st.sidebar.button("↺ Réinitialiser les filtres"):st.cache_data.clear();st.session_state.clear();st.rerun()

if page=="Vue globale":
 m=project_kpis(project,region,district,commune); reg=m["registration"]
 st.markdown(f'<h2 class="crs-section-title">Vue globale — {project}</h2>',unsafe_allow_html=True);st.caption(filter_caption(region,district,commune))
 if reg.empty:st.warning("Aucune donnée bénéficiaire avec les filtres sélectionnés.");st.stop()
 sex=reg.get("ben_sex",pd.Series(index=reg.index,dtype="object")).map(normalize_text); men=int(sex.isin(["male","m","homme","masculin"]).sum()); women=int(sex.isin(["female","f","femme","feminin"]).sum()); hh=pd.to_numeric(reg.get("hh_size",pd.Series(dtype=float)),errors="coerce")
 for b,l,v in zip(st.columns(4),["Bénéficiaires uniques","Hommes","Femmes","Taille moyenne du ménage"],[m["unique_beneficiaries"],men,women,hh.mean() if hh.notna().any() else 0]):b.metric(l,f"{v:,.1f}" if l.startswith("Taille") else f"{v:,}")
 for b,l,k in zip(st.columns(4),["Bénéficiaires Agriculture/Farming","Présents aux distributions","Absents aux distributions","Taux de présence"],["agriculture_beneficiaries","present_beneficiaries","absent_beneficiaries","presence_rate"]):b.metric(l,f'{m[k]:.1f}%' if k=="presence_rate" else f'{m[k]:,}')
 if "project_outcome" in reg:
  ot=reg.assign(Catégorie=reg["project_outcome"].fillna("Non renseigné")).groupby("Catégorie")["unique_key"].nunique().reset_index(name="Bénéficiaires uniques");st.dataframe(ot,use_container_width=True,hide_index=True);st.plotly_chart(px.bar(ot,x="Catégorie",y="Bénéficiaires uniques",color="Catégorie",text="Bénéficiaires uniques"),use_container_width=True)

elif page=="Suivi des distributions":
 d=apply_location_filters(load_distribution_joined(project),region,district,commune)
 st.markdown(f'<h2 class="crs-section-title">Suivi des distributions — {project}</h2>',unsafe_allow_html=True);st.caption(filter_caption(region,district,commune))
 if d.empty:
  st.info("Aucune donnée de distribution.")
  diag=diagnose_distribution(project)
  with st.expander("🔍 Diagnostic",expanded=True):
   if not diag.get("s_exists"):
    st.write(f"❌ La table `distribution_submission` est absente pour le projet **{project}**.")
   elif not diag.get("b_exists"):
    st.write(f"❌ La table `distribution_beneficiary` est absente pour le projet **{project}**.")
   else:
    st.write(f"`distribution_submission` : **{diag['s_rows']}** ligne(s) — `distribution_beneficiary` : **{diag['b_rows']}** ligne(s).")
    if diag["join_key"] is None:
     st.write("❌ Aucune paire de colonnes de jointure trouvée entre les deux tables (`parent_id`/`id`, `distribution_uuid`/`kobo_uuid` ou `submission_uuid`/`kobo_uuid`).")
     st.write("Colonnes disponibles dans `distribution_submission` :");st.code(", ".join(diag["sc"]))
     st.write("Colonnes disponibles dans `distribution_beneficiary` :");st.code(", ".join(diag["bc"]))
    else:
     st.write(f"Jointure utilisée : `{diag['join_key']}` → **{diag.get('joined_rows',0)}** ligne(s) après jointure.")
     if diag.get('joined_rows',0)==0:
      st.write("La jointure ne trouve aucune correspondance : vérifiez que les valeurs de ces colonnes concordent bien entre les deux tables (format UUID différent, casse, espaces, colonne vide...).")
  st.stop()
 available=[n for n,c in VOLET_CONFIG.items() if c["date_col"] in d and d[c["date_col"]].notna().any()]
 if not available:
  st.info("Aucun volet de distribution ne contient de données.")
  with st.expander("🔍 Diagnostic",expanded=True):
   for name,cfg in VOLET_CONFIG.items():
    col=cfg["date_col"]
    if col not in d:st.write(f"- **{name}** : colonne `{col}` absente du jeu de données joint.")
    else:
     nn=int(d[col].notna().sum());st.write(f"- **{name}** : colonne `{col}` présente, {nn} valeur(s) non nulle(s) sur {len(d)} ligne(s).")
  st.stop()
 vm=compute_volet_metrics(d,st.selectbox("Type de distribution",available)); detail=vm["detail_df"]
 st.dataframe(vm["qty_summary"],use_container_width=True,hide_index=True)
 if not vm["qty_summary"].empty:st.plotly_chart(px.bar(vm["qty_summary"],x="Quantité",y="Total distribué",text="Total distribué"),use_container_width=True)
 with st.expander("🔍 Diagnostic du calcul (pourquoi 0 ?)"):
  st.dataframe(vm["debug"],use_container_width=True,hide_index=True)
  st.caption("« Numérique valide » = valeurs converties avec succès en nombre. « Valeurs > 0 » = celles retenues pour le calcul. Si « bid non-null (>0) » est à 0 alors que « Valeurs > 0 » ne l'est pas, l'identifiant bénéficiaire est vide sur ces lignes-là — c'est la cause du 0.")
 cols=[c for c in ["submission_id","parent_id","submission_uuid","beneficiary_row_id","seq_num","sequence_number","present","village","full_name","beneficiary_code","sex","age","cin","agri_date","agri_input_type","mais_weight_kg","rice_weight_kg","groundnut_weight_kg","cassava_qty","cassava_unit","swpotato_qty","swpotato_unit","cuma_type","cuma_weight_kg"] if c in detail]
 st.subheader("Détail des bénéficiaires");st.dataframe(detail[cols],use_container_width=True,hide_index=True)

elif page=="Suivi données agro":
 st.markdown(f'<h2 class="crs-section-title">Suivi données agro — {project}</h2>',unsafe_allow_html=True);st.caption(filter_caption(region,district,commune))
 if project in {"137","4101"}:st.info("Pas de données disponibles pour le moment.");st.stop()
 agro_df=apply_location_filters(load_agro_data(project),region,district,commune)
 if agro_df.empty:st.info("Pas de données disponibles pour le moment.");st.stop()
 if "speculation" in agro_df:
  agro_df["speculation"]=agro_df["speculation"].astype("string").str.strip(); agro_df.loc[agro_df["speculation"].str.upper().eq("RIZ X266").fillna(False),"speculation"]="Riz X265"
 numeric_cols=["quantite_semences_kg","superficie_prevue_are","superficie_emblavee_are","superficie_emblavee_ha","production_estimee_kg"]
 for col in numeric_cols:
  if col in agro_df:agro_df[col]=pd.to_numeric(agro_df[col],errors="coerce")
 household_count=int(agro_df["nom_code_menage"].dropna().astype(str).str.strip().nunique()) if "nom_code_menage" in agro_df else len(agro_df)
 speculation_count=int(agro_df["speculation"].dropna().astype(str).str.strip().nunique()) if "speculation" in agro_df else 0
 production=agro_df["production_estimee_kg"].fillna(0).sum() if "production_estimee_kg" in agro_df else 0
 area=agro_df["superficie_emblavee_ha"].fillna(0).sum() if "superficie_emblavee_ha" in agro_df else 0
 for b,l,v,f in zip(st.columns(4),["Ménages suivis","Spéculations","Production estimée (kg)","Superficie emblavée (ha)"],[household_count,speculation_count,production,area],[",",",",",.0f",",.2f"]):b.metric(l,format(v,f))
 if "speculation" in agro_df:
  aggs={"nb_beneficiaires":("speculation","size")}
  for c in ["quantite_semences_kg","superficie_emblavee_ha","production_estimee_kg"]:
   if c in agro_df:aggs[c]=(c,"sum")
  spec_summary=agro_df.groupby("speculation",dropna=False).agg(**aggs).reset_index().fillna(0)
  for c in ["quantite_semences_kg","superficie_emblavee_ha","production_estimee_kg"]:
   if c not in spec_summary:spec_summary[c]=0
  spec_summary["unite_qte"]=spec_summary["speculation"].astype(str).str.lower().str.contains("manioc|cassava",na=False).map({True:"tiges",False:"kg"})
  st.subheader("Résumé par spéculation");st.dataframe(spec_summary.rename(columns={"speculation":"Spéculation","nb_beneficiaires":"Bénéficiaires","quantite_semences_kg":"Qté distribuée","unite_qte":"Unité qté distribuée","superficie_emblavee_ha":"Superficie emblavée (ha)","production_estimee_kg":"Production estimée (kg)"})[["Spéculation","Bénéficiaires","Qté distribuée","Unité qté distribuée","Production estimée (kg)","Superficie emblavée (ha)"]],use_container_width=True,hide_index=True)
  pc=spec_summary.melt(id_vars="speculation",value_vars=["quantite_semences_kg","production_estimee_kg"],var_name="Indicateur",value_name="Valeur");pc["Indicateur"]=pc["Indicateur"].replace({"quantite_semences_kg":"Qté distribuée","production_estimee_kg":"Production estimée (kg)"})
  st.subheader("Quantité distribuée vs production estimée");st.plotly_chart(px.bar(pc,x="speculation",y="Valeur",color="Indicateur",barmode="group",text="Valeur"),use_container_width=True)
  st.caption("Unité de la quantité distribuée : tiges pour le manioc, kg pour les autres cultures. La production estimée est toujours en kg.")
  st.subheader("Superficie emblavée (ha)");st.plotly_chart(px.bar(spec_summary,x="speculation",y="superficie_emblavee_ha",color="speculation",text="superficie_emblavee_ha"),use_container_width=True)
  st.subheader("Nombre de bénéficiaires");st.plotly_chart(px.bar(spec_summary,x="speculation",y="nb_beneficiaires",color="speculation",text="nb_beneficiaires"),use_container_width=True)
 st.subheader("Détail des données agro")
 if "nom_code_menage" in agro_df:agro_df=agro_df.drop(columns=["nom_code_menage"])
 st.dataframe(agro_df,use_container_width=True,hide_index=True)

else:
 st.markdown(f'<h2 class="crs-section-title">Qualité des données — {project}</h2>',unsafe_allow_html=True)
 tables=inspect(DATABASES[project]).get_table_names(schema="public"); selected=st.selectbox("Table à contrôler",tables)
 with DATABASES[project].connect() as con:q=pd.read_sql(text(f'SELECT * FROM public."{selected}" LIMIT {MAX_ROWS}'),con)
 a,b=st.columns(2);a.metric("Lignes analysées",len(q));b.metric("Doublons complets",int(q.duplicated().sum()))
 nums=q.select_dtypes(include="number").columns.tolist()
 if nums:
  n=st.selectbox("Variable numérique",nums);st.plotly_chart(px.box(q,y=n,points="outliers",title=f"Valeurs aberrantes : {n}"),use_container_width=True)