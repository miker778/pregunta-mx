const EJEMPLOS = [
  ["trabajo", "Mi patrón me pide trabajar los sábados a las 10 pm sin pagarme horas extra, ¿dónde me quejo?"],
  ["trabajo", "¿Cómo sé si mi patrón está pagando mi IMSS?"],
  ["trabajo", "¿A qué prestaciones tengo derecho como trabajador y cómo las verifico?"],
  ["trabajo", "¿Cómo veo si mi patrón está haciendo aportaciones a mi Infonavit?"],
  ["vivienda", "Me aumentaron la renta sin previo aviso, ¿qué puedo hacer?"],
  ["federal", "¿Cómo saco mi pasaporte?"],
  ["federal", "¿Cómo me registro en el programa 60 y más?"],
  ["federal", "¿Cómo me registro en Jóvenes Construyendo el Futuro?"],
  ["federal", "Me voy a casar con una persona extranjera"],
  ["cdmx", "¿Cómo pido que bacheen mi calle?"],
  ["cdmx", "¿Qué hago si me robaron en mi casa?"],
  ["cdmx", "Compré un coche, ¿qué trámites siguen?"],
  ["cdmx", "Me cambio de casa, ¿qué tengo que actualizar?"],
  ["justicia", "¿Cómo hago un amparo?"],
  ["justicia", "¿Hay abogados públicos gratuitos para un juicio?"],
  ["justicia", "¿Cómo es el proceso en un juzgado?"],
  ["vivienda", "Voy a comprar una casa"],
  ["vivienda", "¿Cómo hago un contrato de arrendamiento?"],
  ["vivienda", "¿A qué tengo derecho como arrendador?"],
  ["vivienda", "Voy a rentar un departamento"],
];
const NOMBRE_TAG = { trabajo: "Trabajo", federal: "Federal", cdmx: "CDMX", justicia: "Justicia", vivienda: "Vivienda" };
const DOMINIOS = ["gob.mx", "sre.gob.mx", "sat.gob.mx", "imss.gob.mx", "bienestar.gob.mx", "cdmx.gob.mx",
  "fgjcdmx.gob.mx", "scjn.gob.mx", "diputados.gob.mx", "dof.gob.mx", "stps.gob.mx", "infonavit.org.mx",
  "ine.mx", "profeco.gob.mx", "cjf.gob.mx", "locatel.cdmx.gob.mx"];

