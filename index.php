<?php

/**
 * Analizador de Características de Celular
 *
 * Funciona en dos modos:
 *  - Modo 1 (ADB): extrae datos reales de un celular Android conectado por USB.
 *  - Modo 2 (Offline/API): consulta una base de datos local (dispositivos.json)
 *    por marca y modelo cuando no hay ADB o no hay dispositivo conectado.
 *
 * Compatible con PHP 8.0+, ejecutable en CLI o en servidor web.
 * Sigue convenciones PSR-12.
 *
 * @author  Analizador de Celular
 * @license MIT
 */

declare(strict_types=1);

// ---------------------------------------------------------------------
// Constantes y utilidades generales
// ---------------------------------------------------------------------

const REPORTES_DIR = __DIR__ . '/reportes';
const DISPOSITIVOS_JSON = __DIR__ . '/dispositivos.json';

const CATEGORIAS = ['pantalla', 'sensores', 'conectividad', 'camara', 'bateria'];

/**
 * Determina si el script se ejecuta desde la línea de comandos.
 */
function esCli(): bool
{
    return PHP_SAPI === 'cli';
}

/**
 * Carga variables de entorno simples desde un archivo .env (si existe),
 * sin dependencias externas. No sobreescribe variables ya definidas.
 */
function cargarEnv(string $rutaEnv): void
{
    if (!is_readable($rutaEnv)) {
        return;
    }

    $lineas = file($rutaEnv, FILE_IGNORE_NEW_LINES | FILE_SKIP_EMPTY_LINES);
    if ($lineas === false) {
        return;
    }

    foreach ($lineas as $linea) {
        $linea = trim($linea);
        if ($linea === '' || str_starts_with($linea, '#') || !str_contains($linea, '=')) {
            continue;
        }
        [$clave, $valor] = array_map('trim', explode('=', $linea, 2));
        $valor = trim($valor, "\"'");
        if (getenv($clave) === false) {
            putenv("{$clave}={$valor}");
        }
    }
}

/**
 * Ejecuta un comando de shell de forma segura y devuelve su salida como texto.
 * Devuelve cadena vacía si el comando falla o no produce salida.
 */
function ejecutarComando(string $comando): string
{
    $descriptores = [
        0 => ['pipe', 'r'],
        1 => ['pipe', 'w'],
        2 => ['pipe', 'w'],
    ];

    $proceso = @proc_open($comando, $descriptores, $tuberias);
    if (!is_resource($proceso)) {
        return '';
    }

    fclose($tuberias[0]);
    $salida = stream_get_contents($tuberias[1]) ?: '';
    fclose($tuberias[1]);
    fclose($tuberias[2]);
    proc_close($proceso);

    return trim($salida);
}

/**
 * Verifica si un binario existe en el PATH del sistema.
 */
function comandoExiste(string $binario): bool
{
    $rutaVerificacion = stripos(PHP_OS, 'WIN') === 0 ? 'where' : 'which';
    $resultado = ejecutarComando("{$rutaVerificacion} {$binario} 2>/dev/null");
    return $resultado !== '';
}

// ---------------------------------------------------------------------
// Modo 1: Detección vía ADB
// ---------------------------------------------------------------------

/**
 * Verifica que adb esté instalado. Si no, devuelve instrucciones de instalación.
 *
 * @return array{disponible: bool, mensaje: string}
 */
function verificarAdbInstalado(): array
{
    if (comandoExiste('adb')) {
        return ['disponible' => true, 'mensaje' => ''];
    }

    $mensaje = "ADB (Android Debug Bridge) no está instalado en este sistema.\n"
        . "Para instalarlo en Debian/Ubuntu, ejecute uno de los siguientes comandos:\n"
        . "  sudo apt install adb\n"
        . "  sudo apt-get install android-tools-adb\n";

    return ['disponible' => false, 'mensaje' => $mensaje];
}

/**
 * Obtiene la lista de dispositivos Android conectados y autorizados vía ADB.
 *
 * @return string[] Lista de identificadores de serie de dispositivos "device".
 */
