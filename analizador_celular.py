#!/usr/bin/env python3
"""
=====================================================================
 ANALIZADOR DE CARACTERÍSTICAS DE CELULAR (WSL + ADB / Modo Offline)
=====================================================================

Funciona en dos modos:

  MODO 1 - ADB (preferido):
      Detecta un celular Android conectado por USB con depuración
      activada y extrae sus características reales de hardware.

  MODO 2 - Consulta manual / base offline:
      Si no hay ADB o no hay celular conectado, permite ingresar
      marca y modelo y consulta una pequeña base de datos JSON local
      (modo offline simulado, ya que no existe una API pública y
      gratuita de especificaciones tipo GSMArena).

Requiere: Python 3.8+, adb instalado en WSL (opcional pero recomendado).
No requiere librerías externas obligatorias. `requests` se usa solo
si en el futuro se configura una API real (ver función consultar_api).

Autor: Generado con Claude
=====================================================================
"""

import json
import os
import shutil
import subprocess
import sys
from datetime import datetime

# ---------------------------------------------------------------------------
# Utilidades generales
# ---------------------------------------------------------------------------

SEPARADOR = "=" * 70
SUBSEPARADOR = "-" * 70


def encabezado(titulo: str) -> None:
    print("\n" + SEPARADOR)
    print(f" {titulo}")
    print(SEPARADOR)


def sub_encabezado(titulo: str) -> None:
    print("\n" + SUBSEPARADOR)
    print(f" {titulo}")
    print(SUBSEPARADOR)


def ejecutar_comando(cmd: list, timeout: int = 15) -> str:
    """Ejecuta un comando de shell y devuelve su salida como texto.
    Devuelve cadena vacía si falla."""
    try:
        resultado = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            timeout=timeout,
        )
        return resultado.stdout.strip()
    except (subprocess.TimeoutExpired, FileNotFoundError, OSError):
        return ""


# ---------------------------------------------------------------------------
# MODO 1: ADB
# ---------------------------------------------------------------------------

def adb_instalado() -> bool:
    """Verifica si el binario adb está disponible en el PATH de WSL."""
    return shutil.which("adb") is not None


def mostrar_instrucciones_instalacion_adb() -> None:
    sub_encabezado("ADB no está instalado en este entorno WSL")
    print(
        "Para instalar Android Debug Bridge (adb) en WSL, ejecuta en tu\n"
        "terminal de WSL (Ubuntu/Debian) los siguientes comandos:\n"
    )
    print("    sudo apt update")
    print("    sudo apt install -y adb\n")
    print(
        "Verifica la instalación con:\n"
        "    adb version\n"
    )
    print(
        "Nota importante sobre WSL y USB:\n"
        "WSL2 no comparte el bus USB con Windows de forma nativa. Para que\n"
        "'adb devices' detecte tu celular conectado por USB al PC, tienes\n"
        "dos opciones recomendadas:\n\n"
        "  a) Usar 'usbipd-win' para compartir el dispositivo USB con WSL:\n"
        "     1. En Windows (PowerShell como administrador):\n"
        "          winget install usbipd\n"
        "     2. Conecta el celular y lista los dispositivos USB:\n"
        "          usbipd list\n"
        "     3. Comparte y adjunta el dispositivo del celular a WSL:\n"
        "          usbipd bind --busid <BUSID>\n"
        "          usbipd attach --wsl --busid <BUSID>\n"
        "     4. Dentro de WSL, confirma que aparece con:\n"
        "          lsusb\n\n"
        "  b) Alternativa más simple: correr el servidor adb en Windows\n"
        "     (adb.exe de Android Platform Tools) y en WSL conectar por\n"
        "     red usando la IP del host:\n"
        "          adb.exe tcpip 5555\n"
        "          adb connect <IP_DEL_CELULAR>:5555\n"
    )


def mostrar_instrucciones_depuracion_usb() -> None:
    sub_encabezado("Cómo activar la Depuración USB en el celular")
    print(
        "1. Ve a Ajustes > Acerca del teléfono.\n"
        "2. Toca 7 veces seguidas sobre 'Número de compilación' hasta que\n"
        "   aparezca el mensaje 'Ya eres desarrollador'.\n"
        "3. Regresa a Ajustes > Sistema > Opciones de desarrollador\n"
        "   (en algunos modelos aparece directamente en Ajustes).\n"
        "4. Activa 'Depuración USB'.\n"
        "5. Conecta el celular por cable USB al PC y, cuando aparezca el\n"
        "   diálogo 'Permitir depuración USB', acepta y marca\n"
        "   'Confiar siempre en este equipo'.\n"
        "6. Verifica la conexión desde WSL con:\n"
        "       adb devices\n"
        "   Debe aparecer el ID del dispositivo seguido de 'device'.\n"
    )


