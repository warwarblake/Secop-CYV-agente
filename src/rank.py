"""
Ranking layer.

The model receives a numbered list of candidates and returns only:
  - which index numbers made the top 5
  - a Spanish rationale for each
  - a risk flag

It never returns process IDs, values, URLs or dates. Those are looked up from
the original API record by index, so a hallucinated tender number is
structurally impossible.
"""

from __future__ import annotations

import json
import os
import re

import requests

from . import config

API_URL = "https://api.anthropic.com/v1/messages"
MODEL = "claude-sonnet-5"


def _summarize(row: dict, index: int) -> str:
    f = config.FIELDS
    price = row.get(f["base_price"]) or 0
    try:
        price_txt = f"{float(price):,.0f} COP"
    except (TypeError, ValueError):
        price_txt = str(price)

    desc = (row.get(f["description"]) or "")[:600]
    return (
        f"[{index}]\n"
        f"Entidad: {row.get(f['entity'], 'N/D')}\n"
        f"Ubicacion: {row.get(f['city'], 'N/D')}, {row.get(f['department'], 'N/D')}\n"
        f"Objeto: {row.get(f['title'], 'N/D')}\n"
        f"Descripcion: {desc}\n"
        f"Modalidad: {row.get(f['modality'], 'N/D')}\n"
        f"Valor base: {price_txt}\n"
        f"Cierre: {row.get(f['closes'], 'N/D')}\n"
    )


PROMPT = """Eres analista de licitaciones para una constructora colombiana.
Escribes para Claudia Duran, quien necesita decidir rapido si vale la pena
estudiar un proceso a fondo.

PERFIL DE LA EMPRESA:
{profile}

A continuacion hay {n} procesos de contratacion publica abiertos en la region
Caribe, obtenidos de SECOP II. Selecciona los {top_n} que mejor se ajustan.

Criterios de seleccion, en orden de importancia:
1. Coincidencia tecnica con las lineas de negocio de la empresa.
2. Cercania geografica. Barranquilla y el resto del Atlantico pesan mas que
   los demas departamentos; luego Cartagena y Santa Marta.
3. Valor dentro o cerca del rango historico de la empresa.
4. Plazo de cierre (presentacion de ofertas) que todavia permite preparar
   una oferta. Si el campo de cierre no aparece en el proceso, dilo en la
   alerta -- nunca inventes ni asumas una fecha.

PROCESOS:
{candidates}

Responde UNICAMENTE con JSON valido, sin texto adicional y sin bloques de
codigo. Formato exacto:

{{"seleccion": [
  {{"indice": 0,
    "resumen": "UNA o DOS frases en espanol claro explicando que se va a
                construir. Nada de jerga contractual. Como se lo explicarias
                a alguien en treinta segundos.",
    "encaje": "Una o dos frases sobre por que encaja con la experiencia
               de la empresa.",
    "experiencia_estimada": "En lenguaje sencillo, que experiencia
                probablemente exigira el pliego: tipo de obra similar,
                cuantos contratos anteriores, y que magnitud. Basate en el
                objeto, el valor y la modalidad. Si no tienes base suficiente
                para estimar, escribe exactamente: Requiere revisar el pliego.",
    "prioridad": "alta" | "media" | "baja",
    "alerta": "Un riesgo o advertencia en una frase, o cadena vacia."}}
]}}

REGLA CRITICA sobre "experiencia_estimada": es una ESTIMACION tuya, no un dato
publicado. Nunca cites cifras, porcentajes en SMMLV ni numeros de contratos
como si fueran textuales del pliego. Usa lenguaje de probabilidad
("probablemente exigira", "es tipico que pidan").

El campo "indice" debe ser el numero entre corchetes del proceso. Devuelve
exactamente {top_n} elementos, ordenados del mejor al menos bueno.
"""


def rank(candidates: list[dict]) -> list[dict]:
    """Return the top-N original API rows, each with model commentary attached."""
    if not candidates:
        return []

    api_key = os.environ["ANTHROPIC_API_KEY"]
    top_n = min(config.TOP_N, len(candidates))

    blocks = "\n".join(_summarize(row, i) for i, row in enumerate(candidates[:60]))
    prompt = PROMPT.format(
        profile=config.COMPANY_PROFILE,
        n=len(candidates[:60]),
        top_n=top_n,
        candidates=blocks,
    )

    resp = requests.post(
        API_URL,
        headers={
            "x-api-key": api_key,
            "anthropic-version": "2023-06-01",
            "content-type": "application/json",
        },
        json={
            "model": MODEL,
            "max_tokens": 2000,
            "messages": [{"role": "user", "content": prompt}],
        },
        timeout=180,
    )
    if resp.status_code != 200:
        print(f"Anthropic API returned {resp.status_code}. Response body:")
        print(resp.text[:2000])
    resp.raise_for_status()

    text = "".join(
        block.get("text", "")
        for block in resp.json().get("content", [])
        if block.get("type") == "text"
    )
    text = re.sub(r"^```(?:json)?|```$", "", text.strip(), flags=re.MULTILINE).strip()

    try:
        parsed = json.loads(text)
    except json.JSONDecodeError:
        # Fall back to keyword-hit ordering rather than sending nothing.
        return [
            {
                **row,
                "_resumen": "",
                "_encaje": "",
                "_experiencia": "Requiere revisar el pliego.",
                "_prioridad": "media",
                "_alerta": "",
            }
            for row in candidates[:top_n]
        ]

    selected = []
    for item in parsed.get("seleccion", [])[:top_n]:
        idx = item.get("indice")
        if not isinstance(idx, int) or not (0 <= idx < len(candidates)):
            continue
        row = dict(candidates[idx])
        row["_resumen"] = item.get("resumen", "")
        row["_encaje"] = item.get("encaje", "")
        row["_experiencia"] = item.get("experiencia_estimada", "")
        row["_prioridad"] = item.get("prioridad", "media")
        row["_alerta"] = item.get("alerta", "")
        selected.append(row)

    return selected
