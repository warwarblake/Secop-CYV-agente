"""
Configuration for the CYV daily opportunity report.

Everything you are likely to need to tune lives in this file.
"""

# ---------------------------------------------------------------------------
# SECOP II open data (Socrata / datos.gov.co)
# ---------------------------------------------------------------------------
SOCRATA_DOMAIN = "https://www.datos.gov.co"

# SECOP II - Procesos de Contratacion
DATASET_ID = "p6dx-8zbt"

# Optional. Without a token you are rate limited but it still works.
# Get one free at https://evergreen.data.socrata.com/signup
# Set as the SOCRATA_APP_TOKEN environment variable.

# ---------------------------------------------------------------------------
# FIELD MAPPING
#
# IMPORTANT: run `python main.py --inspect` once before your first real run.
# It prints the live column names for the dataset. If any of these are wrong,
# fix them here and nowhere else -- the rest of the code reads through this map.
# ---------------------------------------------------------------------------
FIELDS = {
    "process_id":   "id_del_proceso",
    "reference":    "referencia_del_proceso",
    "entity":       "entidad",
    "department":   "departamento_entidad",
    "city":         "ciudad_entidad",
    "title":        "nombre_del_procedimiento",
    "description":  "descripci_n_del_procedimiento",
    "phase":        "fase",
    "status":       "estado_del_procedimiento",
    "modality":     "modalidad_de_contratacion",
    "base_price":   "precio_base",
    "published":    "fecha_de_publicacion_del",
    "closes":       "fecha_de_recepcion_de",
    "duration":     "duracion",
    "duration_unit": "unidad_de_duracion",
    # Bid-submission deadline. Confirmed against live SECOP II metadata:
    # fieldName "fecha_de_recepcion_de" = human label
    # "Fecha de Recepcion de Respuestas" (date offers/responses are due).
    "closes":       "fecha_de_recepcion_de",
    "unspsc":       "codigo_principal_de_categoria",
    "contract_type": "tipo_de_contrato",
    "url":          "urlproceso",
}

# If True and "closes" is mapped, any process whose deadline has already
# passed is dropped before ranking -- never send an opportunity Claudia
# can no longer act on. Has no effect while "closes" is None above.
EXCLUDE_OVERDUE = True

# Claudia Duran is the recipient at CYV. Her stated requirements, in order:
#   1. exact link to the process
#   2. short description
#   3. experience required, in plain language
#   4. price
# Items 1, 2 and 4 come straight from the API. Item 3 is NOT published in the
# open dataset -- it lives in the pliego de condiciones PDF. The model produces
# a clearly-labelled ESTIMATE and the email always links to the source document.

# ---------------------------------------------------------------------------
# Modality and contract type
#
# You asked specifically for "Licitacion Publica (obra publica)". These are
# two separate fields in SECOP II:
#   - modalidad_de_contratacion: the bidding procedure (Licitacion Publica,
#     Seleccion Abreviada, Minima Cuantia, Concurso de Meritos, Contratacion
#     Directa, etc.)
#   - tipo_de_contrato: what's being bought (Obra, Consultoria, Suministro,
#     Prestacion de servicios, etc.)
#
# A process must match BOTH to pass. This is what actually excludes
# consultorias and interventorias that happen to mention "vias" or
# "alcantarillado" in their description -- the keyword filter alone couldn't
# tell those apart from a real construction contract.
#
# Matching is accent/case-insensitive substring matching (see secop.normalize).
# ---------------------------------------------------------------------------
REQUIRE_MODALITY = ["licitacion publica"]
REQUIRE_CONTRACT_TYPE = ["obra"]


#
# These are compared using accent-insensitive, case-insensitive matching,
# so "Atlantico", "Atlántico" and "ATLÁNTICO" all match. Do not add accents
# here -- normalisation strips them from both sides.
# ---------------------------------------------------------------------------
TARGET_DEPARTMENTS = [
    "atlantico",
    "bolivar",
    "magdalena",
    "sucre",
    "cordoba",
    "cesar",
]

# ---------------------------------------------------------------------------
# Hard filters
# ---------------------------------------------------------------------------

# Ignore anything below this base price (COP). CYV's confirmed track record
# runs 15,000M-138,000M, but obra publica in these six departments includes
# plenty of smaller viable projects (single-block road repairs, one-park
# rehabilitations, small institutional buildings) that a firm CYV's size can
# take on alone, without needing a union temporal. Lowered from 5,000M to
# 1,500M to surface those too. Raise this back up if the daily list starts
# feeling too long or too small to be worth CYV's time.
MIN_BASE_PRICE_COP = 1_500_000_000