def obtener_dispositivos_adb() -> list:
    """Devuelve la lista de IDs de dispositivos conectados y autorizados."""
    salida = ejecutar_comando(["adb", "devices"])
    dispositivos = []
    if not salida:
        return dispositivos
    lineas = salida.splitlines()[1:]  # saltar encabezado "List of devices attached"
    for linea in lineas:
        partes = linea.strip().split()
        if len(partes) == 2 and partes[1] == "device":
            dispositivos.append(partes[0])
    return dispositivos


def adb_shell(device_id: str, comando: str) -> str:
    return ejecutar_comando(["adb", "-s", device_id, "shell", comando])


def obtener_getprop(device_id: str) -> dict:
    salida = adb_shell(device_id, "getprop")
    props = {}
    for linea in salida.splitlines():
        linea = linea.strip()
        if linea.startswith("[") and "]: [" in linea:
            try:
                clave, valor = linea.split("]: [", 1)
                clave = clave.lstrip("[")
                valor = valor.rstrip("]")
                props[clave] = valor
            except ValueError:
                continue

    def g(*claves, default="Desconocido"):
        for c in claves:
            if c in props and props[c]:
                return props[c]
        return default

    return {
        "marca": g("ro.product.manufacturer", "ro.product.brand"),
        "modelo": g("ro.product.model"),
        "nombre_dispositivo": g("ro.product.device"),
        "version_android": g("ro.build.version.release"),
        "sdk_api": g("ro.build.version.sdk"),
        "procesador": g("ro.board.platform", "ro.product.board"),
        "fabricante_soc": g("ro.hardware"),
        "numero_serie": g("ro.serialno", "ro.boot.serialno"),
    }


# Mapa de patrones de sensores -> nombre amigable en español
PATRONES_SENSORES = [
    ("gyroscope", "Giroscopio"),
    ("accelerometer", "Acelerómetro"),
    ("magnetic field", "Magnetómetro / Brújula"),
    ("proximity", "Sensor de proximidad"),
    ("light", "Sensor de luz ambiental"),
    ("gravity", "Sensor de gravedad"),
    ("rotation vector", "Vector de rotación"),
    ("linear acceleration", "Aceleración lineal"),
    ("step counter", "Contador de pasos"),
    ("step detector", "Detector de pasos"),
    ("barometer", "Barómetro"),
    ("pressure", "Sensor de presión"),
    ("heart rate", "Sensor de ritmo cardíaco"),
    ("fingerprint", "Sensor de huella (vía sensorservice)"),
    ("hinge", "Sensor de bisagra (plegables)"),
    ("temperature", "Sensor de temperatura"),
]


def obtener_sensores(device_id: str) -> list:
    salida = adb_shell(device_id, "dumpsys sensorservice")
    if not salida:
        return []
    encontrados = []
    texto = salida.lower()
    for patron, nombre in PATRONES_SENSORES:
        if patron in texto:
            encontrados.append(nombre)
    # Eliminar duplicados manteniendo orden
    vistos = set()
    unicos = []
    for s in encontrados:
        if s not in vistos:
            vistos.add(s)
            unicos.append(s)
    return unicos


# Mapa de características de hardware (pm list features) -> nombre amigable
PATRONES_FEATURES = [
    ("android.hardware.nfc", "NFC"),
    ("android.hardware.fingerprint", "Lector de huellas dactilares"),
    ("android.hardware.biometrics.face", "Reconocimiento facial"),
    ("android.hardware.camera.front", "Cámara frontal"),
    ("android.hardware.camera.flash", "Flash de cámara"),
    ("android.hardware.camera", "Cámara"),
    ("android.hardware.bluetooth_le", "Bluetooth Low Energy"),
    ("android.hardware.bluetooth", "Bluetooth"),
    ("android.hardware.wifi.direct", "Wi-Fi Direct"),
    ("android.hardware.wifi", "Wi-Fi"),
    ("android.hardware.telephony.gsm", "Telefonía GSM"),
    ("android.hardware.telephony", "Telefonía / Llamadas"),
    ("android.hardware.usb.host", "USB Host (USB OTG)"),
    ("android.hardware.sensor.gyroscope", "Giroscopio (feature)"),
    ("android.hardware.sensor.accelerometer", "Acelerómetro (feature)"),
    ("android.hardware.sensor.compass", "Brújula (feature)"),
    ("android.hardware.sensor.proximity", "Proximidad (feature)"),
    ("android.hardware.sensor.light", "Luz ambiental (feature)"),
    ("android.hardware.sensor.barometer", "Barómetro (feature)"),
    ("android.hardware.location.gps", "GPS"),
    ("android.hardware.location", "Localización"),
    ("android.hardware.screen.landscape", "Rotación de pantalla (landscape)"),
    ("android.hardware.vulkan", "Soporte gráfico Vulkan"),
    ("android.software.leanback", "Android TV (leanback)"),
    ("android.hardware.type.watch", "Formato reloj (Wear OS)"),
]


