# -*- coding: utf-8 -*-
import html
import sys
from pathlib import Path

import pandas as pd
import plotly.express as px
import streamlit as st
from sqlalchemy import inspect, text

ROOT_DIR = Path(__file__).resolve().parents[1]
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from connections import DATABASES

st.set_page_config(page_title="Dashboard Projet 4101", page_icon="📊", layout="wide")
ENGINE = DATABASES["4101"]
SCHEMA = "public"
MAX_ROWS = 150000
TABLES = {"benef":"beneficiary_registration","menages":"distribution","groupements":"distribution_groupement","production":"suivi_production_4101"}

st.markdown("""<style>
section[data-testid="stSidebar"]{background:#F4F8FA;border-right:3px solid #00468B}
div[data-testid="stMetric"]{background:white;border:1px solid #E1E8ED;border-left:5px solid #00A2C7;border-radius:10px;padding:.8rem 1rem}
div[data-testid="stMetricValue"]{color:#00468B}.banner{background:linear-gradient(90deg,#00468B,#00A2C7);color:white;padding:1.1rem 1.5rem;border-radius:12px;margin-bottom:1rem}.banner h1{margin:0}.title{color:#00468B;border-bottom:3px solid #9053A1;display:inline-block}</style>
<div class="banner"><h1>📊 Dashboard du projet 4101</h1><p>Bénéficiaires, distributions et suivi de production agricole</p></div>""",unsafe_allow_html=True)
px.defaults.template="plotly_white"
px.defaults.color_discrete_sequence=["#00468B","#00A2C7","#9053A1","#0099A9","#79A02C","#EF6E0B"]

def existing_tables():
    try:return set(inspect(ENGINE).get_table_names(schema=SCHEMA))
    except Exception as e:st.error(f"Connexion impossible : {e}");st.stop()

@st.cache_data(ttl=900,show_spinner=False)
def load(name):
    if name not in existing_tables():return pd.DataFrame()
    try:
        with ENGINE.connect() as con:return pd.read_sql(text(f'SELECT * FROM {SCHEMA}."{name}" LIMIT {MAX_ROWS}'),con)
    except Exception as e:st.warning(f"Lecture impossible de {name} : {e}");return pd.DataFrame()

def prep(df):
    d=df.copy()
    for c in ["region","district","commune","fokontany","nom_groupement","nom_code_menage","code_benef","secteur_activite","gs_cs_annee","chaine_valeur","techniques_cep_repliquees","autres_techniques_utilisees","unite","article"]:
        if c in d:
            d[c]=d[c].apply(lambda x:x if pd.isna(x) else ("Liane" if str(x).strip().lower()=="liane" else "kg" if str(x).strip().lower()=="kg" else str(x).strip()))
    for c in ["quantite_semences_recues","quantite_semences_semees","superficie_prevue_are","superficie_emblavee_are","superficie_emblavee_ha","production_estimee_kg","production_reelle_kg","production_reelle_tonne","quantite_consommee_kg","quantite_vendue_kg","prix_vente_marche","quantite_stockee_kg","point_gps_latitude","point_gps_longitude","point_gps_altitude","point_gps_precision","quantite_distribuee","quantite","nombre"]:
        if c in d:d[c]=pd.to_numeric(d[c],errors="coerce")
    for c in ["date_suivi_1","date_semis","date_suivi_2","date_recolte"]:
        if c in d:d[c]=pd.to_datetime(d[c],errors="coerce")
    return d

def filt(df,filters):
    d=df.copy()
    for c,v in filters.items():
        if v!="Tous" and c in d:d=d[d[c].astype(str)==str(v)]
    return d

def options(df,c):
    if df.empty or c not in df:return ["Tous"]
    return ["Tous"]+sorted(df[c].dropna().astype(str).str.strip().replace("",pd.NA).dropna().unique().tolist())

