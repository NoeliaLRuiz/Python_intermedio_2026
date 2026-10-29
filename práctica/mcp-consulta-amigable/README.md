# MCP de la Consulta Amigable del MEF

Servidor MCP hecho con FastMCP 4 que consulta el presupuesto y el gasto de las entidades públicas del Perú en la
[Consulta Amigable](https://apps5.mineco.gob.pe/transparencia/Navegador/default.aspx) del MEF: PIA, PIM,
certificación, compromiso, devengado, girado y avance %, desde 2012. Sigue la estructura del proyecto de la
Sesión 04 (herramientas, recurso, prompt, pruebas y evaluación), con la Consulta Amigable en lugar del BCRP.

| Archivo | Qué es |
|---|---|
| `server.py` | El servidor: 4 herramientas, 2 recursos y 2 prompts |
| `test_server.py` | El contrato: 9 pruebas con datos reales de 2025, un año cerrado |
| `preguntas.csv` | 10 preguntas con la cifra oficial, la tolerancia y la fuente en la web |
| `evaluar.py` | Le hace cada pregunta a Claude sin herramientas y con el MCP, y califica |
| `resultados.csv`, `resultados_sin_salida.csv` | Lo que dio `evaluar.py`, con y sin permiso para decir «no sé» |
| `informe.md`, `grafico.png` | El análisis de los resultados; `grafico.py` rehace la figura |
| `.mcp.json` | Los servidores `mef` y `fetch`, sin claves |

## Qué ofrece

| Pieza | Nombre | Para qué |
|---|---|---|
| Herramienta | `buscar_entidad` | Encontrar el código de una ejecutora, pliego o municipalidad por su nombre |
| Herramienta | `consulta_amigable` | Cualquier tabla del navegador: por sector, pliego, genérica, fuente, mes, etc. |
| Herramienta | `resumen` | Las cuentas de una entidad: avance, saldo por devengar, PIM contra PIA, mes pico y genéricas |
| Herramienta | `evolucion` | PIA, PIM, devengado y avance año por año, con la variación del devengado |
| Recurso | `mef://dimensiones` | Las 19 dimensiones que se pueden usar como desglose o filtro |
| Recurso | `mef://ejecutora/{codigo}` | Ficha de una ejecutora: nivel, sector, pliego y presupuesto del año |
| Prompt | `ejecucion_presupuestal` | Reporte del gasto de una entidad, con fuentes |
| Prompt | `comparar_entidades` | Tabla comparativa de varias entidades |

Cómo funciona: el navegador de la Consulta Amigable guarda cada consulta en la URL, con un número por dimensión
(`1` nivel, `2` sector, `3` pliego, `4` ejecutora, `24` genérica, `23` mes…). Por ejemplo,
`Navegar_7.aspx?_uhc=yes&0=&4=77&24=&y=2025&ap=ActProy` lista las genéricas de la ejecutora 77 en 2025. El
servidor arma esa URL, la pide sin iniciar sesión, lee la tabla y devuelve el link como fuente de cada cifra.

## Usarlo

Necesitan `uv`, Claude Code con su sesión iniciada e internet.

```bash
uv run pytest -q          # 8 passed; la primera vez crea el entorno
claude                    # en esta carpeta; acepten los servidores de .mcp.json
```

Dentro de Claude Code:

1. `/mcp`: `mef` y `fetch` conectados.
2. Una pregunta: *«¿Cuánto ha devengado este año la Municipalidad de Villa El Salvador y en qué genéricas va más atrasada?»*
3. Un recurso: `@mef:mef://ejecutora/77 ¿a qué pliego pertenece?`
4. Un prompt: `/mcp__mef__ejecucion_presupuestal Instituto Pedagógico Nacional de Monterrico`

Para medir si el MCP ayuda:

```bash
uv run evaluar.py                          # memoria contra mcp, con Haiku; escribe resultados.csv
uv run evaluar.py --modos memoria web mcp  # también contra la búsqueda web
uv run evaluar.py --sin-salida             # sin permiso para decir «no sé»; escribe resultados_sin_salida.csv
uv run grafico.py                          # rehace grafico.png
```

## Límites

- Hay datos de 2012 al año en curso, y se actualizan a diario: las cifras del año actual cambian de un día a otro.
- Los totales suman montos redondeados a soles y pueden diferir en unos soles de los de la web.
- Los nombres del MEF van en mayúsculas y abreviados («M. DE EDUCACION», «U.N.»): si una búsqueda no encuentra
  nada, conviene probar con menos palabras.
- Por mes o trimestre no hay PIA ni PIM, solo la ejecución.