def obtener_features(device_id: str) -> list:
    salida = adb_shell(device_id, "pm list features")
    if not salida:
        return []
    texto = salida.lower()
    encontradas = []
    for patron, nombre in PATRONES_FEATURES:
        if patron in texto:
            encontradas.append(nombre)
    return encontradas


def obtener_pantalla(device_id: str) -> dict:
    tam = adb_shell(device_id, "wm size")
    dens = adb_shell(device_id, "wm density")
    resolucion = "Desconocida"
    densidad = "Desconocida"
    if "Physical size:" in tam:
        resolucion = tam.split("Physical size:")[-1].strip()
    if "Physical density:" in dens:
        densidad = dens.split("Physical density:")[-1].strip() + " dpi"
    return {"resolucion": resolucion, "densidad": densidad}


def obtener_bateria(device_id: str) -> dict:
    salida = adb_shell(device_id, "dumpsys battery")
    datos = {"nivel": "Desconocido", "estado": "Desconocido", "tecnologia": "Desconocida",
              "temperatura": "Desconocida", "salud": "Desconocida"}
    for linea in salida.splitlines():
        linea = linea.strip()
        if linea.lower().startswith("level:"):
            datos["nivel"] = linea.split(":", 1)[1].strip() + " %"
        elif linea.lower().startswith("status:"):
            datos["estado"] = linea.split(":", 1)[1].strip()
        elif linea.lower().startswith("technology:"):
            datos["tecnologia"] = linea.split(":", 1)[1].strip()
        elif linea.lower().startswith("temperature:"):
            try:
                valor = int(linea.split(":", 1)[1].strip())
                datos["temperatura"] = f"{valor / 10:.1f} °C"
            except ValueError:
                pass
        elif linea.lower().startswith("health:"):
            datos["salud"] = linea.split(":", 1)[1].strip()
    return datos


def analizar_via_adb(device_id: str) -> dict:
    print(f"\nExtrayendo información del dispositivo '{device_id}'... esto puede tardar unos segundos.")
    props = obtener_getprop(device_id)
    sensores = obtener_sensores(device_id)
    features = obtener_features(device_id)
    pantalla = obtener_pantalla(device_id)
    bateria = obtener_bateria(device_id)

    return {
        "origen": "ADB (datos reales del dispositivo)",
        "fecha_analisis": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        "general": {
            "Marca": props["marca"],
            "Modelo": props["modelo"],
            "Nombre interno": props["nombre_dispositivo"],
            "Versión de Android": props["version_android"],
            "API Level": props["sdk_api"],
            "Procesador / SoC": props["procesador"],
            "Número de serie": props["numero_serie"],
        },
        "pantalla": pantalla,
        "sensores": sensores if sensores else ["No se pudo determinar (revisa permisos de adb shell)"],
        "conectividad": [f for f in features if f in (
            "NFC", "Bluetooth Low Energy", "Bluetooth", "Wi-Fi Direct", "Wi-Fi",
            "Telefonía GSM", "Telefonía / Llamadas", "USB Host (USB OTG)", "GPS", "Localización"
        )] or ["No se detectaron características de conectividad"],
        "camara": [f for f in features if "cámara" in f.lower() or "flash" in f.lower()]
                   or ["No se detectó información de cámara"],
        "seguridad_biometria": [f for f in features if "huella" in f.lower() or "facial" in f.lower()]
                   or ["No se detectaron sensores biométricos"],
        "bateria": bateria,
        "todas_las_features": features,
    }


