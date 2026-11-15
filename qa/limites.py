import httpx, time, json
c=httpx.Client(base_url="http://localhost:8100",timeout=120)
C={"departamento":"PE-CUS"}
casos=[
 ("calendario","inyección SQL en departamento",{"departamento":"PE-CUS' OR '1'='1"}),
 ("calendario","inyección SQL en bbox",{"bbox":"-72,-14,-71,-13); DROP TABLE x;--"}),
 ("calendario","bbox con NaN",{"bbox":"nan,nan,nan,nan"}),
 ("calendario","bbox con inf",{"bbox":"-inf,-14,inf,-13"}),
 ("calendario","bbox de área cero",{"bbox":"-72,-14,-72,-13"}),
 ("calendario","bbox diminuto",{"bbox":"-71.9700,-13.5200,-71.9699,-13.5199"}),
 ("calendario","bbox con espacios",{"bbox":" -72.2 , -13.4 , -71.8 , -13.1 "}),
 ("calendario","bbox con 5 números",{"bbox":"-72,-14,-71,-13,5"}),
 ("calendario","lat NaN",{"lat":"nan","lon":-72,"radio_km":10}),
 ("calendario","radio inf",{"lat":-13.5,"lon":-72,"radio_km":"inf"}),
 ("calendario","radio NaN",{"lat":-13.5,"lon":-72,"radio_km":"nan"}),
 ("calendario","departamento vacío",{"departamento":""}),
 ("calendario","departamento muy largo",{"departamento":"X"*5000}),
 ("calendario","departamento con tilde",{"departamento":"Cuscó"}),
 ("calendario","fecha 0000-01",{**C,"fecha_inicio":"0000-01","fecha_fin":"2001-01"}),
 ("calendario","fecha 9999-12",{**C,"fecha_inicio":"2020-01","fecha_fin":"9999-12"}),
 ("calendario","mes 00",{**C,"fecha_inicio":"2020-00","fecha_fin":"2020-05"}),
 ("calendario","mes de un dígito",{**C,"fecha_inicio":"2020-1","fecha_fin":"2020-5"}),
 ("calendario","fecha con espacio",{**C,"fecha_inicio":" 2020-01","fecha_fin":"2020-05"}),
 ("calendario","fecha ISO con hora",{**C,"fecha_inicio":"2020-01-01T00:00:00Z","fecha_fin":"2020-05"}),
 ("calendario","solo fecha_fin",{**C,"fecha_fin":"2001-03"}),
 ("calendario","fecha_fin antes de cobertura",{**C,"fecha_fin":"2000-06"}),
 ("anomalias","mes 2000-11 (primer mes, extrapolado)",{**C,"mes":"2000-11"}),
 ("anomalias","mes 2025-12 (último, día 31 incompleto)",{**C,"mes":"2025-12"}),
 ("anomalias","mes 2000-10 (justo antes)",{**C,"mes":"2000-10"}),
 ("anomalias","mes vacío",{**C,"mes":""}),
 ("anomalias","área chica, mes extrapolado",{"lat":-12.6,"lon":-72.6,"radio_km":5,"mes":"2001-08"}),
 ("hotspots.csv","rango de un mes sin focos en área chica",{"lat":-13.52,"lon":-71.97,"radio_km":2,"fecha_inicio":"2020-02","fecha_fin":"2020-02"}),
 ("hotspots.csv","fecha_inicio 1990 a 2001",{**C,"fecha_inicio":"1990-01","fecha_fin":"2001-01"}),
 ("focos.geojson","área chica sin focos en el mes",{"lat":-13.52,"lon":-71.97,"radio_km":2,"fecha_inicio":"2020-02","fecha_fin":"2020-02"}),
 ("focos.geojson","sin fechas",C),
 ("analitica/acumulado","anio texto",{**C,"anio":"abc"}),
 ("analitica/acumulado","anio 2000",{**C,"anio":2000}),
 ("analitica/recurrencia","limite -1",{**C,"limite":-1}),
 ("analitica/recurrencia","limite 20001",{**C,"limite":20001}),
 ("analitica/recurrencia","limite 0",{**C,"limite":0}),
 ("analitica/estacionalidad","área fuera de Cusco",{"bbox":"-77.2,-12.2,-76.8,-11.9"}),
 ("analitica/ranking","área en Cusco sin fuego",{"bbox":"-71.36,-13.82,-71.34,-13.80"}),
 ("resumen","área en Cusco sin fuego",{"bbox":"-71.36,-13.82,-71.34,-13.80"}),
 ("resumen","sin AOI",{}),
 ("analitica/nada","ruta que no existe",C),
 ("departamentos","lista de departamentos",{}),
 ("metadatos","metadatos",{}),
]
out=[]
for ep,desc,p in casos:
    t=time.time(); r=c.get(f"/api/{ep}",params=p); ms=round((time.time()-t)*1000)
    try: b=r.json(); det=b.get("detail") if isinstance(b,dict) else None; extra=b.get("errors") if isinstance(b,dict) else None
    except Exception: b=None; det=r.text[:150]; extra=None
    info=""
    if r.status_code==200 and isinstance(b,dict):
        if ep=="calendario": info=f"total={b.get('total_focos_armonizados')} rango={b.get('fecha_inicio')}..{b.get('fecha_fin')} aoi={b.get('aoi',{}).get('descripcion')} area={b.get('aoi',{}).get('area_km2')}"
        elif ep=="anomalias": info=f"valor={b.get('focos_armonizados')} med={b.get('mediana_hist')} anom={b.get('anomalia')} cat={b.get('categoria')} n_anios={b.get('n_anios_hist')} parcial={b.get('parcial')} notes={len(b.get('notes',[]))}"
        elif ep=="focos.geojson": info=f"features={len(b.get('features',[]))}"
        elif "analitica" in ep or ep=="resumen": info=(b.get('en_simple') or str([f['respuesta'] for f in b.get('frases',[])][:1]))[:200]
    elif r.status_code==200: info=f"filas={r.headers.get('x-row-count')} total={r.headers.get('x-total-eq-foco')} bytes={len(r.content)}"
    out.append((ep,desc,r.status_code,ms,det,extra,info))
    print(f"[{r.status_code}] {ms}ms {ep} · {desc}\n     {det or ''} {extra or ''} {info}")
# métodos y documentación
for m,u in [("POST","/api/calendario"),("GET","/docs"),("GET","/openapi.json"),("GET","/"),("GET","/no-existe"),("GET","/api/v1/calendar")]:
    r=c.request(m,u); print(f"[{r.status_code}] {m} {u} {r.headers.get('content-type')} {r.text[:80]!r}")
