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
REQUIRE_MODALITY = ["licitacion publica", "menor cuantia"]
# "menor cuantia" matches "Seleccion Abreviada de Menor Cuantia" via substring.
# Deliberately does NOT match "Minima Cuantia", which is a smaller, different
# category -- "menor cuantia" and "minima cuantia" are distinct legal terms
# in Colombian procurement and are not interchangeable.
#
# Menor Cuantia is a noisier modality than Licitacion Publica -- it covers
# everything from small repairs to office supplies to catering. The
# REQUIRE_CONTRACT_TYPE = ["obra"] gate below and the keyword filter further
# down are what actually keep this clean; without both, Menor Cuantia would
# flood the results with irrelevant small purchases.
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

# Ignore anything below this base price (COP).
#
# Lowered from 1,500M to 500M for two reasons, both confirmed against CYV's
# real project history (Anexo_Obras_CYV_2026.pdf):
#   1. Seleccion Abreviada de Menor Cuantia has a legal ceiling around 1,000
#      SMMLV (roughly $1.4-1.6B COP as of 2025-2026) -- a 1,500M floor would
#      exclude nearly every Menor Cuantia process, making that modality
#      pointless to include.
#   2. CYV's actual track record includes real, completed projects as small
#      as ~$824M COP (erosion protection, Puerto Giraldo) and ~$952M COP
#      (vehicular bridge, Villa Carolina) -- a 1,500M floor would have
#      excluded contracts CYV has genuinely executed before.
MIN_BASE_PRICE_COP = 500_000_000

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
    # water, sewer, drainage -- CYV's largest confirmed line of business
    "alcantarillado", "acueducto", "arroyo", "canalizacion", "canalizar",
    "drenaje", "pluvial", "aguas lluvias", "colector", "box culvert",
    "boxculvert", "box coulvert", "ptar", "saneamiento", "obras hidraulicas",
    "planta de tratamiento", "estacion de bombeo", "red hidrosanitaria",
    "distrito de riego", "jaguey", "jagueyes",
    # public space, parks, urbanism
    "parque", "espacio publico", "urbanismo", "amoblamiento", "mobiliario urbano",
    "plaza", "malecon", "ciclorruta", "ciclovia", "senderos",
    # buildings and institutional
    "construccion", "edificacion", "adecuacion", "remodelacion", "restauracion",
    "ampliacion", "mejoramiento", "institucion educativa", "colegio",
    "sede", "escenario deportivo", "estadio", "coliseo", "polideportivo",
    # housing and social infrastructure -- confirmed via Edubar/Gobernacion projects
    "vivienda", "centro de vida", "adulto mayor", "poblacion vulnerable",
    "damnificado", "damnificados",
    # earthworks -- confirmed line of business
    "movimiento de tierra", "corte y relleno", "cargue y retiro", "pre-mineria",
    "mitigacion de riesgo",
    # general civil works
    "obra civil", "obras civiles", "infraestructura", "muro de contencion",
    "puente", "dragado", "proteccion costera", "control de erosion",
]

# Terms that almost always mean "not a construction contract for CYV".
# Especially important now that Menor Cuantia is in scope -- that modality
# covers far more non-construction procurement than Licitacion Publica does.
EXCLUDE_KEYWORDS = [
    "interventoria", "consultoria", "estudios y disenos", "supervision tecnica",
    "suministro de alimentos", "servicio de vigilancia", "poliza",
    "seguros", "arrendamiento de vehiculos", "papeleria", "aseo",
    "capacitacion", "transporte escolar", "dotacion de elementos",
    "compraventa", "adquisicion de", "prestacion de servicios profesionales",
]

