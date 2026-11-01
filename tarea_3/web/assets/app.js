// Dashboard «Menos víctimas, más violencia»: lee los datos de data/ y dibuja los gráficos con Plotly.

const INDICADORES = {
  tasa_homicidios: { nombre: "Homicidios por 100 mil habitantes", corto: "Homicidios por 100 mil hab.", dec: 1 },
  victimizacion: { nombre: "% de personas víctimas de algún delito", corto: "Víctimas de algún delito", dec: 1, pct: true, azul: true },
  tasa_extorsiones: { nombre: "Denuncias de extorsión por 100 mil habitantes", corto: "Extorsiones por 100 mil hab.", dec: 1 },
  victimas_arma_fuego: { nombre: "% de víctimas atacadas con arma de fuego", corto: "Víctimas con arma de fuego", dec: 1, pct: true },
  tasa_secuestros: { nombre: "Denuncias de secuestro por 100 mil habitantes", corto: "Secuestros por 100 mil hab.", dec: 1 },
  feminicidios: { nombre: "Feminicidios (número de casos)", corto: "Feminicidios", dec: 0 },
};
const KPIS = ["victimizacion", "tasa_homicidios", "tasa_extorsiones", "victimas_arma_fuego"];
const PERU = 0;
// Escalas de un solo tono, de oscuro (poco) a brillante (mucho): naranja para la violencia y celeste para las víctimas
const RAMPA_NARANJA = [[0, "#22324d"], [0.35, "#5e3f45"], [0.7, "#b85a3d"], [1, "#ff7a45"]];
const RAMPA_AZUL = [[0, "#22324d"], [0.5, "#3c69a8"], [1, "#8cc0ff"]];
const BORDE_MAPA = "#0b1424";
const CONFIG = { responsive: true, displayModeBar: false };
const TRANSICION = { duration: 500, easing: "cubic-in-out" };
const SIN_MOVIMIENTO = matchMedia("(prefers-reduced-motion: reduce)").matches;

const estado = { region: PERU, indicador: "tasa_homicidios", anio: 2024, modalidad: "Extorsión", anioDen: 2025 };
let datos, mapaRegiones, mapaLima, porClave, aniosCon, reproduccion = null;
const kpiAnterior = {};

// ---------- utilidades ----------
const color = (variable) => getComputedStyle(document.documentElement).getPropertyValue(variable).trim();
const $ = (id) => document.getElementById(id);
const colorDe = (ind) => (INDICADORES[ind].azul ? color("--serie-1") : color("--serie-2"));
const rampaDe = (ind) => (INDICADORES[ind].azul ? RAMPA_AZUL : RAMPA_NARANJA);

function formato(x, dec = 1) {
  // Coma decimal y espacio para los miles (solo desde 10 000), como recomienda la RAE
  if (x === null || x === undefined || Number.isNaN(x)) return "s. d.";
  let [entero, decimales] = Math.abs(x).toFixed(dec).split(".");
  if (entero.length > 4) entero = entero.replace(/\B(?=(\d{3})+(?!\d))/g, " ");
  return (x < 0 ? "−" : "") + entero + (decimales ? "," + decimales : "");
}
const conUnidad = (ind, x) => formato(x, INDICADORES[ind].dec) + (INDICADORES[ind].pct ? " %" : "");
const nombreRegion = (codigo) => (codigo === PERU ? "Perú" : datos.regiones[codigo]);
const valor = (codigo, anio, ind) => porClave.get(`${codigo}-${anio}`)?.[ind] ?? null;

function anioUsado(ind, anio) {
  // Si el indicador no tiene datos en ese año, se usa el año más cercano anterior (o el primero)
  const anios = aniosCon[ind];
  if (anios.includes(anio)) return anio;
  const previos = anios.filter((a) => a < anio);
  return previos.length ? Math.max(...previos) : Math.min(...anios);
}

