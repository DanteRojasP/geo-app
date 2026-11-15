"""Pruebas de control en un servidor aparte (8006):
A) 2023 empezando el ▶ en julio (¿falla por el mes o por la posición en la secuencia?)
B) 2023 dejando el ▶ correr 2 vueltas (24 meses): estado estable.
"""
import json, time, sys
sys.path.insert(0, "/home/claude/qa")
from play_por_anio import correr_anio

out = {}
out["2023_desde_julio"] = correr_anio(8006, 2023, mes_inicio=7, meses=12)
time.sleep(35)
out["2023_dos_vueltas"] = correr_anio(8006, 2023, mes_inicio=1, meses=24)
json.dump(out, open("/home/claude/qa/play_controles.json", "w"), ensure_ascii=False, indent=1)
print("FIN")