def nunique(df,c):return int(df[c].nunique()) if not df.empty and c in df else 0
def total(df,c):return float(df[c].sum()) if not df.empty and c in df else 0.0
def fmt(x,n=0):return f"{x:,.{n}f}".replace(","," ")
def first(df,names):return next((c for c in names if c in df),None)
def title(t):st.markdown(f'<h2 class="title">{html.escape(t)}</h2>',unsafe_allow_html=True)
def empty(msg="Aucune donnée disponible pour les filtres sélectionnés."):st.info(msg)
def qcol(df):return first(df,["quantite_distribuee","quantite","quantite_totale","nombre","quantite_semence","quantite_semences"])
def ccol(df):return first(df,["categorie_semences","categorie_semence","article","type_intrant","chaine_valeur","designation"])
def acol(df):return first(df,["article","categorie_semences","categorie_semence","type_intrant","designation","chaine_valeur"])

def article_summary(df,id_col=None):
    """Tableau : nombre de bénéficiaires et quantité distribuée par article."""
    art=acol(df);qty=qcol(df)
    if df.empty or not art:return pd.DataFrame()
    d=df.copy()
    d[art]=d[art].fillna("Non renseigné").astype(str).str.strip().replace("","Non renseigné")
    keys=[art]
    if "unite" in d and art!="unite":
        d["unite"]=d["unite"].fillna("").astype(str).str.strip();keys.append("unite")
    d["_n"]=1
    agg={"Bénéficiaires":(id_col,"nunique") if id_col and id_col in d else ("_n","sum")}
    if qty:agg["Quantité distribuée"]=(qty,"sum")
    out=d.groupby(keys,dropna=False).agg(**agg).reset_index()
    out=out.rename(columns={art:"Article","unite":"Unité"})
    return out.sort_values("Quantité distribuée" if qty else "Bénéficiaires",ascending=False).reset_index(drop=True)

def show_article_summary(df,id_col=None,who="Bénéficiaires"):
    st.subheader("Résumé par article")
    s=article_summary(df,id_col)
    if s.empty:
        st.info("Aucune colonne d'article disponible pour produire le résumé.");return
    s=s.rename(columns={"Bénéficiaires":who})
    st.dataframe(s,width="stretch",hide_index=True)

benef=prep(load(TABLES["benef"]));menages=prep(load(TABLES["menages"]));groupements=prep(load(TABLES["groupements"]));production=prep(load(TABLES["production"]))

# Pour l’affichage du ménage, garder uniquement le CIN situé après le dernier caractère |.
def extract_cin(value):
    if pd.isna(value):
        return value
    return str(value).split("|")[-1].strip()

if "nom_code_menage" in production.columns:
    production["cin_menage"] = production["nom_code_menage"].map(extract_cin)
source=next((d for d in [production,menages,groupements,benef] if not d.empty and "region" in d),pd.DataFrame())
st.sidebar.title("Projet 4101")
region=st.sidebar.selectbox("Région",options(source,"region"));s1=filt(source,{"region":region})
district=st.sidebar.selectbox("District",options(s1,"district"));s2=filt(s1,{"district":district})
commune=st.sidebar.selectbox("Commune",options(s2,"commune"));s3=filt(s2,{"commune":commune})
fokontany=st.sidebar.selectbox("Fokontany",options(s3,"fokontany"))
filters={"region":region,"district":district,"commune":commune,"fokontany":fokontany}
page=st.sidebar.radio("Navigation",["Vue globale","Distribution aux ménages","Distribution aux groupements","Suivi de production","Carte","Qualité des données"])
if st.sidebar.button("Actualiser les données",width="stretch"):st.cache_data.clear();st.rerun()
bdf,hdf,gdf,pdf=[filt(d,filters) for d in [benef,menages,groupements,production]]