# ---------------------------------------------------------------------------
# MODO 2: Consulta manual / base de datos offline
# ---------------------------------------------------------------------------

RUTA_BASE_OFFLINE = os.path.join(os.path.dirname(os.path.abspath(__file__)), "base_celulares_offline.json")

BASE_OFFLINE_EJEMPLO = {
    "samsung galaxy s23": {
        "marca": "Samsung", "modelo": "Galaxy S23",
        "pantalla": {"resolucion": "1080 x 2340", "densidad": "425 dpi", "tamano": "6.1 pulgadas", "tecnologia": "Dynamic AMOLED 2X"},
        "sensores": ["Giroscopio", "Acelerómetro", "Magnetómetro / Brújula", "Sensor de proximidad",
                     "Sensor de luz ambiental", "Barómetro", "Sensor de huella (bajo pantalla)"],
        "conectividad": ["NFC", "Bluetooth 5.3", "Wi-Fi 6E", "5G", "GPS"],
        "camara": ["Principal 50MP", "Ultra gran angular 12MP", "Teleobjetivo 10MP", "Frontal 12MP"],
        "bateria": {"capacidad": "3900 mAh", "carga_rapida": "25W"},
    },
    "xiaomi redmi note 12": {
        "marca": "Xiaomi", "modelo": "Redmi Note 12",
        "pantalla": {"resolucion": "1080 x 2400", "densidad": "395 dpi", "tamano": "6.67 pulgadas", "tecnologia": "AMOLED"},
        "sensores": ["Giroscopio", "Acelerómetro", "Magnetómetro / Brújula", "Sensor de proximidad",
                     "Sensor de luz ambiental", "Sensor de huella (lateral)"],
        "conectividad": ["NFC (según región)", "Bluetooth 5.1", "Wi-Fi 5", "4G LTE", "GPS"],
        "camara": ["Principal 48MP", "Ultra gran angular 8MP", "Macro 2MP", "Frontal 13MP"],
        "bateria": {"capacidad": "5000 mAh", "carga_rapida": "33W"},
    },
    "motorola moto g84": {
        "marca": "Motorola", "modelo": "Moto G84",
        "pantalla": {"resolucion": "1080 x 2400", "densidad": "394 dpi", "tamano": "6.55 pulgadas", "tecnologia": "P-OLED"},
        "sensores": ["Giroscopio", "Acelerómetro", "Magnetómetro / Brújula", "Sensor de proximidad",
                     "Sensor de luz ambiental", "Sensor de huella (lateral)"],
        "conectividad": ["NFC", "Bluetooth 5.1", "Wi-Fi 5", "5G", "GPS"],
        "camara": ["Principal 50MP", "Ultra gran angular 8MP", "Frontal 16MP"],
        "bateria": {"capacidad": "5000 mAh", "carga_rapida": "30W"},
    },
}


def asegurar_base_offline() -> dict:
    """Crea el archivo de base offline si no existe, y lo devuelve cargado."""
    if not os.path.exists(RUTA_BASE_OFFLINE):
        with open(RUTA_BASE_OFFLINE, "w", encoding="utf-8") as f:
            json.dump(BASE_OFFLINE_EJEMPLO, f, ensure_ascii=False, indent=2)
    try:
        with open(RUTA_BASE_OFFLINE, "r", encoding="utf-8") as f:
            return json.load(f)
    except (json.JSONDecodeError, OSError):
        return BASE_OFFLINE_EJEMPLO


def consultar_api(marca: str, modelo: str):
    """
    Punto de extensión para una API real de especificaciones (por ejemplo,
    un servicio de pago de GSMArena o similar). Actualmente no existe una
    API pública y gratuita confiable para esto, así que esta función
    devuelve None y el programa cae automáticamente al modo offline.

    Si en el futuro se dispone de una API con clave propia, se podría
    implementar aquí usando la librería `requests`, por ejemplo:

        import requests
        resp = requests.get(
            "https://api.ejemplo.com/specs",
            params={"brand": marca, "model": modelo},
            timeout=10,
        )
        if resp.status_code == 200:
            return resp.json()
    """
    return None


