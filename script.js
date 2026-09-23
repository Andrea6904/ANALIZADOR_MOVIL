// Visor del informe del Analizador de Características de Celular.
// Carga un JSON con la forma que exporta analizador_celular.py y lo
// renderiza usando las mismas clases definidas en style.css.

function escapar(texto) {
  return String(texto)
    .replace(/&/g, "&amp;")
    .replace(/</g, "&lt;")
    .replace(/>/g, "&gt;");
}

function filasKV(datos) {
  if (!datos || Object.keys(datos).length === 0) {
    return '<p class="vacio">Sin datos</p>';
  }
  const filas = Object.entries(datos)
    .map(([clave, valor]) => {
      const etiqueta = clave.replace(/_/g, " ");
      const etiquetaCap = etiqueta.charAt(0).toUpperCase() + etiqueta.slice(1);
      return `<div class="fila"><span class="clave">${escapar(etiquetaCap)}</span><span class="valor">${escapar(valor)}</span></div>`;
    })
    .join("");
  return `<div class="tabla-kv">${filas}</div>`;
}

function chips(items) {
  if (!items || items.length === 0) {
    return '<p class="vacio">Sin datos</p>';
  }
  const html = items.map((i) => `<span class="chip">${escapar(i)}</span>`).join("");
  return `<div class="chips">${html}</div>`;
}

function modulo(titulo, contenidoHtml) {
  return `
    <section class="modulo">
      <h2>${escapar(titulo)}</h2>
      ${contenidoHtml}
    </section>`;
}

function renderizarReporte(reporte) {
  const general = reporte.general || {};
  const marca = general.Marca || general.marca || "";
  const modeloDispositivo = general.Modelo || general.modelo || "Dispositivo analizado";
  const titulo = `${marca} ${modeloDispositivo}`.trim() || "Dispositivo analizado";

  document.getElementById("dispositivo").textContent = titulo;

  const origen = reporte.origen || "Desconocido";
  const fecha = reporte.fecha_analisis || "";
  document.getElementById("meta").innerHTML =
    `Origen: <strong>${escapar(origen)}</strong> &nbsp;·&nbsp; Fecha de análisis: ${escapar(fecha)}`;

  const secciones = [
    modulo("Información general", filasKV(general)),
    modulo("Pantalla", filasKV(reporte.pantalla || {})),
    modulo("Sensores", chips(reporte.sensores || [])),
    modulo("Conectividad", chips(reporte.conectividad || [])),
    modulo("Cámara", chips(reporte.camara || [])),
    modulo("Seguridad y biometría", chips(reporte.seguridad_biometria || [])),
    modulo("Batería", filasKV(reporte.bateria || {})),
  ].join("");

  document.getElementById("contenedor-secciones").innerHTML = secciones;
}

function mostrarError(mensaje) {
  document.getElementById("contenedor-secciones").innerHTML =
    `<section class="modulo"><h2>No se pudo cargar el informe</h2><p class="vacio">${escapar(mensaje)}</p></section>`;
}

// Carga manual: el usuario selecciona el archivo .json exportado por el script
document.getElementById("archivo-json").addEventListener("change", (evento) => {
  const archivo = evento.target.files[0];
  if (!archivo) return;

  const lector = new FileReader();
  lector.onload = () => {
    try {
      const datos = JSON.parse(lector.result);
      renderizarReporte(datos);
    } catch (error) {
      mostrarError("El archivo seleccionado no es un JSON válido de análisis.");
    }
  };
  lector.onerror = () => {
    mostrarError("No se pudo leer el archivo seleccionado.");
  };
  lector.readAsText(archivo, "utf-8");
});

// Carga automática: intenta leer "analisis_celular.json" junto a esta página.
// Esto funciona cuando la página se sirve por http/https (por ejemplo,
// GitHub Pages); al abrir el HTML directamente con doble clic (file://),
// el navegador bloquea esta carga por seguridad y hay que usar el botón.
window.addEventListener("DOMContentLoaded", () => {
  fetch("analisis_celular.json")
    .then((respuesta) => {
      if (!respuesta.ok) throw new Error("No encontrado");
      return respuesta.json();
    })
    .then((datos) => renderizarReporte(datos))
    .catch(() => {
      // No pasa nada: se deja el estado inicial esperando carga manual.
    });
});