function sentidoHorario(geojson) {
  // Plotly dibuja los mapas con d3, que espera el borde exterior de cada polígono en sentido horario
  // (y los huecos al revés). Los GeoJSON hechos con geopandas vienen al contrario: sin esto, el mapa sale vacío.
  const area = (anillo) => anillo.reduce((s, [x1, y1], i) => {
    const [x2, y2] = anillo[(i + 1) % anillo.length];
    return s + (x2 - x1) * (y2 + y1);
  }, 0);
  const orientar = (poligono) => poligono.map((anillo, i) => ((i === 0) === (area(anillo) > 0) ? anillo : [...anillo].reverse()));
  for (const { geometry: g } of geojson.features) {
    if (!g) continue;
    if (g.type === "Polygon") g.coordinates = orientar(g.coordinates);
    if (g.type === "MultiPolygon") g.coordinates = g.coordinates.map(orientar);
  }
  return geojson;
}

const MESES = ["enero", "febrero", "marzo", "abril", "mayo", "junio", "julio", "agosto", "setiembre", "octubre", "noviembre", "diciembre"];

function baseLayout(extra = {}) {
  return {
    paper_bgcolor: "rgba(0,0,0,0)", plot_bgcolor: "rgba(0,0,0,0)", separators: ", ",
    font: { family: 'system-ui, -apple-system, "Segoe UI", sans-serif', size: 12, color: color("--texto-2") },
    hoverlabel: { bgcolor: "#101b30", bordercolor: color("--borde"), font: { color: color("--texto") } },
    margin: { l: 48, r: 16, t: 8, b: 36 },
    ...extra,
  };
}
const eje = (extra = {}) => ({ gridcolor: color("--linea"), linecolor: color("--linea"), zeroline: false,
                               tickfont: { color: color("--texto-suave") }, ...extra });

// ---------- filtros ----------
function llenarSelect(select, opciones, elegido) {
  select.replaceChildren(...opciones.map(([valorOpcion, texto]) => {
    const op = document.createElement("option");
    op.value = valorOpcion;
    op.textContent = texto;
    op.selected = String(valorOpcion) === String(elegido);
    return op;
  }));
}

function prepararFiltros() {
  const regiones = Object.entries(datos.regiones).sort((a, b) => a[1].localeCompare(b[1], "es"));
  llenarSelect($("filtro-region"), [[PERU, "Perú (todo el país)"], ...regiones], estado.region);
  llenarSelect($("filtro-indicador"), Object.entries(INDICADORES).map(([k, v]) => [k, v.nombre]), estado.indicador);
  const anios = [...new Set(datos.panel.map((f) => f.anio))].sort((a, b) => b - a);
  llenarSelect($("filtro-anio"), anios.map((a) => [a, a]), estado.anio);
  const modalidades = [...new Set(datos.denuncias_mensual.map((f) => f.modalidad))].sort((a, b) => a.localeCompare(b, "es"));
  llenarSelect($("filtro-modalidad"), modalidades.map((m) => [m, m]), estado.modalidad);
  const aniosDen = [...new Set(datos.denuncias_lima.map((f) => f.anio))].sort((a, b) => b - a);
  llenarSelect($("filtro-anio-denuncias"), aniosDen.map((a) => [a, a]), estado.anioDen);

  // Botón para recorrer los años automáticamente (se crea aquí, junto al filtro de año)
  const boton = document.createElement("button");
  boton.type = "button";
  boton.id = "boton-reproducir";
  boton.className = "boton-reproducir";
  boton.textContent = "▶ Reproducir años";
  $("filtro-anio").closest("label").after(boton);

  $("filtro-region").addEventListener("change", (e) => { estado.region = Number(e.target.value); dibujarGenerales(); });
  $("filtro-indicador").addEventListener("change", (e) => { estado.indicador = e.target.value; dibujarGenerales(); });
  $("filtro-anio").addEventListener("change", (e) => { detener(); estado.anio = Number(e.target.value); dibujarGenerales(); });
  $("filtro-modalidad").addEventListener("change", (e) => { estado.modalidad = e.target.value; dibujarDenuncias(); });
  $("filtro-anio-denuncias").addEventListener("change", (e) => { estado.anioDen = Number(e.target.value); dibujarDenuncias(); });
  $("boton-descargar").addEventListener("click", descargarCSV);
  boton.addEventListener("click", () => (reproduccion ? detener() : reproducir()));
}