function obtenerDispositivosAdb(): array
{
    $salida = ejecutarComando('adb devices 2>/dev/null');
    $lineas = explode("\n", $salida);
    $dispositivos = [];

    foreach ($lineas as $linea) {
        $linea = trim($linea);
        if ($linea === '' || str_starts_with($linea, 'List of devices')) {
            continue;
        }
        if (preg_match('/^(\S+)\s+device$/', $linea, $coincidencias)) {
            $dispositivos[] = $coincidencias[1];
        }
    }

    return $dispositivos;
}

/**
 * Ejecuta un comando `adb shell` sobre un dispositivo específico.
 */
function adbShell(string $serie, string $comando): string
{
    $serieEscapada = escapeshellarg($serie);
    return ejecutarComando("adb -s {$serieEscapada} shell {$comando} 2>/dev/null");
}

/**
 * Parsea la salida de `getprop` en un arreglo clave => valor.
 */
function parsearGetprop(string $salida): array
{
    $propiedades = [];
    foreach (explode("\n", $salida) as $linea) {
        if (preg_match('/^\[(.+?)\]:\s*\[(.*)\]$/', trim($linea), $coincidencias)) {
            $propiedades[$coincidencias[1]] = $coincidencias[2];
        }
    }
    return $propiedades;
}

/**
 * Determina la lista de sensores presentes a partir de `dumpsys sensorservice`.
 *
 * @return string[]
 */
function parsearSensores(string $salida): array
{
    $sensoresDetectados = [];
    $patronesConocidos = [
        'Accelerometer'       => 'Acelerómetro',
        'Gyroscope'           => 'Giroscopio',
        'Magnetic Field'      => 'Brújula / Magnetómetro',
        'Orientation'         => 'Sensor de orientación',
        'Proximity'           => 'Proximidad',
        'Light'               => 'Sensor de luz',
        'Pressure'            => 'Barómetro',
        'Gravity'             => 'Gravedad',
        'Linear Acceleration' => 'Aceleración lineal',
        'Rotation Vector'     => 'Vector de rotación',
        'Step Counter'        => 'Contador de pasos',
        'Step Detector'       => 'Detector de pasos',
        'Heart Rate'          => 'Ritmo cardíaco',
        'Fingerprint'         => 'Huella digital (sensor)',
    ];

    foreach ($patronesConocidos as $clave => $nombre) {
        if (stripos($salida, $clave) !== false) {
            $sensoresDetectados[] = $nombre;
        }
    }

    return $sensoresDetectados;
}

/**
 * Determina características de hardware a partir de `pm list features`.
 *
 * @return array<string, bool>
 */
function parsearCaracteristicasHardware(string $salida): array
{
    return [
        'NFC'               => stripos($salida, 'android.hardware.nfc') !== false,
        'Huella digital'    => stripos($salida, 'android.hardware.fingerprint') !== false,
        'Cámara'            => stripos($salida, 'android.hardware.camera') !== false,
        'Cámara frontal'    => stripos($salida, 'android.hardware.camera.front') !== false,
        'Flash de cámara'   => stripos($salida, 'android.hardware.camera.flash') !== false,
        'Bluetooth'         => stripos($salida, 'android.hardware.bluetooth') !== false,
        'WiFi'              => stripos($salida, 'android.hardware.wifi') !== false,
        'GPS'               => stripos($salida, 'android.hardware.location.gps') !== false,
        'Giroscopio (HAL)'  => stripos($salida, 'android.hardware.sensor.gyroscope') !== false,
        'Telefonía (SIM)'   => stripos($salida, 'android.hardware.telephony') !== false,
        'USB Host'          => stripos($salida, 'android.hardware.usb.host') !== false,
        'Sensor de huella'  => stripos($salida, 'android.hardware.fingerprint') !== false,
    ];
}

/**
 * Recolecta toda la información de un dispositivo conectado vía ADB
 * y la organiza por categorías.
 *
 * @return array<string, mixed>
 */