if page=="Vue globale":
    title("Vue globale");bid=first(bdf,["code_beneficiaire","ben_unique_id","code_benef","nom_code_menage"])
    vals=[("Bénéficiaires enregistrés",nunique(bdf,bid) if bid else len(bdf)),("Ménages suivis",nunique(pdf,"nom_code_menage")),("Groupements suivis",nunique(pdf,"nom_groupement")),("Chaînes de valeur",nunique(pdf,"chaine_valeur"))]
    for col,(lab,val) in zip(st.columns(4),vals):col.metric(lab,fmt(val))
    vals=[("Superficie emblavée",fmt(total(pdf,"superficie_emblavee_ha"),2)+" ha"),("Production estimée",fmt(total(pdf,"production_estimee_kg"))+" kg"),("Production réelle",fmt(total(pdf,"production_reelle_kg"))+" kg"),("Quantité vendue",fmt(total(pdf,"quantite_vendue_kg"))+" kg")]
    for col,(lab,val) in zip(st.columns(4),vals):col.metric(lab,val)
    if not pdf.empty and "chaine_valeur" in pdf:
        x=pdf.groupby("chaine_valeur",dropna=False).agg(Ménages=("nom_code_menage","nunique"),Production=("production_reelle_kg","sum")).reset_index()
        a,b=st.columns(2);a.plotly_chart(px.bar(x,x="chaine_valeur",y="Ménages",color="chaine_valeur",title="Ménages par chaîne de valeur"),width="stretch");b.plotly_chart(px.bar(x,x="chaine_valeur",y="Production",color="chaine_valeur",title="Production réelle par chaîne de valeur"),width="stretch")

elif page=="Distribution aux ménages":
    title("Distribution aux ménages")
    if hdf.empty:empty("Aucune donnée dans public.distribution.")
    else:
        hid=first(hdf,["code_benef","code_beneficiaire","nom_code_menage"]);cat=ccol(hdf);qty=qcol(hdf)
        for col,(lab,val) in zip(st.columns(3),[("Ménages bénéficiaires",nunique(hdf,hid) if hid else len(hdf)),("Catégories de semences",nunique(hdf,cat) if cat else 0),("Quantité distribuée",fmt(total(hdf,qty)) if qty else "N/D")]):col.metric(lab,val)
        show_article_summary(hdf,hid,"Ménages bénéficiaires")
        if cat and qty:
            x=hdf.groupby(cat,dropna=False)[qty].sum().reset_index();st.plotly_chart(px.bar(x,x=cat,y=qty,color=cat,title="Quantité par catégorie de semences"),width="stretch")
        st.dataframe(hdf.drop(columns=["nom_code_menage"],errors="ignore"),width="stretch",hide_index=True)

elif page=="Distribution aux groupements":
    title("Distribution aux groupements")
    if gdf.empty:empty("Aucune donnée dans public.distribution_groupement.")
    else:
        cat=ccol(gdf);qty=qcol(gdf)
        for col,(lab,val) in zip(st.columns(3),[("Groupements bénéficiaires",nunique(gdf,"nom_groupement")),("Catégories de semences",nunique(gdf,cat) if cat else 0),("Quantité distribuée",fmt(total(gdf,qty)) if qty else "N/D")]):col.metric(lab,val)
        show_article_summary(gdf,"nom_groupement" if "nom_groupement" in gdf else None,"Groupements bénéficiaires")
        if cat and qty:
            x=gdf.groupby(cat,dropna=False)[qty].sum().reset_index();st.plotly_chart(px.bar(x,x=cat,y=qty,color=cat,title="Quantité distribuée aux groupements"),width="stretch")
        st.dataframe(gdf,width="stretch",hide_index=True)