// ---------- reproducir los años ----------
function reproducir() {
  const anios = aniosCon[estado.indicador];
  let k = 0;
  const paso = () => {
    estado.anio = anios[k];
    $("filtro-anio").value = estado.anio;
    dibujarGenerales();
    k += 1;
    if (k >= anios.length) detener();
  };
  $("boton-reproducir").textContent = "⏸ Pausar";
  $("boton-reproducir").classList.add("activo");
  paso();
  reproduccion = setInterval(paso, 1100);
}

function detener() {
  clearInterval(reproduccion);
  reproduccion = null;
  const boton = $("boton-reproducir");
  if (boton) {
    boton.textContent = "▶ Reproducir años";
    boton.classList.remove("activo");
  }
}

// ---------- KPIs ----------
function contar(elemento, ind, desde, hasta) {
  // El número «cuenta» desde el valor anterior hasta el nuevo en 0,7 s
  if (SIN_MOVIMIENTO || desde === null || hasta === null || desde === hasta) {
    elemento.textContent = conUnidad(ind, hasta);
    return;
  }
  const inicio = performance.now();
  const cuadro = (ahora) => {
    const p = Math.min(1, (ahora - inicio) / 700);
    const suave = 1 - (1 - p) ** 3;
    elemento.textContent = conUnidad(ind, desde + (hasta - desde) * suave);
    if (p < 1) requestAnimationFrame(cuadro);
  };
  requestAnimationFrame(cuadro);
}

function dibujarKpis() {
  const tarjetas = KPIS.map((ind) => {
    const a = anioUsado(ind, estado.anio);
    const v = valor(estado.region, a, ind);
    const primero = Math.min(...aniosCon[ind]);
    const antes = valor(estado.region, primero, ind);
    let puesto = "Total del país";
    if (estado.region !== PERU) {
      const orden = Object.keys(datos.regiones).map(Number)
        .map((c) => valor(c, a, ind)).filter((x) => x !== null).sort((x, y) => y - x);
      puesto = `Puesto ${orden.indexOf(v) + 1} de ${orden.length} (1 = el más alto)`;
    }
    const tarjeta = document.createElement("article");
    tarjeta.className = "kpi";
    tarjeta.style.setProperty("--color-kpi", colorDe(ind));
    const partes = [
      ["etiqueta", `${INDICADORES[ind].corto} · ${a}`],
      ["valor", ""],
      ["detalle", `En ${primero}: ${conUnidad(ind, antes)}`],
      ["detalle", puesto],
    ];
    for (const [clase, texto] of partes) {
      const p = document.createElement("p");
      p.className = clase;
      p.textContent = texto;
      tarjeta.append(p);
    }
    contar(tarjeta.querySelector(".valor"), ind, kpiAnterior[ind] ?? 0, v);
    kpiAnterior[ind] = v;
    return tarjeta;
  });
  $("kpis").replaceChildren(...tarjetas);
}

// ---------- mapa y ranking ----------
function filasRanking(ind, a) {
  return Object.keys(datos.regiones).map(Number)
    .map((c) => ({ codigo: c, region: datos.regiones[c], valor: valor(c, a, ind) }))
    .filter((f) => f.valor !== null)
    .sort((x, y) => y.valor - x.valor)
    .map((f, i) => ({ ...f, puesto: i + 1 }));
}

function dibujarMapa(ind, a, filas) {
  $("titulo-mapa").textContent = `${INDICADORES[ind].nombre}, ${a}`;
  const trazos = [{
    type: "choropleth", geojson: mapaRegiones, featureidkey: "properties.codigo",
    locations: filas.map((f) => f.codigo), z: filas.map((f) => f.valor), text: filas.map((f) => f.region),
    colorscale: rampaDe(ind), marker: { line: { color: BORDE_MAPA, width: 1 } },
    colorbar: { thickness: 12, len: 0.7, outlinewidth: 0, tickfont: { color: color("--texto-suave") } },
    hovertemplate: `<b>%{z:,.${INDICADORES[ind].dec}f}${INDICADORES[ind].pct ? " %" : ""}</b><br>%{text}<extra></extra>`,
  }];
  if (estado.region !== PERU) {      // contorno blanco en la región seleccionada
    trazos.push({
      type: "choropleth", geojson: mapaRegiones, featureidkey: "properties.codigo",
      locations: [estado.region], z: [1], showscale: false, hoverinfo: "skip",
      colorscale: [[0, "rgba(0,0,0,0)"], [1, "rgba(0,0,0,0)"]],
      marker: { line: { color: "#ffffff", width: 3 } },
    });
  }
  Plotly.react("grafico-mapa", trazos, baseLayout({
    margin: { l: 0, r: 0, t: 0, b: 0 },
    geo: { fitbounds: "locations", visible: false, bgcolor: "rgba(0,0,0,0)", projection: { type: "mercator" } },
  }), CONFIG);
}