function recolectarInformacionAdb(string $serie): array
{
    $propiedades = parsearGetprop(adbShell($serie, 'getprop'));
    $sensoresRaw = adbShell($serie, 'dumpsys sensorservice');
    $featuresRaw = adbShell($serie, 'pm list features');
    $tamanoPantalla = adbShell($serie, 'wm size');
    $densidadPantalla = adbShell($serie, 'wm density');

    $modelo = $propiedades['ro.product.model'] ?? 'Desconocido';
    $marca = $propiedades['ro.product.brand'] ?? $propiedades['ro.product.manufacturer'] ?? 'Desconocida';
    $versionAndroid = $propiedades['ro.build.version.release'] ?? 'Desconocida';
    $sdk = $propiedades['ro.build.version.sdk'] ?? 'Desconocido';

    preg_match('/Physical size:\s*(\d+x\d+)/', $tamanoPantalla, $coincResolucion);
    preg_match('/Physical density:\s*(\d+)/', $densidadPantalla, $coincDensidad);

    $caracteristicas = parsearCaracteristicasHardware($featuresRaw);

    return [
        'origen' => 'adb',
        'modelo' => "{$marca} {$modelo}",
        'android' => "Android {$versionAndroid} (SDK {$sdk})",
        'pantalla' => [
            'Resolución' => $coincResolucion[1] ?? 'No disponible',
            'Densidad (dpi)' => $coincDensidad[1] ?? 'No disponible',
        ],
        'sensores' => parsearSensores($sensoresRaw) ?: ['No se detectaron sensores'],
        'conectividad' => [
            'NFC' => $caracteristicas['NFC'] ? 'Sí' : 'No',
            'Bluetooth' => $caracteristicas['Bluetooth'] ? 'Sí' : 'No',
            'WiFi' => $caracteristicas['WiFi'] ? 'Sí' : 'No',
            'GPS' => $caracteristicas['GPS'] ? 'Sí' : 'No',
            'Telefonía (SIM)' => $caracteristicas['Telefonía (SIM)'] ? 'Sí' : 'No',
            'USB Host' => $caracteristicas['USB Host'] ? 'Sí' : 'No',
        ],
        'camara' => [
            'Cámara trasera' => $caracteristicas['Cámara'] ? 'Sí' : 'No',
            'Cámara frontal' => $caracteristicas['Cámara frontal'] ? 'Sí' : 'No',
            'Flash' => $caracteristicas['Flash de cámara'] ? 'Sí' : 'No',
        ],
        'bateria' => [
            'Nota' => 'El nivel de batería en tiempo real requiere "adb shell dumpsys battery"',
        ],
        'lector_huella' => $caracteristicas['Huella digital'] ? 'Sí' : 'No',
    ];
}

// ---------------------------------------------------------------------
// Modo 2: Consulta offline / base de datos local
// ---------------------------------------------------------------------

/**
 * Genera un archivo dispositivos.json de ejemplo si no existe,
 * simulando una base de datos de especificaciones técnicas.
 */
function asegurarBaseDeDatosLocal(): void
{
    if (file_exists(DISPOSITIVOS_JSON)) {
        return;
    }

    $datosEjemplo = [
        'samsung galaxy s23' => [
            'modelo' => 'Samsung Galaxy S23',
            'android' => 'Android 14',
            'pantalla' => ['Resolución' => '2340x1080', 'Tamaño' => '6.1 pulgadas'],
            'sensores' => ['Acelerómetro', 'Giroscopio', 'Brújula / Magnetómetro', 'Proximidad', 'Sensor de luz'],
            'conectividad' => ['NFC' => 'Sí', 'Bluetooth' => 'Sí', 'WiFi' => 'Sí', 'GPS' => 'Sí'],
            'camara' => ['Cámara trasera' => '50 MP', 'Cámara frontal' => '12 MP', 'Flash' => 'Sí'],
            'bateria' => ['Capacidad' => '3900 mAh'],
            'lector_huella' => 'Sí (bajo pantalla)',
        ],
        'xiaomi redmi note 12' => [
            'modelo' => 'Xiaomi Redmi Note 12',
            'android' => 'Android 12 (MIUI 13)',
            'pantalla' => ['Resolución' => '2400x1080', 'Tamaño' => '6.67 pulgadas'],
            'sensores' => ['Acelerómetro', 'Giroscopio', 'Proximidad', 'Sensor de luz'],
            'conectividad' => ['NFC' => 'No', 'Bluetooth' => 'Sí', 'WiFi' => 'Sí', 'GPS' => 'Sí'],
            'camara' => ['Cámara trasera' => '48 MP', 'Cámara frontal' => '13 MP', 'Flash' => 'Sí'],
            'bateria' => ['Capacidad' => '5000 mAh'],
            'lector_huella' => 'Sí (lateral)',
        ],
        'motorola moto g84' => [
            'modelo' => 'Motorola Moto G84',
            'android' => 'Android 13',
            'pantalla' => ['Resolución' => '2400x1080', 'Tamaño' => '6.5 pulgadas'],
            'sensores' => ['Acelerómetro', 'Giroscopio', 'Proximidad', 'Sensor de luz'],
            'conectividad' => ['NFC' => 'Sí', 'Bluetooth' => 'Sí', 'WiFi' => 'Sí', 'GPS' => 'Sí'],
            'camara' => ['Cámara trasera' => '50 MP', 'Cámara frontal' => '16 MP', 'Flash' => 'Sí'],
            'bateria' => ['Capacidad' => '5000 mAh'],
            'lector_huella' => 'Sí (bajo pantalla)',
        ],
    ];

    file_put_contents(DISPOSITIVOS_JSON, json_encode($datosEjemplo, JSON_PRETTY_PRINT | JSON_UNESCAPED_UNICODE));
}