elif page=="Suivi de production":
    title("Suivi de production agricole")
    if pdf.empty:empty("Aucune donnée dans public.suivi_production_4101.")
    else:
        chains=sorted(pdf["chaine_valeur"].dropna().astype(str).unique()) if "chaine_valeur" in pdf else []
        chosen=st.multiselect("Chaîne de valeur",chains,default=chains);view=pdf[pdf["chaine_valeur"].isin(chosen)] if chains else pdf
        metrics=[("Ménages suivis",fmt(nunique(view,"nom_code_menage"))),("Semences reçues",fmt(total(view,"quantite_semences_recues"))+" kg"),("Semences semées",fmt(total(view,"quantite_semences_semees"))+" kg"),("Superficie emblavée",fmt(total(view,"superficie_emblavee_ha"),2)+" ha"),("Production estimée",fmt(total(view,"production_estimee_kg"))+" kg"),("Production réelle",fmt(total(view,"production_reelle_kg"))+" kg"),("Quantité consommée",fmt(total(view,"quantite_consommee_kg"))+" kg"),("Quantité vendue",fmt(total(view,"quantite_vendue_kg"))+" kg")]
        for row in [metrics[:4],metrics[4:]]:
            for col,(lab,val) in zip(st.columns(4),row):col.metric(lab,val)
        summary=view.groupby("chaine_valeur",dropna=False).agg(menages=("nom_code_menage","nunique"),groupements=("nom_groupement","nunique"),semences_recues_kg=("quantite_semences_recues","sum"),semences_semees_kg=("quantite_semences_semees","sum"),superficie_emblavee_ha=("superficie_emblavee_ha","sum"),production_estimee_kg=("production_estimee_kg","sum"),production_reelle_kg=("production_reelle_kg","sum"),quantite_consommee_kg=("quantite_consommee_kg","sum"),quantite_vendue_kg=("quantite_vendue_kg","sum"),quantite_stockee_kg=("quantite_stockee_kg","sum"),prix_vente_moyen=("prix_vente_marche","mean")).reset_index()
        st.subheader("Résumé par chaîne de valeur");st.dataframe(summary,width="stretch",hide_index=True)
        a,b=st.columns(2)
        x=summary.melt(id_vars="chaine_valeur",value_vars=["production_estimee_kg","production_reelle_kg"],var_name="Type",value_name="Quantité (kg)");a.plotly_chart(px.bar(x,x="chaine_valeur",y="Quantité (kg)",color="Type",barmode="group",title="Production estimée et réelle"),width="stretch")
        y=summary.melt(id_vars="chaine_valeur",value_vars=["quantite_consommee_kg","quantite_vendue_kg","quantite_stockee_kg"],var_name="Utilisation",value_name="Quantité (kg)");b.plotly_chart(px.bar(y,x="chaine_valeur",y="Quantité (kg)",color="Utilisation",barmode="group",title="Utilisation de la production"),width="stretch")
        visible=view.drop(columns=["nom_code_menage"],errors="ignore");st.subheader("Détail du suivi");st.caption("Le code ménage est masqué dans l’aperçu.");st.dataframe(visible,width="stretch",hide_index=True)
        st.download_button("Télécharger le suivi filtré",visible.to_csv(index=False).encode("utf-8-sig"),"suivi_production_4101_filtre.csv","text/csv")

elif page=="Carte":
    title("Localisation des ménages suivis")
    if pdf.empty or not {"point_gps_latitude","point_gps_longitude"}.issubset(pdf.columns):empty("Coordonnées GPS indisponibles.")
    else:
        m=pdf.dropna(subset=["point_gps_latitude","point_gps_longitude"]);m=m[m.point_gps_latitude.between(-90,90)&m.point_gps_longitude.between(-180,180)]
        if m.empty:empty("Aucune coordonnée GPS valide.")
        else:st.metric("Points GPS valides",fmt(len(m)));st.map(m.rename(columns={"point_gps_latitude":"latitude","point_gps_longitude":"longitude"})[["latitude","longitude"]])

else:
    title("Qualité des données");datasets={"Bénéficiaires":bdf,"Distribution ménages":hdf,"Distribution groupements":gdf,"Suivi production":pdf};label=st.selectbox("Table",list(datasets));d=datasets[label]
    if d.empty:empty()
    else:
        for col,(lab,val) in zip(st.columns(4),[("Lignes",len(d)),("Colonnes",len(d.columns)),("Doublons",int(d.duplicated().sum())),("Cellules manquantes",int(d.isna().sum().sum()))]):col.metric(lab,fmt(val))
        q=pd.DataFrame({"Colonne":d.columns,"Type":d.dtypes.astype(str).values,"Valeurs manquantes":d.isna().sum().values,"% manquant":d.isna().mean().mul(100).round(1).values,"Valeurs distinctes":d.nunique(dropna=True).values}).sort_values("% manquant",ascending=False)
        st.plotly_chart(px.bar(q.head(20),x="Colonne",y="% manquant",color="% manquant",title="Valeurs manquantes"),width="stretch");st.dataframe(q,width="stretch",hide_index=True)

st.caption("Dashboard Projet 4101 | Résultats selon les filtres actifs.")