def analizar_via_api_o_offline() -> dict:
    sub_encabezado("Modo 2: Consulta manual de especificaciones")
    marca = input("Ingresa la marca del celular (ej. Samsung): ").strip()
    modelo = input("Ingresa el modelo del celular (ej. Galaxy S23): ").strip()

    resultado_api = consultar_api(marca, modelo)
    if resultado_api:
        resultado_api["origen"] = "API en línea"
        return resultado_api

    print(
        "\n[AVISO] No hay una API pública gratuita disponible para consultar "
        "especificaciones en tiempo real.\n"
        "Se usará una BASE DE DATOS LOCAL DE EJEMPLO (modo offline simulado)."
    )

    base = asegurar_base_offline()
    clave = f"{marca} {modelo}".strip().lower()

    datos = None
    for k, v in base.items():
        if clave == k or (marca.lower() in k and modelo.lower() in k):
            datos = v
            break

    if datos is None:
        print(
            f"\nNo se encontró '{marca} {modelo}' en la base offline de ejemplo.\n"
            f"Modelos disponibles actualmente: {', '.join(v['marca'] + ' ' + v['modelo'] for v in base.values())}\n"
            "Se generará un resultado genérico de referencia."
        )
        datos = {
            "marca": marca or "Desconocida",
            "modelo": modelo or "Desconocido",
            "pantalla": {"resolucion": "No disponible", "densidad": "No disponible",
                         "tamano": "No disponible", "tecnologia": "No disponible"},
            "sensores": ["Sin datos (modelo no encontrado en base offline)"],
            "conectividad": ["Sin datos (modelo no encontrado en base offline)"],
            "camara": ["Sin datos (modelo no encontrado en base offline)"],
            "bateria": {"capacidad": "No disponible", "carga_rapida": "No disponible"},
        }

    return {
        "origen": "Base de datos OFFLINE de ejemplo (simulada, no en tiempo real)",
        "fecha_analisis": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        "general": {
            "Marca": datos.get("marca", marca),
            "Modelo": datos.get("modelo", modelo),
        },
        "pantalla": datos.get("pantalla", {}),
        "sensores": datos.get("sensores", []),
        "conectividad": datos.get("conectividad", []),
        "camara": datos.get("camara", []),
        "seguridad_biometria": [s for s in datos.get("sensores", []) if "huella" in s.lower()]
                                or ["No especificado en base offline"],
        "bateria": datos.get("bateria", {}),
    }


# ---------------------------------------------------------------------------
# Presentación de resultados
# ---------------------------------------------------------------------------

def imprimir_lista(items, indent="   - "):
    if not items:
        print(f"{indent}Sin datos")
        return
    for item in items:
        print(f"{indent}{item}")


def imprimir_diccionario(d, indent="   "):
    if not d:
        print(f"{indent}Sin datos")
        return
    for clave, valor in d.items():
        etiqueta = clave.replace("_", " ").capitalize()
        print(f"{indent}{etiqueta}: {valor}")


def mostrar_reporte(reporte: dict) -> None:
    encabezado("RESULTADO DEL ANÁLISIS")
    print(f"Origen de los datos : {reporte.get('origen', 'Desconocido')}")
    print(f"Fecha de análisis   : {reporte.get('fecha_analisis', 'Desconocido')}")

    sub_encabezado("INFORMACIÓN GENERAL")
    imprimir_diccionario(reporte.get("general", {}))

    sub_encabezado("PANTALLA")
    imprimir_diccionario(reporte.get("pantalla", {}))

    sub_encabezado("SENSORES")
    imprimir_lista(reporte.get("sensores", []))

    sub_encabezado("CONECTIVIDAD")
    imprimir_lista(reporte.get("conectividad", []))

    sub_encabezado("CÁMARA")
    imprimir_lista(reporte.get("camara", []))

    sub_encabezado("SEGURIDAD / BIOMETRÍA")
    imprimir_lista(reporte.get("seguridad_biometria", []))

    sub_encabezado("BATERÍA")
    imprimir_diccionario(reporte.get("bateria", {}))

    print("\n" + SEPARADOR)


# ---------------------------------------------------------------------------
# Exportación de informe
# ---------------------------------------------------------------------------

def _html_escapar(texto) -> str:
    texto = str(texto)
    return (
        texto.replace("&", "&amp;")
        .replace("<", "&lt;")
        .replace(">", "&gt;")
    )


def _html_filas_kv(d: dict) -> str:
    if not d:
        return '<p class="vacio">Sin datos</p>'
    filas = []
    for clave, valor in d.items():
        etiqueta = _html_escapar(clave.replace("_", " ").capitalize())
        filas.append(
            f'<div class="fila"><span class="clave">{etiqueta}</span>'
            f'<span class="valor">{_html_escapar(valor)}</span></div>'
        )
    return '<div class="tabla-kv">' + "".join(filas) + "</div>"