function dibujarRanking(ind, a, filas) {
  $("titulo-ranking").textContent = `Ranking de las 26 regiones, ${a}`;
  const orden = [...filas].reverse();      // la más alta arriba
  const nacional = valor(PERU, a, ind);
  const shapes = nacional === null ? [] : [{ type: "line", xref: "x", yref: "paper", x0: nacional, x1: nacional, y0: 0, y1: 1,
                                             line: { color: color("--texto-suave"), width: 1.5, dash: "dash" } }];
  const annotations = nacional === null ? [] : [{ xref: "x", yref: "paper", x: nacional, y: 1, yanchor: "bottom",
    text: `Perú: ${conUnidad(ind, nacional)}`, showarrow: false, font: { size: 11, color: color("--texto-2") } }];
  Plotly.react("grafico-ranking", [{
    type: "bar", orientation: "h", y: orden.map((f) => f.region), x: orden.map((f) => f.valor),
    marker: { color: orden.map((f) => (f.codigo === estado.region ? "#ffffff" : colorDe(ind))) },
    hovertemplate: `<b>%{x:,.${INDICADORES[ind].dec}f}${INDICADORES[ind].pct ? " %" : ""}</b><br>%{y}<extra></extra>`,
  }], baseLayout({
    margin: { l: 130, r: 16, t: 20, b: 30 }, bargap: 0.25, barcornerradius: 3, shapes, annotations,
    transition: SIN_MOVIMIENTO ? undefined : TRANSICION,
    xaxis: eje({ rangemode: "tozero" }), yaxis: eje({ gridcolor: "rgba(0,0,0,0)", tickfont: { size: 11, color: color("--texto-2") } }),
  }), CONFIG);

  // La misma información como tabla (para quien no puede ver el gráfico)
  const tabla = document.createElement("table");
  const encabezado = tabla.createTHead().insertRow();
  for (const [texto, clase] of [["Puesto", "num"], ["Región", ""], [INDICADORES[ind].corto, "num"]]) {
    const th = document.createElement("th");
    th.textContent = texto;
    th.className = clase;
    encabezado.append(th);
  }
  const cuerpo = tabla.createTBody();
  for (const f of filas) {
    const fila = cuerpo.insertRow();
    for (const [texto, clase] of [[f.puesto, "num"], [f.region, ""], [conUnidad(ind, f.valor), "num"]]) {
      const td = fila.insertCell();
      td.textContent = texto;
      td.className = clase;
    }
  }
  $("tabla-ranking").replaceChildren(tabla);
}

function descargarCSV() {
  const ind = estado.indicador;
  const a = anioUsado(ind, estado.anio);
  const lineas = [["puesto", "region", "anio", ind].join(",")];
  for (const f of filasRanking(ind, a)) lineas.push([f.puesto, `"${f.region}"`, a, f.valor].join(","));
  // "\ufeff" al inicio hace que Excel reconozca las tildes
  const archivo = new Blob(["\ufeff" + lineas.join("\n")], { type: "text/csv;charset=utf-8" });
  const enlace = document.createElement("a");
  enlace.href = URL.createObjectURL(archivo);
  enlace.download = `${ind}_${a}.csv`;
  enlace.click();
  URL.revokeObjectURL(enlace.href);
}