# How many days back to look for newly published processes.
LOOKBACK_DAYS = 30

# Max processes pulled from the API per run before local filtering.
API_PAGE_LIMIT = 5000

# How many opportunities to put in the email.
TOP_N = 5

# ---------------------------------------------------------------------------
# Keyword pre-filter
#
# A process must hit at least one of these in its title or description to be
# passed to the ranking model. This is a cheap, deterministic first pass --
# it keeps token costs down and stops unrelated procurement (IT, catering,
# consultancy) from ever reaching the model.
# ---------------------------------------------------------------------------
RELEVANT_KEYWORDS = [
    # roads
    "via", "vial", "vias", "pavimento", "pavimentacion", "repavimentacion",
    "carretera", "calzada", "andenes", "bordillo", "placa huella",
    # water, sewer, drainage -- CYV's historic core
    "alcantarillado", "acueducto", "arroyo", "canalizacion", "canalizar",
    "drenaje", "pluvial", "aguas lluvias", "colector", "box culvert",
    "ptar", "saneamiento", "obras hidraulicas",
    # public space, parks, urbanism
    "parque", "espacio publico", "urbanismo", "amoblamiento", "mobiliario urbano",
    "plaza", "malecon", "ciclorruta", "ciclovia", "senderos",
    # buildings and institutional
    "construccion", "edificacion", "adecuacion", "remodelacion", "restauracion",
    "ampliacion", "mejoramiento", "institucion educativa", "colegio",
    "sede", "escenario deportivo", "estadio", "coliseo", "polideportivo",
    # general civil works
    "obra civil", "obras civiles", "infraestructura", "muro de contencion",
    "puente", "box coulvert", "dragado", "proteccion costera",
]

# Terms that almost always mean "not a construction contract for CYV".
EXCLUDE_KEYWORDS = [
    "interventoria", "consultoria", "estudios y disenos", "supervision tecnica",
    "suministro de alimentos", "servicio de vigilancia", "poliza",
    "seguros", "arrendamiento de vehiculos", "papeleria",
]

# ---------------------------------------------------------------------------
# Company profile -- this is what the ranking model reads.
# Built from CYV's public track record. Edit freely as you learn more.
# ---------------------------------------------------------------------------
COMPANY_PROFILE = """
Constructora Yacaman Vivero S.A.S. (CYV Constructora)
Sede: Barranquilla, Atlantico, Colombia.
Fundada por el ingeniero civil William Yacaman y Rosa Maria Vivero.
Certificaciones: ISO 9001 (Bureau Veritas), OHSAS 18001, RUC.

LINEAS DE NEGOCIO PRINCIPALES
- Obras hidraulicas urbanas: canalizacion de arroyos, colectores de aguas
  lluvias, alcantarillado y acueducto. Esta es su fortaleza historica
  (canalizacion del arroyo de la calle 84 en Barranquilla; colector central
  de aguas lluvias en Monteria).
- Infraestructura vial urbana: rehabilitacion y construccion de vias en
  barrios, pavimentacion, obras de movilidad.
- Espacio publico y urbanismo: parques, plazas, amoblamiento urbano
  (Plaza de la Intendencia Fluvial, Barranquilla).
- Escenarios deportivos: Parque Estadio de Atletismo, Cartagena.
- Edificaciones institucionales y educativas: sedes universitarias, colegios.
- Restauracion patrimonial (proyecto Bellas Artes, Barranquilla).
- Desarrollo inmobiliario propio (proyecto K7 Galeria Comercial).

PATRON DE CONTRATACION
Casi siempre se presenta en union temporal o consorcio, tomando una
participacion del 40% al 50%. Socios recurrentes: Solutect Ingenieria,
Constructora K7, Conyca Soluciones, A.E. Ingenieros Civiles. Por lo tanto,
un proceso que exige una capacidad financiera muy alta NO debe descartarse
automaticamente: pueden asociarse.

RANGO DE VALOR OBSERVADO
Procesos entre 15.000 millones y 138.000 millones de COP.
El punto dulce parece estar entre 18.000 y 50.000 millones.

GEOGRAFIA
Atlantico (Barranquilla, Puerto Colombia, Sabanalarga), Bolivar (Cartagena),
Cordoba (Monteria), y region Caribe en general.
"""