/**
 * Busca un dispositivo por marca y modelo en la API pública configurada
 * (si hay una API key en el entorno) o, en su defecto, en la base local.
 *
 * @return array<string, mixed>|null
 */
function buscarDispositivo(string $marca, string $modelo): ?array
{
    $apiKey = getenv('DEVICE_SPECS_API_KEY');
    $apiUrl = getenv('DEVICE_SPECS_API_URL');

    if ($apiKey !== false && $apiUrl !== false && $apiUrl !== '') {
        $resultado = consultarApiExterna($apiUrl, $apiKey, $marca, $modelo);
        if ($resultado !== null) {
            return $resultado;
        }
        // Si la API falla, se continúa con el modo offline como respaldo.
    }

    asegurarBaseDeDatosLocal();
    $contenido = file_get_contents(DISPOSITIVOS_JSON);
    $baseDatos = json_decode($contenido ?: '{}', true) ?: [];

    $clave = strtolower(trim("{$marca} {$modelo}"));
    if (isset($baseDatos[$clave])) {
        $datos = $baseDatos[$clave];
        $datos['origen'] = 'offline';
        return $datos;
    }

    return null;
}

/**
 * Realiza una consulta a una API externa de especificaciones técnicas.
 * La URL y la clave se leen de variables de entorno, nunca hardcodeadas.
 *
 * @return array<string, mixed>|null
 */
function consultarApiExterna(string $apiUrl, string $apiKey, string $marca, string $modelo): ?array
{
    if (!function_exists('curl_init')) {
        return null;
    }

    $consulta = http_build_query(['brand' => $marca, 'model' => $modelo]);
    $curl = curl_init("{$apiUrl}?{$consulta}");

    curl_setopt_array($curl, [
        CURLOPT_RETURNTRANSFER => true,
        CURLOPT_TIMEOUT => 8,
        CURLOPT_HTTPHEADER => ["Authorization: Bearer {$apiKey}"],
    ]);

    $respuesta = curl_exec($curl);
    $codigoHttp = curl_getinfo($curl, CURLINFO_HTTP_CODE);
    curl_close($curl);

    if ($respuesta === false || $codigoHttp !== 200) {
        return null;
    }

    $datos = json_decode($respuesta, true);
    if (!is_array($datos)) {
        return null;
    }

    $datos['origen'] = 'api';
    return $datos;
}

// ---------------------------------------------------------------------
// Presentación de resultados
// ---------------------------------------------------------------------

/**
 * Verifica si un arreglo es una lista secuencial (compatible con PHP 8.0,
 * donde array_is_list() todavía no existe).
 */
function esListaSecuencial(array $arreglo): bool
{
    if (function_exists('array_is_list')) {
        return array_is_list($arreglo);
    }
    return $arreglo === array_values($arreglo);
}

/**
 * Aplana un arreglo de información en filas [categoría, clave, valor]
 * para presentación tabular.
 *
 * @return array<int, array{0: string, 1: string, 2: string}>
 */