# ---------------------------------------------------------------------------
# Named past projects -- SOURCE: Anexo_Obras_CYV_2026.pdf, provided directly
# by Claudia Duran. This replaced an earlier guessed list built from public
# search results; everything below is verified, not inferred.
#
# Grouped by category exactly as CYV's own document groups them, since the
# ranking model uses these category headers to judge fit. Each line is
# "Objeto -- Entidad, Ano, Valor". Keep in sync with COMPANY_PROFILE below.
# ---------------------------------------------------------------------------
PAST_PROJECTS = {
    "Edificaciones y Parques": [
        "Mejoramiento de vivienda, poblacion vulnerable, Barranquilla ETAPA III -- Edubar S.A., en ejecucion, $19.819.228.000",
        "Construccion y dotacion de Centros de Vida del Adulto Mayor (Campo de la Cruz, Juan de Acosta, Luruaco, Manati, Repelon, Soledad, Suan) -- Edubar S.A., en ejecucion, $25.457.781.106",
        "Construccion de la Galeria Comercial K7 -- Constructora Yacaman Vivero SAS, en proyecto, $17.000.000.000",
        "Intervencion integral edificios sede Bellas Artes, Universidad del Atlantico (reparaciones locativas, refuerzo estructural, restauracion, obra nueva, ampliacion, demolicion, reconstruccion) -- Universidad del Atlantico, 2025, $36.716.394.000",
        "Mejoramiento de vivienda, Barranquilla Modulo II -- Edubar S.A., 2023, $5.561.125.503",
        "Construccion/adecuacion/ampliacion Centros de Integracion Deportivo y Comunitario para la Paz, Tubara -- Gobernacion del Atlantico, 2019, $14.557.915.018",
        "Reconstruccion y/o adecuacion Estadio Romelio Martinez, Barranquilla (Juegos Centroamericanos y del Caribe 2018, incluye Patrimonio Arquitectonico) -- Alcaldia de Barranquilla, 2018, $79.982.097.310",
        "Adecuacion y/o remodelacion Estadio Metropolitano de Barranquilla (Juegos Centroamericanos y del Caribe 2018) -- Alcaldia de Barranquilla, 2018, $11.158.037.032",
        "Construccion Institucion Educativa Oriental, Santo Tomas -- Gobernacion del Atlantico, 2016, $13.054.533.589",
        "Construccion instituciones educativas Nuestra Senora de Pitalito (Polonuevo), Playa Mendoza (Tubara), San Antonio (Piojo) -- Gobernacion del Atlantico, 2016, $26.572.024.831",
        "Construccion y recuperacion Plaza de la Intendencia Fluvial / Plaza Grande del rio Magdalena (incluye Patrimonio Arquitectonico) -- Alcaldia de Barranquilla, 2014, $11.381.270.460",
        "Reposicion de aulas, bateria sanitaria, dotacion mobiliaria, IE Maria Mancilla Sanchez, Puerto Colombia -- Gobernacion del Atlantico, 2008, $955.765.541",
        "Construccion Parque Estadio de Atletismo, Cartagena D.T. -- FONADE, 2006, $18.833.806.974",
        "Terminacion/adecuacion y construccion de 2 aulas, Colegio Fossy Marco Maria, Aracataca (Magdalena) -- FONADE, 2005, $1.459.380.158",
        "Construccion Parque Cultural de Malambo -- Coopmunicipios, 2002, $1.135.903.339",
    ],
    "Obras Viales": [
        "Mejoramiento via principal barrio El Rodeo, Turbaco (Bolivar) -- Gobernacion de Bolivar, 2022, $8.148.613.442",
        "Mejoramiento/pavimentacion Via 40 (calles 85-110) y modernizacion alumbrado publico, Barranquilla -- Alcaldia de Barranquilla, 2020, $75.743.381.294",
        "Mejoramiento via Tubara-Guaymaral-Paluato -- Gobernacion del Atlantico, 2019, $33.573.133.900",
        "Pavimentacion concreto hidraulico, Barrios a la Obra Etapa IV, varias localidades Barranquilla -- Alcaldia de Barranquilla, 2017, $24.902.228.389",
        "Mejoramiento via Santa Lucia-Algodonal-Campo de la Cruz -- Gobernacion del Atlantico, 2017, $22.127.521.885",
        "Mantenimiento y pavimentacion via acceso aeropuerto de carga, Soledad -- Gobernacion del Atlantico, 2016, $9.687.339.172",
        "Mejoramiento via Las Compuertas-Puente Amarillo Etapa 1 -- Gobernacion del Atlantico, 2015, $3.702.904.122",
        "Mantenimiento/rehabilitacion via alterna Puerto Maritimo Santa Marta, Mamatoco-Terminal Maritimo (Magdalena) -- INVIAS, 2013, $19.231.105.528",
        "Construccion segunda calzada corredor universitario, vias 1/4/5/6 -- URVISA, 2010, $2.352.655.906",
        "Rehabilitacion via Sexta Entrada a Barranquilla, Etapa 2 -- Gobernacion del Atlantico, 2008, $4.036.144.304",
        "Construccion pavimento, paseo peatonal, ciclorruta, via perimetral Cienaga de la Virgen, Cartagena (etapa 1) -- FONADE, 2006, $22.013.175.568",
        "Construccion vias conectoras carreras 52/53, via perimetral Cienaga de la Virgen, Cartagena-Bolivar -- FONADE, 2006, $16.608.770.106",
    ],
    "Obras con Puentes y Boxculvert": [
        "Construccion puente vehicular No.3, Urbanizacion Villa Carolina II -- URVISA, 2007, $952.495.196",
        "Fase 1 construccion/adecuacion colector central de aguas lluvias y amoblamiento urbano, avenida circunvalar (calles 29-41), Monteria -- FONADE, 2005, $14.562.773.120",
    ],
    "Obras de Saneamiento Basico": [
        "Optimizacion conduccion y redes de acueducto, Usiacuri -- Gobernacion del Atlantico, 2024, $10.389.149.849",
        "Construccion redes de alcantarillado aguas residuales, Piojo Etapa 1 -- Gobernacion del Atlantico, 2022, $8.348.814.599",
        "Rehabilitacion sistema tratamiento aguas residuales, Repelon Primera etapa -- Gobernacion del Atlantico, 2021, $4.005.157.336",
        "Construccion sistema alcantarillado Urbanizacion Mundo Feliz y Barrio Petronitas, Galapa (segunda etapa) -- FINDETER, 2019, $10.753.608.132",
        "Optimizacion sistema alcantarillado urbano, Amaga -- FINDETER, 2018, $11.199.034.594",
        "Optimizacion/operacion redes acueducto circuitos El Tesoro/Bellavista/Concord/Veredas, Malambo -- Gobernacion del Atlantico, 2017, $19.256.926.535",
        "Sistema de Alcantarillado Barrio Los Angeles III, Barranquilla -- FINDETER, 2017, $3.171.404.918",
        "Construccion sistema tratamiento aguas residuales, cabecera municipal Polonuevo -- Gobernacion del Atlantico, 2015, $10.136.209.001",
        "Construccion plan maestro de alcantarillado Segunda etapa, Villa del Rosario -- FINDETER, 2015, $30.557.334.597",
        "Optimizacion/construccion planta tratamiento agua potable El Tesoro, Malambo -- Aguas de Malambo, 2014, $12.789.816.570",
        "Construccion primera etapa sistema alcantarillado Urbanizacion Mundo Feliz/Las Petronitas, Galapa -- FINDETER, 2014, $14.693.299.645",
        "Construccion sistema tratamiento aguas residuales, Baranoa -- Gobernacion del Atlantico, 2013, $11.079.332.095",
        "Rehabilitacion sistema acueducto Santa Lucia y Corregimiento Algodonal -- Gobernacion del Atlantico, 2012, $5.020.839.962",
        "Instalacion tuberia conduccion y redes acueducto, Urb. Mundo Feliz, Galapa -- Gobernacion del Atlantico, 2011, $4.333.877.947",
        "Construccion primera etapa alcantarillado sanitario margen izquierda Monteria, estacion de bombeo El Dorado -- Proactiva Aguas de Monteria S.A. ESP, 2009, $11.236.918.597",
        "Construccion redes de acueducto varios barrios, Sabanalarga (Atlantico) -- Gobernacion del Atlantico, 2008, $6.116.457.723",
        "Construccion infraestructura social, redes distribucion agua potable, Villas del Rey, Soledad -- Gobernacion del Atlantico, 2008, $3.073.755.344",
    ],
    "Obras de Urbanismo": [
        "Transformacion de Entornos Urbanos, Distrito de Barranquilla -- Edubar S.A., 2025, $27.115.757.077",
        "Construccion urbanismo prolongacion carrera 65, sector 1 -- Grupo Argos S.A, 2019, $3.089.466.999",
        "Construccion vias, andenes, redes hidrosanitarias y pluviales, urbanismo Portal Empresarial Norte -- SITUM, 2016, $3.455.423.596",
        "Construccion obra de urbanismo, Puerto Giraldo, Ponedera -- Fundacion Mario Santo Domingo, 2015, $841.363.296",
        "Construccion obras proyecto de vivienda poblacion damnificada/vulnerable, Tubara (FA) -- COMFENALCO, 2015, $1.825.043.409",
        "Obras civiles urbanismo y mitigacion de riesgo, El Puyal, Campo de la Cruz -- Fundacion Mario Santo Domingo, 2015, $1.359.179.680",
        "Construccion obras proyecto vivienda poblacion damnificada/vulnerable, Tubara -- Gobernacion del Atlantico, 2014, $3.113.054.102",
        "Construccion redes hidrosanitarias, vias y mobiliario urbano, Portal de Alejandria Etapa 2 Sector 1 -- URVISA, 2011, $2.393.859.039",
    ],
    "Obras Hidraulicas": [
        "Programa limpieza/mantenimiento/adecuacion de jagueyes, campesinos del Atlantico -- Gobernacion del Atlantico, 2017, $1.363.903.396",
        "Control de erosion y proteccion tuberia conduccion Acueducto Costero, zonas de deslizamiento -- Gobernacion del Atlantico, 2012, $8.791.356.200",
        "Proteccion contra erosion Planta de Tratamiento de Agua Potable, Puerto Giraldo -- Gobernacion del Atlantico, 2011, $824.557.606",
        "Mejoramiento/pavimentacion via Repelon-Villa Rosa-Santa Lucia-Carretera Oriental (reconstruccion via Dique Calamar-Santa Lucia) -- Gobernacion del Atlantico, 2011, $23.662.958.998",
        "Rehabilitacion/complementacion obras civiles distrito de riego, Repelon -- INCODER, 2010, $14.798.711.851",
        "Construccion laguna facultativa margen izquierda y colector matriz, barrio El Dorado, Monteria (Cordoba) -- Proactiva Aguas de Monteria, 2010, $6.950.447.107",
        "Rehabilitacion distrito de riego mediana escala, Santa Lucia -- Gobernacion del Atlantico, 2006, $988.779.414",
        "Rehabilitacion primera fase red de drenaje cano La Caimanera, Cordoba (grupo 03) -- FONADE, 2006, $4.341.375.125",
        "Canalizacion en concreto reforzado, cauce arroyo Calle 84, Barranquilla (via 40 hasta el rio Magdalena) -- DADIMA, 2003, $8.005.468.199",
    ],
    "Movimientos de Tierra": [
        "Construccion obras de pre-mineria, proyecto minero Las Palmeras, Puerto Libertador (Cordoba) -- GECELCA S.A. E.S.P., 2020, $17.828.097.621",
        "Obras de mitigacion urbanismo proyecto Villa Carolina, Repelon - Grupo V -- Gobernacion del Atlantico, 2018, $2.784.326.496",
    ],
}