// ---------- evolución (cuatro gráficos pequeños) ----------
function dibujarEvolucion() {
  $("titulo-evolucion").textContent = nombreRegion(estado.region);
  for (const ind of KPIS) {
    const anios = aniosCon[ind];
    const serie = (codigo) => anios.map((a) => valor(codigo, a, ind));
    const trazos = [];
    if (estado.region !== PERU) {
      trazos.push({ type: "scatter", mode: "lines", name: "Perú", x: anios, y: serie(PERU),
                    line: { color: color("--texto-suave"), width: 2, dash: "dash" },
                    hovertemplate: `<b>%{y:,.1f}</b> Perú<extra></extra>` });
    }
    trazos.push({ type: "scatter", mode: "lines+markers", name: nombreRegion(estado.region), x: anios, y: serie(estado.region),
                  line: { color: colorDe(ind), width: 3, shape: "spline", smoothing: 0.4 }, marker: { size: 6 },
                  fill: "tozeroy", fillcolor: INDICADORES[ind].azul ? "rgba(94,161,240,0.15)" : "rgba(255,122,69,0.15)",
                  hovertemplate: `<b>%{y:,.1f}</b> ${nombreRegion(estado.region)}<extra></extra>` });
    Plotly.react(`ev-${ind}`, trazos, baseLayout({
      showlegend: false, hovermode: "x unified", margin: { l: 40, r: 10, t: 6, b: 28 },
      transition: SIN_MOVIMIENTO ? undefined : TRANSICION,
      xaxis: eje({ dtick: 2, showspikes: true, spikemode: "across", spikethickness: 1, spikecolor: color("--texto-suave") }),
      yaxis: eje({ rangemode: "tozero" }),
    }), CONFIG);
  }
}

// ---------- cruce: victimización vs homicidios ----------
function correlacion(xs, ys) {
  const n = xs.length, mx = xs.reduce((s, x) => s + x, 0) / n, my = ys.reduce((s, y) => s + y, 0) / n;
  let sxy = 0, sxx = 0, syy = 0;
  for (let i = 0; i < n; i++) {
    sxy += (xs[i] - mx) * (ys[i] - my); sxx += (xs[i] - mx) ** 2; syy += (ys[i] - my) ** 2;
  }
  return sxy / Math.sqrt(sxx * syy);
}

function dibujarCruce() {
  const a = anioUsado("tasa_homicidios", estado.anio);
  const filas = Object.keys(datos.regiones).map(Number)
    .map((c) => ({ codigo: c, region: datos.regiones[c], x: valor(c, a, "victimizacion"), y: valor(c, a, "tasa_homicidios") }))
    .filter((f) => f.x !== null && f.y !== null);
  const r = Math.round(correlacion(filas.map((f) => f.x), filas.map((f) => f.y)) * 100) / 100 + 0;   // + 0 evita «−0»
  // Etiquetas solo para algunas regiones: las 3 con más homicidios, las 3 con más víctimas y la seleccionada.
  // Entre las de más víctimas, la de menos homicidios lleva su nombre debajo del punto para que no se monten.
  const masHomicidios = [...filas].sort((p, q) => q.y - p.y).slice(0, 3).map((f) => f.codigo);
  const masVictimas = [...filas].sort((p, q) => q.x - p.x).slice(0, 3).sort((p, q) => p.y - q.y).map((f) => f.codigo);
  const destacadas = new Set([...masHomicidios, ...masVictimas, estado.region]);
  const posicion = (f) => (f.codigo === masVictimas[0] && !masHomicidios.includes(f.codigo) ? "bottom center" : "top center");
  $("titulo-cruce").textContent = `Cada punto es una región, ${a}`;
  $("nota-cruce").textContent = `Donde más personas dicen haber sido víctimas de un delito no es donde hay más homicidios. ` +
    `En ${a}, la correlación entre ambos indicadores es ${formato(r, 2)} (0 = ninguna relación; 1 = relación perfecta).`;
  const marcas = (f) => f.codigo === estado.region;
  Plotly.react("grafico-cruce", [{
    type: "scatter", mode: "markers+text", x: filas.map((f) => f.x), y: filas.map((f) => f.y),
    text: filas.map((f) => (destacadas.has(f.codigo) ? f.region : "")), textposition: filas.map(posicion),
    textfont: { size: 11, color: color("--texto-2") }, customdata: filas.map((f) => f.region),
    marker: { size: filas.map((f) => (marcas(f) ? 15 : 11)),
              color: filas.map((f) => (marcas(f) ? color("--serie-2") : color("--serie-1"))),
              line: { color: color("--pagina"), width: 2 } },
    hovertemplate: "<b>%{customdata}</b><br>Víctimas: %{x:,.1f} %<br>Homicidios: %{y:,.1f} por 100 mil<extra></extra>",
  }], baseLayout({
    margin: { l: 56, r: 16, t: 10, b: 48 }, transition: SIN_MOVIMIENTO ? undefined : TRANSICION,
    xaxis: eje({ title: { text: "% de personas víctimas de algún delito" } }),
    yaxis: eje({ title: { text: "Homicidios por 100 mil habitantes" }, rangemode: "tozero" }),
  }), CONFIG);
}