function aplanarInformacion(array $info): array
{
    $filas = [];
    $etiquetasCategorias = [
        'pantalla' => 'Pantalla',
        'sensores' => 'Sensores',
        'conectividad' => 'Conectividad',
        'camara' => 'Cámara',
        'bateria' => 'Batería',
    ];

    foreach ($etiquetasCategorias as $clave => $etiqueta) {
        if (!isset($info[$clave])) {
            continue;
        }
        $valor = $info[$clave];
        if (is_array($valor)) {
            $esLista = esListaSecuencial($valor);
            foreach ($valor as $k => $v) {
                $nombreCampo = $esLista ? ('Sensor detectado') : (string) $k;
                $filas[] = [$etiqueta, $nombreCampo, (string) $v];
            }
        } else {
            $filas[] = [$etiqueta, $etiqueta, (string) $valor];
        }
    }

    if (isset($info['lector_huella'])) {
        $filas[] = ['Sensores', 'Lector de huella', (string) $info['lector_huella']];
    }

    return $filas;
}

/**
 * Imprime los resultados como tabla de texto simple en CLI usando str_pad().
 */
function imprimirTablaCli(array $info): void
{
    $anchoCategoria = 15;
    $anchoCampo = 25;
    $anchoValor = 35;

    echo "\n";
    echo "Dispositivo: " . ($info['modelo'] ?? 'Desconocido') . "\n";
    if (isset($info['android'])) {
        echo "Sistema: " . $info['android'] . "\n";
    }
    echo "Origen de datos: " . strtoupper($info['origen'] ?? 'desconocido') . "\n\n";

    echo str_pad('Categoría', $anchoCategoria)
        . str_pad('Campo', $anchoCampo)
        . str_pad('Valor', $anchoValor) . "\n";
    echo str_repeat('-', $anchoCategoria + $anchoCampo + $anchoValor) . "\n";

    foreach (aplanarInformacion($info) as [$categoria, $campo, $valor]) {
        echo str_pad($categoria, $anchoCategoria)
            . str_pad($campo, $anchoCampo)
            . str_pad($valor, $anchoValor) . "\n";
    }
    echo "\n";
}

/**
 * Genera la tabla de resultados en HTML básico.
 */
function generarTablaHtml(array $info): string
{
    $modelo = htmlspecialchars((string) ($info['modelo'] ?? 'Desconocido'), ENT_QUOTES, 'UTF-8');
    $android = htmlspecialchars((string) ($info['android'] ?? ''), ENT_QUOTES, 'UTF-8');
    $origen = htmlspecialchars(strtoupper((string) ($info['origen'] ?? 'desconocido')), ENT_QUOTES, 'UTF-8');

    $filasHtml = '';
    foreach (aplanarInformacion($info) as [$categoria, $campo, $valor]) {
        $filasHtml .= '<tr><td>' . htmlspecialchars($categoria, ENT_QUOTES, 'UTF-8') . '</td>'
            . '<td>' . htmlspecialchars($campo, ENT_QUOTES, 'UTF-8') . '</td>'
            . '<td>' . htmlspecialchars($valor, ENT_QUOTES, 'UTF-8') . '</td></tr>';
    }

    return <<<HTML
        <h2>{$modelo}</h2>
        <p><strong>Sistema:</strong> {$android} &mdash; <strong>Origen de datos:</strong> {$origen}</p>
        <table border="1" cellpadding="6" cellspacing="0">
            <thead>
                <tr><th>Categoría</th><th>Campo</th><th>Valor</th></tr>
            </thead>
            <tbody>
                {$filasHtml}
            </tbody>
        </table>
        HTML;
}

// ---------------------------------------------------------------------
// Exportación de informes
// ---------------------------------------------------------------------

/**
 * Guarda el resultado del análisis como archivo .json (y opcionalmente .txt)
 * dentro de la carpeta ./reportes.
 */
