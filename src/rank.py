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

Para cada proceso seleccionado, DEBES hacer dos cosas sin excepcion:

PASO 1 - ENCAJE: Identifica cual LINEA DE NEGOCIO PRINCIPAL del perfil coincide
con el proceso. Por ejemplo: "infraestructura vial urbana", "obras hidraulicas
urbanas", "espacio publico y urbanismo", "escenarios deportivos", "edificaciones
institucionales", "restauracion patrimonial". NUNCA escribas una respuesta generica.
Nombra la linea especifica o no incluyas el proceso en la seleccion.

PASO 2 - PROYECTOS RELACIONADOS: Para CADA proceso seleccionado, revisa la lista
de proyectos anteriores de CYV en el perfil y encuentra los que coincidan en tipo
de obra. Por ejemplo, si el proceso es sobre pavimentacion/vias, busca "rehabilitacion
y construccion de vias". Si es hidraulica, busca "canalizacion del arroyo" o "colector
central de aguas lluvias". Nombra el proyecto concreto y di POR QUE coincide
(tipo de obra similar, magnitud parecida, region similar). Si no encuentras
coincidencia clara despues de revisar TODO el perfil, escribe: "Sin antecedente
directo comparable en el perfil actual."

Criterios de seleccion (en orden):
1. Coincidencia tecnica con una LINEA DE NEGOCIO PRINCIPAL (no negociable).
2. Ubicacion geografica (Atlantico > otros).
3. Valor dentro del rango historico de CYV.
4. Plazo de cierre realista para preparar oferta.

PROCESOS:
{candidates}

Responde UNICAMENTE con JSON valido, sin texto adicional. Formato:

{{"seleccion": [
  {{"indice": 0,
    "resumen": "UNA o DOS frases explicando que se va a construir. Lenguaje claro.",
    "encaje": "Una o dos frases nombrando LA LINEA DE NEGOCIO ESPECIFICA con la que
               coincide (ej: 'Infraestructura vial urbana: pavimentacion y
               rehabilitacion de vias en barrios.'). Esto NO puede ser generico.",
    "proyectos_relacionados": "El nombre de uno o mas proyectos de CYV del perfil
                que sean similares, con UNA frase explicando por que (tipo de obra,
                region, magnitud). Ej: 'Rehabilitacion y construccion de vias en
                barrios (proyecto similar en valor y tipo de obra a nivel local).'
                O si no hay coincidencia clara: 'Sin antecedente directo comparable
                en el perfil actual.'",
    "experiencia_estimada": "Que experiencia exigira probablemente el pliego (obra
                similar, numero de contratos, magnitud). Lenguaje de probabilidad.",
    "prioridad": "alta" | "media" | "baja",
    "alerta": "Riesgo o advertencia en una frase, o vacio."}}
]}}

REGLAS CRITICAS:
- "encaje" DEBE nombrar la linea de negocio especifica. Prohibido generico.
- "proyectos_relacionados" DEBE tener contenido -- o un proyecto del perfil, o
  la frase 'Sin antecedente directo comparable en el perfil actual.'
- Devuelve maximo {top_n} elementos. Prefiere calidad sobre cantidad.
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
                "_proyectos_relacionados": "",
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
        row["_proyectos_relacionados"] = item.get("proyectos_relacionados", "")
        row["_experiencia"] = item.get("experiencia_estimada", "")
        row["_prioridad"] = item.get("prioridad", "media")
        row["_alerta"] = item.get("alerta", "")
        selected.append(row)

    return selected