// ---------- denuncias ----------
function dibujarDenuncias() {
  const mod = estado.modalidad;
  const mensual = datos.denuncias_mensual.filter((f) => f.modalidad === mod);
  $("titulo-mensual").textContent = `${mod}: denuncias en todo el país, por mes (enero 2018 - setiembre 2026)`;
  const conCorte = ["Robo", "Hurto"].includes(mod);
  Plotly.react("grafico-mensual", [{
    type: "scatter", mode: "lines", x: mensual.map((f) => `${f.anio}-${String(f.mes).padStart(2, "0")}-01`),
    y: mensual.map((f) => f.denuncias), line: { color: color("--serie-2"), width: 2.5 },
    fill: "tozeroy", fillcolor: "rgba(255,122,69,0.12)",
    customdata: mensual.map((f) => `${MESES[f.mes - 1]} ${f.anio}`),
    hovertemplate: "<b>%{y:,.0f}</b> denuncias<br>%{customdata}<extra></extra>",
  }], baseLayout({
    hovermode: "x", margin: { l: 56, r: 16, t: 24, b: 36 },
    xaxis: eje({ showspikes: true, spikemode: "across", spikethickness: 1, spikecolor: color("--texto-suave") }),
    yaxis: eje({ rangemode: "tozero" }),
    shapes: conCorte ? [{ type: "line", x0: "2024-11-01", x1: "2024-11-01", yref: "paper", y0: 0, y1: 1,
                          line: { color: color("--texto-suave"), dash: "dot", width: 1.5 } }] : [],
    annotations: conCorte ? [{ x: "2024-11-01", yref: "paper", y: 1, yanchor: "bottom", xanchor: "right", showarrow: false,
                               text: "Desde nov. 2024 faltan las denuncias virtuales", font: { size: 11, color: color("--texto-2") } }] : [],
  }), CONFIG);

  // Mapa de Lima Metropolitana por distrito (los distritos sin denuncias valen 0)
  const filas = new Map(datos.denuncias_lima.filter((f) => f.modalidad === mod && f.anio === estado.anioDen)
    .map((f) => [f.ubigeo, f]));
  const distritos = mapaLima.features.map((ft) => ft.properties);
  const tasas = distritos.map((d) => filas.get(d.ubigeo)?.tasa ?? 0);
  // Un distrito muy alto (el Cercado) aplastaría al resto en la escala: el color se corta en el percentil 95
  const zmax = [...tasas].sort((p, q) => p - q)[Math.floor(0.95 * (tasas.length - 1))] || 1;
  $("titulo-lima").textContent = `Lima Metropolitana: ${mod.toLowerCase()} por 100 mil habitantes, ${estado.anioDen}`;
  Plotly.react("grafico-lima", [{
    type: "choropleth", geojson: mapaLima, featureidkey: "properties.ubigeo",
    locations: distritos.map((d) => d.ubigeo), z: tasas, zmin: 0, zmax,
    customdata: distritos.map((d) => [d.distrito, filas.get(d.ubigeo)?.denuncias ?? 0]),
    colorscale: RAMPA_NARANJA, marker: { line: { color: BORDE_MAPA, width: 0.8 } },
    colorbar: { thickness: 12, len: 0.7, outlinewidth: 0, tickfont: { color: color("--texto-suave") } },
    hovertemplate: "<b>%{z:,.1f}</b> por 100 mil<br>%{customdata[0]}<br>%{customdata[1]:,.0f} denuncias<extra></extra>",
  }], baseLayout({ margin: { l: 0, r: 0, t: 0, b: 0 },
                   geo: { fitbounds: "locations", visible: false, bgcolor: "rgba(0,0,0,0)", projection: { type: "mercator" } } }), CONFIG);

  // Los 5 distritos con la tasa más alta (de 20 mil habitantes a más)
  const top = [...filas.values()].filter((f) => f.tasa > 0 && (f.denuncias / f.tasa) * 100000 >= 20000)
    .sort((p, q) => q.tasa - p.tasa).slice(0, 5);
  $("titulo-lima-top").textContent = `Los 5 distritos con la tasa más alta, ${estado.anioDen}`;
  $("lista-lima").replaceChildren(...top.map((f) => {
    const li = document.createElement("li");
    const cifra = document.createElement("span");
    cifra.className = "cifra";
    cifra.textContent = formato(f.tasa, 1);
    li.append(cifra, ` por 100 mil · ${f.distrito} (${formato(f.denuncias, 0)} denuncias)`);
    return li;
  }));
}