function exportarInforme(array $info, string $formato = 'json'): string
{
    if (!is_dir(REPORTES_DIR)) {
        mkdir(REPORTES_DIR, 0755, true);
    }

    $nombreBase = 'analisis_celular_' . date('Ymd_His');

    if ($formato === 'txt') {
        $ruta = REPORTES_DIR . "/{$nombreBase}.txt";
        $contenido = "Dispositivo: " . ($info['modelo'] ?? 'Desconocido') . "\n";
        $contenido .= "Sistema: " . ($info['android'] ?? '') . "\n";
        $contenido .= "Origen: " . ($info['origen'] ?? '') . "\n\n";
        foreach (aplanarInformacion($info) as [$categoria, $campo, $valor]) {
            $contenido .= "[{$categoria}] {$campo}: {$valor}\n";
        }
        file_put_contents($ruta, $contenido);
        return $ruta;
    }

    $ruta = REPORTES_DIR . "/{$nombreBase}.json";
    file_put_contents($ruta, json_encode($info, JSON_PRETTY_PRINT | JSON_UNESCAPED_UNICODE));
    return $ruta;
}

// ---------------------------------------------------------------------
// Flujo CLI
// ---------------------------------------------------------------------

function ejecutarFlujoCli(): void
{
    echo "=== Analizador de Características de Celular ===\n\n";

    $estadoAdb = verificarAdbInstalado();
    $info = null;

    if ($estadoAdb['disponible']) {
        $dispositivos = obtenerDispositivosAdb();

        if (count($dispositivos) > 0) {
            echo "Dispositivo(s) detectado(s) vía ADB. Analizando...\n";
            $info = recolectarInformacionAdb($dispositivos[0]);
        } else {
            echo "No se detectó ningún celular conectado con depuración USB activada.\n";
            echo "Verifique que el cable esté conectado y que haya aceptado la autorización ADB en el teléfono.\n\n";
        }
    } else {
        echo $estadoAdb['mensaje'] . "\n";
    }

    if ($info === null) {
        echo "¿Desea usar el Modo 2 (consulta offline por marca y modelo)? [s/n]: ";
        $respuesta = strtolower(trim((string) readline()));

        if ($respuesta === 's' || $respuesta === 'si') {
            echo "Marca del celular (ej. Samsung): ";
            $marca = trim((string) readline());
            echo "Modelo del celular (ej. Galaxy S23): ";
            $modelo = trim((string) readline());

            $info = buscarDispositivo($marca, $modelo);

            if ($info === null) {
                echo "\nNo se encontró información para \"{$marca} {$modelo}\" en la base de datos local ni en la API.\n";
                echo "Pruebe con: Samsung Galaxy S23, Xiaomi Redmi Note 12 o Motorola Moto G84.\n";
                return;
            }
        } else {
            echo "Análisis cancelado.\n";
            return;
        }
    }

    imprimirTablaCli($info);

    echo "¿Desea exportar este informe? [json/txt/n]: ";
    $formato = strtolower(trim((string) readline()));

    if ($formato === 'json' || $formato === 'txt') {
        $ruta = exportarInforme($info, $formato);
        echo "Informe guardado en: {$ruta}\n";
    }
}

// ---------------------------------------------------------------------
// Flujo Web
// ---------------------------------------------------------------------