# ---------------------------------------------------------------------------
# Company profile -- this is what the ranking model reads for overall fit.
# SOURCE: Anexo_Obras_CYV_2026.pdf, provided by Claudia Duran, plus public
# corporate info (founders, certifications). Edit freely as you learn more.
# ---------------------------------------------------------------------------
COMPANY_PROFILE = """
Constructora Yacaman Vivero S.A.S. (CYV Constructora)
Sede: Cra. 28 # 8-208 Lt 2A, Puerto Colombia, Atlantico, Colombia.
Fundada por el ingeniero civil William Yacaman y Rosa Maria Vivero.
Certificaciones: ISO 9001 (Bureau Veritas), OHSAS 18001, RUC.

LINEAS DE NEGOCIO CONFIRMADAS (ver PAST_PROJECTS para el listado completo,
organizado en estas mismas 7 categorias):
1. Edificaciones y Parques -- vivienda social, centros de vida del adulto
   mayor, edificios universitarios, escenarios deportivos (incluye obras
   para los Juegos Centroamericanos y del Caribe 2018), instituciones
   educativas, espacio publico/patrimonio arquitectonico.
2. Obras Viales -- pavimentacion, mejoramiento y rehabilitacion de vias
   urbanas e interurbanas, corredores universitarios, alumbrado publico
   asociado.
3. Obras con Puentes y Boxculvert -- puentes vehiculares, colectores de
   aguas lluvias con amoblamiento urbano.
4. Obras de Saneamiento Basico -- acueducto, alcantarillado (sanitario y
   pluvial), plantas de tratamiento de agua potable y de aguas residuales,
   estaciones de bombeo. Esta es la linea con MAS proyectos ejecutados.
5. Obras de Urbanismo -- vias, andenes, redes hidrosanitarias y pluviales,
   mobiliario urbano, vivienda para poblacion vulnerable/damnificada,
   mitigacion de riesgo.
6. Obras Hidraulicas -- control de erosion, distritos de riego, canalizacion
   de arroyos y canos, lagunas facultativas, proteccion de infraestructura
   de acueducto.
7. Movimientos de Tierra -- corte, cargue, relleno, obras de pre-mineria,
   obras de mitigacion asociadas a proyectos de urbanismo.

PATRON DE CONTRATACION
La mayoria de los proyectos son contratados directamente por CYV (no
siempre en union temporal). Entidades contratantes recurrentes: Gobernacion
del Atlantico (el cliente mas frecuente por lejos), Alcaldia de Barranquilla,
FONADE, FINDETER, Edubar S.A. Tambien ha trabajado para clientes privados
(Grupo Argos, URVISA, Fundacion Mario Santo Domingo, COMFENALCO).

RANGO DE VALOR REAL (valores actuales, segun Anexo_Obras_CYV_2026.pdf)
Desde aproximadamente $824.000.000 COP (proteccion de erosion, obra menor)
hasta $79.982.000.000 COP (Estadio Romelio Martinez, el proyecto mas grande
documentado). La gran mayoria de los proyectos caen entre $2.000 millones y
$30.000 millones COP -- ese es el rango donde CYV tiene mas experiencia
directa y repetida.

GEOGRAFIA CONFIRMADA
Fuertemente concentrada en el Departamento del Atlantico (Barranquilla,
Puerto Colombia, Soledad, Malambo, Galapa, Sabanalarga, Repelon, Piojo,
Polonuevo, Tubara, Baranoa, Usiacuri, Santa Lucia, Campo de la Cruz,
Ponedera). Tambien tiene obras confirmadas en Cartagena y Turbaco
(Bolivar), Monteria y Puerto Libertador (Cordoba), y Santa Marta y
Aracataca (Magdalena). Un numero pequeno de proyectos historicos en
Antioquia y Bogota existen pero estan fuera del foco geografico actual de
busqueda.
"""