def _html_chips(items: list) -> str:
    if not items:
        return '<p class="vacio">Sin datos</p>'
    chips = "".join(f'<span class="chip">{_html_escapar(i)}</span>' for i in items)
    return f'<div class="chips">{chips}</div>'


def generar_html_reporte(reporte: dict) -> str:
    """Construye un informe HTML autocontenido (CSS incluido) con estética
    de 'hoja de diagnóstico técnico' para visualizar el análisis del celular."""

    general = reporte.get("general", {})
    modelo = general.get("Modelo", "Dispositivo desconocido")
    marca = general.get("Marca", "")
    titulo_dispositivo = f"{marca} {modelo}".strip() or "Dispositivo analizado"

    secciones_html = f"""
    <section class="modulo">
      <h2>Información general</h2>
      {_html_filas_kv(general)}
    </section>

    <section class="modulo">
      <h2>Pantalla</h2>
      {_html_filas_kv(reporte.get("pantalla", {}))}
    </section>

    <section class="modulo">
      <h2>Sensores</h2>
      {_html_chips(reporte.get("sensores", []))}
    </section>

    <section class="modulo">
      <h2>Conectividad</h2>
      {_html_chips(reporte.get("conectividad", []))}
    </section>

    <section class="modulo">
      <h2>Cámara</h2>
      {_html_chips(reporte.get("camara", []))}
    </section>

    <section class="modulo">
      <h2>Seguridad y biometría</h2>
      {_html_chips(reporte.get("seguridad_biometria", []))}
    </section>

    <section class="modulo">
      <h2>Batería</h2>
      {_html_filas_kv(reporte.get("bateria", {}))}
    </section>
    """

    origen = _html_escapar(reporte.get("origen", "Desconocido"))
    fecha = _html_escapar(reporte.get("fecha_analisis", ""))

    return f"""<!DOCTYPE html>
<html lang="es">
<head>
<meta charset="UTF-8">
<title>Análisis — {_html_escapar(titulo_dispositivo)}</title>
<style>
  :root {{
    --bg: #0b1622;
    --bg-grid-line: rgba(124, 231, 208, 0.06);
    --panel: #101f30;
    --line: #24405c;
    --accent: #7ce7d0;
    --accent-warn: #f2b84b;
    --text: #e7eef5;
    --text-muted: #8aa0b8;
  }}

  * {{ box-sizing: border-box; }}

  body {{
    margin: 0;
    background-color: var(--bg);
    background-image:
      linear-gradient(var(--bg-grid-line) 1px, transparent 1px),
      linear-gradient(90deg, var(--bg-grid-line) 1px, transparent 1px);
    background-size: 28px 28px;
    color: var(--text);
    font-family: "IBM Plex Sans", "Segoe UI", Arial, sans-serif;
    line-height: 1.5;
    padding: 40px 20px 80px;
  }}

  .hoja {{
    max-width: 760px;
    margin: 0 auto;
  }}

  header.cabecera {{
    position: relative;
    padding: 28px 26px;
    margin-bottom: 34px;
    border: 1px solid var(--line);
    background: linear-gradient(180deg, rgba(124,231,208,0.05), transparent 60%);
  }}

  header.cabecera::before,
  header.cabecera::after,
  .modulo::before,
  .modulo::after {{
    content: "";
    position: absolute;
    width: 14px;
    height: 14px;
    border: 2px solid var(--accent);
  }}
  header.cabecera::before {{ top: -1px; left: -1px; border-right: none; border-bottom: none; }}
  header.cabecera::after  {{ bottom: -1px; right: -1px; border-left: none; border-top: none; }}
  .modulo::before {{ top: -1px; left: -1px; border-right: none; border-bottom: none; }}
  .modulo::after  {{ bottom: -1px; right: -1px; border-left: none; border-top: none; }}

  .dispositivo {{
    font-size: 1.9rem;
    font-weight: 700;
    letter-spacing: -0.01em;
    margin: 0 0 6px;
  }}

  .meta {{
    color: var(--text-muted);
    font-family: "IBM Plex Mono", "JetBrains Mono", ui-monospace, monospace;
    font-size: 0.82rem;
  }}

  .meta strong {{ color: var(--accent); font-weight: 500; }}

  .modulo {{
    position: relative;
    border: 1px solid var(--line);
    background: var(--panel);
    padding: 22px 24px;
    margin-bottom: 18px;
  }}

  .modulo h2 {{
    margin: 0 0 14px;
    font-size: 1rem;
    font-weight: 600;
    color: var(--text);
    padding-bottom: 10px;
    border-bottom: 1px solid var(--line);
  }}

  .tabla-kv .fila {{
    display: flex;
    justify-content: space-between;
    gap: 16px;
    padding: 7px 0;
    border-bottom: 1px dashed rgba(138, 160, 184, 0.18);
    font-family: "IBM Plex Mono", "JetBrains Mono", ui-monospace, monospace;
    font-size: 0.88rem;
  }}
  .tabla-kv .fila:last-child {{ border-bottom: none; }}

  .tabla-kv .clave {{ color: var(--text-muted); }}
  .tabla-kv .valor {{ color: var(--text); text-align: right; }}

  .chips {{
    display: flex;
    flex-wrap: wrap;
    gap: 8px;
  }}

  .chip {{
    border: 1px solid var(--line);
    color: var(--accent);
    background: rgba(124, 231, 208, 0.06);
    padding: 5px 10px;
    font-family: "IBM Plex Mono", "JetBrains Mono", ui-monospace, monospace;
    font-size: 0.8rem;
  }}

  .vacio {{
    color: var(--text-muted);
    font-style: italic;
    margin: 0;
    font-size: 0.88rem;
  }}

  footer {{
    max-width: 760px;
    margin: 30px auto 0;
    color: var(--text-muted);
    font-family: "IBM Plex Mono", "JetBrains Mono", ui-monospace, monospace;
    font-size: 0.76rem;
    text-align: center;
  }}

  @media (max-width: 600px) {{
    .dispositivo {{ font-size: 1.5rem; }}
    .tabla-kv .fila {{ flex-direction: column; gap: 2px; }}
    .tabla-kv .valor {{ text-align: left; }}
  }}
</style>
</head>
<body>
  <div class="hoja">
    <header class="cabecera">
      <p class="dispositivo">{_html_escapar(titulo_dispositivo)}</p>
      <p class="meta">Origen: <strong>{origen}</strong> &nbsp;·&nbsp; Fecha de análisis: {fecha}</p>
    </header>

    {secciones_html}
  </div>
  <footer>Generado por Analizador de Características de Celular (WSL)</footer>
</body>
</html>
"""