function ejecutarFlujoWeb(): void
{
    $estadoAdb = verificarAdbInstalado();
    $info = null;
    $mensajeError = '';
    $modoUsado = '';

    // Exportación directa vía GET (descarga de un informe ya generado).
    if (isset($_GET['descargar'])) {
        $archivo = basename((string) $_GET['descargar']);
        $ruta = REPORTES_DIR . '/' . $archivo;
        if (is_file($ruta) && str_starts_with(realpath($ruta) ?: '', realpath(REPORTES_DIR) ?: '')) {
            header('Content-Type: application/octet-stream');
            header('Content-Disposition: attachment; filename="' . $archivo . '"');
            readfile($ruta);
            exit;
        }
    }

    if (isset($_POST['accion']) && $_POST['accion'] === 'analizar_adb') {
        if ($estadoAdb['disponible']) {
            $dispositivos = obtenerDispositivosAdb();
            if (count($dispositivos) > 0) {
                $info = recolectarInformacionAdb($dispositivos[0]);
                $modoUsado = 'adb';
            } else {
                $mensajeError = 'No se detectó ningún celular conectado con depuración USB activada. '
                    . 'Verifique el cable y la autorización ADB en el teléfono.';
            }
        } else {
            $mensajeError = $estadoAdb['mensaje'];
        }
    } elseif (isset($_POST['accion']) && $_POST['accion'] === 'analizar_offline') {
        $marca = trim((string) ($_POST['marca'] ?? ''));
        $modelo = trim((string) ($_POST['modelo'] ?? ''));

        if ($marca === '' || $modelo === '') {
            $mensajeError = 'Debe ingresar marca y modelo.';
        } else {
            $info = buscarDispositivo($marca, $modelo);
            $modoUsado = 'offline';
            if ($info === null) {
                $mensajeError = "No se encontró información para \"{$marca} {$modelo}\". "
                    . 'Pruebe con: Samsung Galaxy S23, Xiaomi Redmi Note 12 o Motorola Moto G84.';
            }
        }
    }

    $archivoExportado = null;
    if ($info !== null && isset($_POST['exportar'])) {
        $formato = $_POST['exportar'] === 'txt' ? 'txt' : 'json';
        $rutaCompleta = exportarInforme($info, $formato);
        $archivoExportado = basename($rutaCompleta);
    }

    $tablaHtml = $info !== null ? generarTablaHtml($info) : '';
    $adbDisponibleTexto = $estadoAdb['disponible'] ? 'Sí' : 'No (' . nl2br(htmlspecialchars($estadoAdb['mensaje'], ENT_QUOTES, 'UTF-8')) . ')';

    echo <<<HTML
        <!DOCTYPE html>
        <html lang="es">
        <head>
            <meta charset="UTF-8">
            <title>Analizador de Características de Celular</title>
            <style>
                body { font-family: Arial, sans-serif; max-width: 800px; margin: 2rem auto; padding: 0 1rem; }
                table { border-collapse: collapse; width: 100%; margin-top: 1rem; }
                th, td { text-align: left; padding: 6px 10px; }
                fieldset { margin-bottom: 1.5rem; }
                .error { color: #b00020; }
                .estado { font-size: 0.9rem; color: #555; }
            </style>
        </head>
        <body>
            <h1>Analizador de Características de Celular</h1>
            <p class="estado">Estado de ADB: {$adbDisponibleTexto}</p>

            <fieldset>
                <legend>Modo 1: Analizar por ADB (USB)</legend>
                <form method="post">
                    <input type="hidden" name="accion" value="analizar_adb">
                    <button type="submit">Analizar celular conectado</button>
                </form>
            </fieldset>

            <fieldset>
                <legend>Modo 2: Consulta offline por marca y modelo</legend>
                <form method="post">
                    <input type="hidden" name="accion" value="analizar_offline">
                    <label>Marca: <input type="text" name="marca" placeholder="Samsung"></label><br><br>
                    <label>Modelo: <input type="text" name="modelo" placeholder="Galaxy S23"></label><br><br>
                    <button type="submit">Consultar</button>
                </form>
            </fieldset>
        HTML;

    if ($mensajeError !== '') {
        echo '<p class="error">' . nl2br(htmlspecialchars($mensajeError, ENT_QUOTES, 'UTF-8')) . '</p>';
    }

    if ($info !== null) {
        echo $tablaHtml;
        echo <<<HTML
            <form method="post" style="margin-top:1rem;">
                <input type="hidden" name="accion" value="{$modoUsado}">
                <label>Exportar como:
                    <select name="exportar">
                        <option value="json">JSON</option>
                        <option value="txt">TXT</option>
                    </select>
                </label>
                <button type="submit">Exportar informe</button>
            </form>
            HTML;
    }

    if ($archivoExportado !== null) {
        $enlace = '?descargar=' . urlencode($archivoExportado);
        echo '<p>Informe generado: <a href="' . htmlspecialchars($enlace, ENT_QUOTES, 'UTF-8') . '">'
            . htmlspecialchars($archivoExportado, ENT_QUOTES, 'UTF-8') . '</a></p>';
    }

    echo "</body></html>";
}

// ---------------------------------------------------------------------
// Punto de entrada
// ---------------------------------------------------------------------

cargarEnv(__DIR__ . '/.env');

if (esCli()) {
    ejecutarFlujoCli();
} else {
    ejecutarFlujoWeb();
}
