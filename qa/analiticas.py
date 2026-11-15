import httpx, json, statistics, random
c=httpx.Client(base_url="http://localhost:8100",timeout=120)
AOIS=[("Cusco",{"departamento":"PE-CUS"}),("bbox_norte",{"bbox":"-73.2,-12.2,-72.4,-11.4"}),("bbox_ciudad",{"bbox":"-72.2,-13.7,-71.8,-13.4"}),
      ("punto_chico",{"lat":-13.52,"lon":-71.97,"radio_km":3}),("bbox_poco_fuego",{"bbox":"-71.4,-14.3,-71.2,-14.1"})]
P=[]
def mal(a,m): P.append((a,m))
for nom,aoi in AOIS:
    cal=c.get("/api/calendario",params=aoi)
    if cal.status_code!=200: print(nom,"calendario",cal.status_code,cal.json().get("detail")); 
    else:
        cal=cal.json(); porAnio={}
        for x in cal["celdas"]:
            if not x["sin_dato"]: porAnio[x["anio"]]=porAnio.get(x["anio"],0)+x["focos_armonizados"]
        tot=cal["total_focos_armonizados"]
    for ep in ["resumen","analitica/estacionalidad","analitica/ranking","analitica/acumulado","analitica/altitud","analitica/recurrencia"]:
        r=c.get(f"/api/{ep}",params=aoi)
        if r.status_code!=200:
            print(f"{nom} {ep}: {r.status_code} {r.json().get('detail')}"); continue
        d=r.json()
        if ep.endswith("ranking"):
            for a in d["anios"]:
                if a["anio"] in porAnio and abs(a["total"]-porAnio[a["anio"]])>1: mal(nom,f"ranking {a['anio']} total {a['total']} ≠ calendario {porAnio[a['anio']]:.1f}")
            anos=[a["anio"] for a in d["anios"]]
            if 2000 in anos: mal(nom,f"ranking incluye 2000 (solo nov-dic): puesto {[a['puesto'] for a in d['anios'] if a['anio']==2000]}, total {[a['total'] for a in d['anios'] if a['anio']==2000]}")
            print(f"  {nom} ranking: {d['en_simple']}")
        if ep.endswith("altitud"):
            s=sum(b["focos_armonizados"] for b in d["bandas"]); 
            if abs(s-tot)>1: mal(nom,f"altitud suma {s:.1f} ≠ total {tot}")
            ps=sum(b["parte"] for b in d["bandas"])
            if abs(ps-1)>0.01: mal(nom,f"altitud partes suman {ps}")
            print(f"  {nom} altitud: {d['en_simple']}")
        if ep.endswith("acumulado"):
            y=d["anio"]; fin=d["curva"][-1]["acumulado"]
            if y in porAnio and abs(d["total"]-porAnio[y])>1: mal(nom,f"acumulado {y} total {d['total']} ≠ calendario {porAnio[y]:.1f}")
            if abs(fin-d["total"])>1: mal(nom,f"acumulado curva termina en {fin} ≠ total {d['total']}")
            print(f"  {nom} acumulado: {d['en_simple']}")
        if ep.endswith("estacionalidad"):
            print(f"  {nom} estacionalidad: {d['en_simple']}")
        if ep=="resumen":
            for f in d["frases"]: print(f"  {nom} resumen · {f['pregunta']} → {f['respuesta']}")
            print(f"  {nom} resumen notes: {d['notes']}")
        if ep.endswith("recurrencia"):
            s=sum(x["lugares"] for x in d["por_numero_de_anios"])
            if s!=d["lugares"]: mal(nom,f"recurrencia suma {s} ≠ lugares {d['lugares']}")
            print(f"  {nom} recurrencia: {d['en_simple']}")
# acumulado para cada año en Cusco
for y in range(1999,2027):
    r=c.get("/api/analitica/acumulado",params={"departamento":"PE-CUS","anio":y})
    if r.status_code!=200: print("acumulado",y,r.status_code,r.json().get("detail")); continue
    d=r.json()
    if y in (2000,2001,2002,2025,2026,2003,2012,2013): print("acumulado",y,"→",d["en_simple"], "| notes:",len(d["notes"]))
print("\nPROBLEMAS:"); [print(p) for p in P]