const $ = (id) => document.getElementById(id);
const esc = (s) => String(s ?? "").replace(/[&<>"']/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));

// ejemplos y mosaico
$("rejilla").innerHTML = EJEMPLOS.map(([tag, q]) =>
  `<button class="ejemplo" type="button" data-q="${esc(q)}"><span class="tag ${tag}">${NOMBRE_TAG[tag]}</span><span class="q">${esc(q)}</span></button>`).join("");
$("rejilla").addEventListener("click", (e) => {
  const b = e.target.closest(".ejemplo");
  if (b) preguntar(b.dataset.q);
});
$("mosaico").innerHTML = DOMINIOS.map((d) => `<span>${d}</span>`).join("");

$("caja").addEventListener("submit", (e) => {
  e.preventDefault();
  const q = $("entrada").value.trim();
  if (q.length >= 3) preguntar(q);
});
$("botonInicio").addEventListener("click", () => { if (location.hash === "#chat") history.back(); else irAInicio(); });
window.addEventListener("popstate", () => { if (location.hash !== "#chat") irAInicio(); });

let enCurso = false;
let control = null; // para cancelar la respuesta en curso al volver a Inicio
let enEspera = null; // pregunta enviada mientras se escribía la anterior: va después
let turnos = 0;
const historial = []; // solo en esta pestaña: [{q, resumen}]

function abrirChat() {
  if (!$("chat").hidden) return;
  $("inicio").hidden = true;
  $("chat").hidden = false;
  $("botonInicio").hidden = false;
  document.body.classList.add("en-chat");
  $("entrada").placeholder = "Pregunta algo más...";
  if (location.hash !== "#chat") history.pushState({ chat: true }, "", "#chat");
  window.scrollTo({ top: 0 });
}

function irAInicio() {
  enEspera = null;
  if (control) control.abort();
  $("chat").hidden = true;
  $("inicio").hidden = false;
  $("botonInicio").hidden = true;
  document.body.classList.remove("en-chat");
  $("hilo").innerHTML = "";
  historial.length = 0;
  turnos = 0;
  $("entrada").value = "";
  $("entrada").placeholder = "Pregunta lo que necesites...";
  window.scrollTo({ top: 0 });
}

function contexto() {
  return historial.slice(-2).map((h) => `Antes preguntó: ${h.q}\nY se le contestó: ${h.resumen}`).join("\n\n").slice(0, 1800);
}

async function preguntar(q) {
  if (enCurso) { enEspera = q; $("entrada").value = ""; $("entrada").placeholder = "En cuanto termine, sigue tu pregunta..."; return; }
  enCurso = true;
  $("entrada").value = "";
  abrirChat();
  const id = ++turnos;
  const turno = document.createElement("div");
  turno.className = "turno";
  turno.innerHTML = `<div class="yo"></div><ol class="etapas"></ol><article class="respuesta" hidden></article>`;
  turno.querySelector(".yo").textContent = q;
  $("hilo").appendChild(turno);
  const etapas = turno.querySelector(".etapas");
  const caja = turno.querySelector(".respuesta");
  if (id > 1) turno.scrollIntoView({ behavior: "smooth", block: "start" });
  etapa(etapas, "Entendiendo tu pregunta");
  control = new AbortController();
  try {
    const r = await fetch("/api/preguntar", {
      method: "POST", headers: { "content-type": "application/json" }, signal: control.signal,
      body: JSON.stringify({ pregunta: q, contexto: contexto() }),
    });
    if (!r.ok) {
      const t = await r.json().catch(() => ({}));
      throw new Error(typeof t.detail === "string" ? t.detail : "No se pudo preguntar. Intenta de nuevo.");
    }
    const lector = r.body.getReader();
    const dec = new TextDecoder();
    let buf = "";
    for (;;) {
      const { value, done } = await lector.read();
      if (done) break;
      buf += dec.decode(value, { stream: true });
      let i;
      while ((i = buf.indexOf("\n")) >= 0) {
        const linea = buf.slice(0, i).trim();
        buf = buf.slice(i + 1);
        if (!linea) continue;
        const ev = JSON.parse(linea);
        if (ev.tipo === "etapa") { if (ev.texto !== "Entendiendo tu pregunta") etapa(etapas, ev.texto); }
        else if (ev.tipo === "resumen") {
          etapa(etapas, "Escribiendo los pasos");
          pintar(caja, { resumen: ev.texto, fuentes: ev.fuentes, pasos: [], documentos: [], lugares: [], costos: [], formularios: [], avisos: [], parcial: true }, id);
        }
        else if (ev.tipo === "error") { terminar(etapas); error(caja, ev.texto); }
        else if (ev.tipo === "respuesta") {
          etapa(etapas, `Listo en ${ev.datos.segundos} s`);
          terminar(etapas);
          pintar(caja, ev.datos, id);
          if (!ev.datos.sin_fuente) historial.push({ q, resumen: ev.datos.resumen.replace(/\[\d+\]/g, "") });
        }
      }
    }
  } catch (err) {
    terminar(etapas);
    if (err.name !== "AbortError") error(caja, err.message);
  } finally {
    control = null;
    enCurso = false;
    $("enviar").disabled = false;
    $("entrada").placeholder = "Pregunta algo más...";
    $("entrada").focus({ preventScroll: true });
    if (enEspera && !$("chat").hidden) { const siguiente = enEspera; enEspera = null; preguntar(siguiente); }
  }
}

function etapa(lista, texto) {
  terminar(lista);
  const li = document.createElement("li");
  li.className = "activa";
  li.textContent = texto;
  lista.appendChild(li);
}
function terminar(lista) {
  lista.querySelectorAll("li.activa").forEach((li) => li.classList.remove("activa"));
}
function error(caja, t) {
  caja.hidden = false;
  caja.innerHTML = `<div class="error">${esc(t)}</div>`;
}

function pintar(caja, d, id) {
  const v = new Set(d.fuentes.map((f) => f.n));
  const ref = (n) => `<a class="cita" href="#f-${id}-${n}" data-ref="f-${id}-${n}">${n}</a>`;
  const citas = (texto) => esc(texto).replace(/\[(\d+)\]/g, (m, n) => v.has(+n) ? ref(n) : "");
  const chips = (ns) => (ns || []).filter((n) => v.has(n)).map(ref).join("");
  let h = `<p class="resumen">${citas(d.resumen)}</p>`;
  if (d.pasos.length) {
    h += `<div class="bloque"><h3>Pasos</h3><ol class="pasos">${d.pasos.map((p) =>
      `<li><div><b>${esc(p.titulo)} ${chips(p.fuentes)}</b><span>${citas(p.detalle)}</span></div></li>`).join("")}</ol></div>`;
  }
  if (d.documentos.length) {
    h += `<div class="bloque"><h3>Qué llevar</h3><ul class="lista">${d.documentos.map((x) =>
      `<li>${citas(x.texto)} ${chips(x.fuentes)}</li>`).join("")}</ul></div>`;
  }
  if (d.lugares.length) {
    h += `<div class="bloque"><h3>A dónde ir</h3><ul class="lista">${d.lugares.map((x) =>
      `<li><b>${esc(x.nombre)}</b> ${chips(x.fuentes)}<br><span>${citas(x.detalle || "")}</span></li>`).join("")}</ul></div>`;
  }
  if (d.costos.length) {
    h += `<div class="bloque"><h3>Cuánto cuesta</h3><div class="costos">${d.costos.map((x) =>
      `<div class="costo"><div>${esc(x.concepto)} ${chips(x.fuentes)}<small>Vigente ${esc(x.vigencia || "")}</small></div><div class="monto">${esc(x.monto)}</div></div>`).join("")}</div></div>`;
  }
  if (d.formularios.length) {
    h += `<div class="bloque"><h3>Formularios</h3><ul class="lista">${d.formularios.map((x) =>
      `<li>${esc(x.nombre)} ${chips(x.fuentes)}</li>`).join("")}</ul></div>`;
  }
  if (d.avisos.length) {
    h += `<div class="bloque"><h3>Ojo</h3><div class="avisos">${d.avisos.map((a) => `<div class="aviso">${citas(a)}</div>`).join("")}</div></div>`;
  }
  if (d.fuentes.length) {
    h += `<div class="bloque"><h3>Fuentes oficiales</h3><div class="fuentes">${d.fuentes.map((f) =>
      `<a class="fuente" id="f-${id}-${f.n}" href="${/^https?:\/\//.test(f.url) ? esc(f.url) : "#"}" target="_blank" rel="noopener noreferrer"><span class="n">${f.n}</span><span><span class="t">${esc(f.titulo)}</span><span class="d">${esc(f.dominio)}</span></span></a>`).join("")}</div></div>`;
  }
  if (d.parcial) h += `<div class="cargando-detalle"><span></span><span></span><span></span></div>`;
  h += `<p class="nota">Pregunta MX puede equivocarse. Revisa la fuente oficial antes de ir. No es un sitio del gobierno.</p>`;
  caja.innerHTML = h;
  caja.hidden = false;
}

// tocar una cita lleva a su fuente y la resalta, sin cambiar la URL
document.addEventListener("click", (e) => {
  const c = e.target.closest(".cita[data-ref]");
  if (!c) return;
  e.preventDefault();
  document.querySelectorAll(".fuente.marcada").forEach((f) => f.classList.remove("marcada"));
  const f = document.getElementById(c.dataset.ref);
  if (f) { f.classList.add("marcada"); f.scrollIntoView({ behavior: "smooth", block: "center" }); }
});

if (location.hash === "#chat") history.replaceState(null, "", location.pathname);

// portada: el titular llena la pantalla sin chocar con la caja de pregunta
function ajustarTitular() {
  const heroe = $("heroe"), h1 = heroe.querySelector("h1");
  const alto = window.innerHeight - 76 - 150 - 64, ancho = heroe.clientWidth; // barra, caja y «Prueba un ejemplo»
  let lo = 26, hi = 112;
  for (let i = 0; i < 12; i++) {
    const m = (lo + hi) / 2;
    h1.style.fontSize = m + "px";
    if (h1.scrollHeight <= alto && h1.scrollWidth <= ancho) lo = m; else hi = m;
  }
  h1.style.fontSize = Math.floor(lo) + "px";
}
let tAjuste;
window.addEventListener("resize", () => { clearTimeout(tAjuste); tAjuste = setTimeout(ajustarTitular, 80); });
(document.fonts ? document.fonts.ready : Promise.resolve()).then(() => {
  ajustarTitular();
  requestAnimationFrame(() => $("heroe").classList.add("listo"));
});

// aparecer al hacer scroll, en cascada por grupo
function marcar(selector, paso) {
  document.querySelectorAll(selector).forEach((el, i) => {
    el.classList.add("revela");
    el.style.setProperty("--d", ((i % 4) * paso).toFixed(2) + "s");
  });
}
marcar(".ejemplo", 0.06);
marcar(".importa h2, .importa > p", 0.1);
marcar(".caso", 0.09);
document.querySelectorAll(".cifra").forEach((c) => {
  c.querySelector(".lienzo").classList.add("revela");
  c.querySelectorAll(".texto > *").forEach((el, i) => { el.classList.add("revela"); el.style.setProperty("--d", (0.12 + i * 0.08) + "s"); });
});
document.querySelectorAll(".sub, .pie-pagina p").forEach((el) => el.classList.add("revela"));

function contar(el) {
  const fin = +el.dataset.cuenta, fmt = el.dataset.formato, t0 = performance.now(), dur = 1400;
  const pinta = (v) => { el.textContent = fmt === "pct" ? `${v}%` : `$${v.toLocaleString("es-MX")}`; };
  const paso = (t) => {
    const k = Math.min(1, (t - t0) / dur), e = 1 - Math.pow(1 - k, 3);
    pinta(Math.round(fin * e));
    if (k < 1) requestAnimationFrame(paso);
  };
  requestAnimationFrame(paso);
}

const quieto = matchMedia("(prefers-reduced-motion: reduce)").matches;
const obs = new IntersectionObserver((entradas) => {
  entradas.forEach((en) => {
    if (!en.isIntersecting) return;
    en.target.classList.add("visible");
    const n = en.target.querySelector("[data-cuenta]");
    if (n && !quieto) contar(n);
    obs.unobserve(en.target);
  });
}, { threshold: 0.18, rootMargin: "0px 0px -6% 0px" });
document.querySelectorAll(".revela").forEach((el) => obs.observe(el));