def exportar_reporte(reporte: dict) -> None:
    sub_encabezado("Exportar informe")
    print("1. Exportar como .txt")
    print("2. Exportar como .json")
    print("3. Exportar como .html (vista visual)")
    print("4. No exportar")
    opcion = input("Selecciona una opción: ").strip()

    carpeta_destino = os.path.expanduser("~/Escritorio")
    if not os.path.isdir(carpeta_destino):
        # En muchas instalaciones de WSL la carpeta se llama 'Desktop'
        alterna = os.path.expanduser("~/Desktop")
        carpeta_destino = alterna if os.path.isdir(alterna) else os.path.expanduser("~")

    if opcion == "1":
        ruta = os.path.join(carpeta_destino, "analisis_celular.txt")
        try:
            with open(ruta, "w", encoding="utf-8") as f:
                f.write("REPORTE DE ANÁLISIS DE CELULAR\n")
                f.write(f"Origen: {reporte.get('origen')}\n")
                f.write(f"Fecha: {reporte.get('fecha_analisis')}\n\n")
                for seccion, contenido in reporte.items():
                    if seccion in ("origen", "fecha_analisis"):
                        continue
                    f.write(f"[{seccion.upper()}]\n")
                    if isinstance(contenido, dict):
                        for k, v in contenido.items():
                            f.write(f"  {k}: {v}\n")
                    elif isinstance(contenido, list):
                        for item in contenido:
                            f.write(f"  - {item}\n")
                    f.write("\n")
            print(f"\nInforme guardado exitosamente en: {ruta}")
        except OSError as e:
            print(f"\n[ERROR] No se pudo guardar el archivo: {e}")

    elif opcion == "2":
        ruta = os.path.join(carpeta_destino, "analisis_celular.json")
        try:
            with open(ruta, "w", encoding="utf-8") as f:
                json.dump(reporte, f, ensure_ascii=False, indent=2)
            print(f"\nInforme guardado exitosamente en: {ruta}")
        except OSError as e:
            print(f"\n[ERROR] No se pudo guardar el archivo: {e}")

    elif opcion == "3":
        ruta = os.path.join(carpeta_destino, "analisis_celular.html")
        try:
            with open(ruta, "w", encoding="utf-8") as f:
                f.write(generar_html_reporte(reporte))
            print(f"\nInforme guardado exitosamente en: {ruta}")
            print(
                "Ábrelo con tu navegador (en WSL, por ejemplo):\n"
                f"    explorer.exe $(wslpath -w '{ruta}')"
            )
        except OSError as e:
            print(f"\n[ERROR] No se pudo guardar el archivo: {e}")
    else:
        print("\nNo se exportó ningún archivo.")