// ---------- fuentes ----------
function listarFuentes() {
  $("lista-fuentes").replaceChildren(...Object.values(datos.fuentes).map((f) => {
    const li = document.createElement("li");
    const enlace = document.createElement("a");
    enlace.href = f.url;
    enlace.textContent = f.descripcion.split(". http")[0];
    li.append(enlace, ` (descargado el ${f.fecha_descarga})`);
    return li;
  }));
}

// ---------- secciones que aparecen al bajar ----------
function revelarAlBajar() {
  const elementos = document.querySelectorAll(".kpis, .bloque");
  elementos.forEach((el) => el.classList.add("revelar"));
  const observador = new IntersectionObserver((entradas) => {
    for (const e of entradas) {
      if (e.isIntersecting) {
        e.target.classList.add("visible");
        observador.unobserve(e.target);
      }
    }
  }, { threshold: 0.08 });
  elementos.forEach((el) => observador.observe(el));
}

// ---------- dibujar todo ----------
function dibujarGenerales() {
  const ind = estado.indicador;
  const a = anioUsado(ind, estado.anio);
  $("aviso-anio").textContent = a === estado.anio ? "" :
    `No hay datos de «${INDICADORES[ind].nombre}» para ${estado.anio}; el mapa y el ranking muestran ${a}.`;
  $("titulo-explorar").textContent = `${INDICADORES[ind].nombre}: mapa y ranking`;
  const filas = filasRanking(ind, a);
  dibujarKpis();
  dibujarMapa(ind, a, filas);
  dibujarRanking(ind, a, filas);
  dibujarEvolucion();
  dibujarCruce();
}

async function iniciar() {
  const leer = (ruta) => fetch(ruta).then((r) => { if (!r.ok) throw new Error(`${ruta}: ${r.status}`); return r.json(); });
  [datos, mapaRegiones, mapaLima] = await Promise.all(
    [leer("data/datos.json"), leer("data/regiones.geojson"), leer("data/lima_distritos.geojson")]);
  sentidoHorario(mapaRegiones);
  sentidoHorario(mapaLima);
  const filas = [...datos.panel, ...datos.nacional];
  porClave = new Map(filas.map((f) => [`${f.codigo}-${f.anio}`, f]));
  aniosCon = Object.fromEntries(Object.keys(INDICADORES).map((ind) =>
    [ind, [...new Set(filas.filter((f) => f[ind] !== null).map((f) => f.anio))].sort((a, b) => a - b)]));

  prepararFiltros();
  listarFuentes();
  revelarAlBajar();
  dibujarGenerales();
  dibujarDenuncias();
  // Clic en una región del mapa = elegirla en el filtro
  $("grafico-mapa").on("plotly_click", (e) => {
    estado.region = Number(e.points[0].location);
    $("filtro-region").value = estado.region;
    dibujarGenerales();
  });
}

iniciar().catch((error) => {
  $("kpis").textContent = `No se pudieron cargar los datos (${error.message}). Abre la página desde un servidor, no con doble clic.`;
});