# ---------------------------------------------------------------------------
# Flujo principal / Menú
# ---------------------------------------------------------------------------

def ejecutar_analisis() -> dict:
    """Intenta el Modo 1 (ADB). Si falla, ofrece el Modo 2."""
    encabezado("Paso 1: Verificando ADB")

    if not adb_instalado():
        mostrar_instrucciones_instalacion_adb()
        respuesta = input(
            "\n¿Deseas continuar con el Modo 2 (consulta manual / offline)? (s/n): "
        ).strip().lower()
        if respuesta == "s":
            return analizar_via_api_o_offline()
        else:
            print("\nInstala adb y vuelve a ejecutar el script. Saliendo...")
            sys.exit(0)

    print("adb está instalado correctamente. ✔")
    dispositivos = obtener_dispositivos_adb()

    if not dispositivos:
        sub_encabezado("No se detectó ningún celular conectado")
        print(
            "No se encontraron dispositivos en 'adb devices' con estado 'device'.\n"
            "Posibles causas:\n"
            "  - El celular no está conectado por USB (o no está compartido a WSL).\n"
            "  - La Depuración USB no está activada.\n"
            "  - No has aceptado el diálogo de autorización en el celular.\n"
        )
        mostrar_instrucciones_depuracion_usb()
        respuesta = input(
            "¿Deseas continuar con el Modo 2 (consulta manual / offline)? (s/n): "
        ).strip().lower()
        if respuesta == "s":
            return analizar_via_api_o_offline()
        else:
            print("\nSaliendo...")
            sys.exit(0)

    if len(dispositivos) > 1:
        print(f"\nSe detectaron {len(dispositivos)} dispositivos:")
        for i, d in enumerate(dispositivos, 1):
            print(f"  {i}. {d}")
        seleccion = input("Selecciona el número del dispositivo a analizar: ").strip()
        try:
            idx = int(seleccion) - 1
            device_id = dispositivos[idx]
        except (ValueError, IndexError):
            print("Selección inválida. Se usará el primer dispositivo detectado.")
            device_id = dispositivos[0]
    else:
        device_id = dispositivos[0]
        print(f"\nDispositivo detectado: {device_id} ✔")

    return analizar_via_adb(device_id)


def menu_principal():
    encabezado("ANALIZADOR DE CARACTERÍSTICAS DE CELULAR (WSL)")
    print(
        "Este programa detecta las características técnicas de un celular\n"
        "Android (sensores, cámara, conectividad, pantalla, batería) usando\n"
        "ADB si hay un dispositivo conectado, o una consulta manual/offline\n"
        "si no es posible acceder por ADB.\n"
    )

    while True:
        print("\nMENÚ PRINCIPAL")
        print("1. Ejecutar análisis (ADB automático, con opción a modo manual)")
        print("2. Ver instrucciones para instalar adb en WSL")
        print("3. Ver instrucciones para activar la Depuración USB")
        print("4. Forzar Modo 2 (consulta manual / offline) directamente")
        print("5. Salir")

        opcion = input("\nSelecciona una opción (1-5): ").strip()

        if opcion == "1":
            reporte = ejecutar_analisis()
            mostrar_reporte(reporte)
            exportar_reporte(reporte)
        elif opcion == "2":
            mostrar_instrucciones_instalacion_adb()
        elif opcion == "3":
            mostrar_instrucciones_depuracion_usb()
        elif opcion == "4":
            reporte = analizar_via_api_o_offline()
            mostrar_reporte(reporte)
            exportar_reporte(reporte)
        elif opcion == "5":
            print("\n¡Hasta luego!")
            break
        else:
            print("\nOpción inválida. Intenta nuevamente.")


if __name__ == "__main__":
    try:
        menu_principal()
    except KeyboardInterrupt:
        print("\n\nPrograma interrumpido por el usuario. Saliendo...")
        sys.exit(0)
