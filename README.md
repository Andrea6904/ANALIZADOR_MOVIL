# Analizador de Características de Celular

Script PHP que analiza un teléfono Android y muestra sus características técnicas
(pantalla, sensores, conectividad, cámara y batería). Funciona en dos modos:

- **Modo 1 (ADB, preferido):** conecta el celular por USB con depuración activada
  y extrae datos reales del hardware.
- **Modo 2 (Offline / API):** si no hay `adb` o no hay dispositivo conectado, se
  puede consultar por marca y modelo contra una base de datos local
  (`dispositivos.json`) o, si se configura, contra una API externa.

Funciona tanto en **CLI** (`php index.php`) como en **servidor web** (Apache/Nginx
con PHP, o `php -S`).

## Requisitos

- PHP 8.0 o superior (con extensión `curl` si se desea usar una API externa).
- `adb` (Android Debug Bridge) — opcional, solo necesario para el Modo 1.

### Instalar ADB (Debian/Ubuntu)

```bash
sudo apt update
sudo apt install adb
# o, en distribuciones más antiguas:
sudo apt-get install android-tools-adb
```

Verifique la instalación con:

```bash
adb version
```

## Clonar el repositorio

```bash
git clone https://github.com/tu-usuario/analizador-celular.git
cd analizador-celular
```

## Activar la depuración USB en el celular Android

1. Abra **Ajustes** → **Acerca del teléfono**.
2. Toque 7 veces sobre **Número de compilación** hasta que aparezca el mensaje
   "Ya eres desarrollador".
3. Vuelva a **Ajustes** → **Sistema** → **Opciones de desarrollador**
   (en algunos fabricantes aparece directamente en Ajustes).
4. Active **Depuración USB**.
5. Conecte el celular a la PC por cable USB.
6. Cuando aparezca el diálogo "¿Permitir depuración USB?" en el celular,
   toque **Permitir** (puede marcar "Recordar siempre desde esta computadora").
7. Verifique la conexión desde la PC:

   ```bash
   adb devices
   ```

   Debería aparecer el número de serie del dispositivo seguido de `device`.

## Ejecutar en local

### Modo CLI

```bash
php index.php
```

El script detecta automáticamente si hay un celular conectado por ADB. Si no lo
hay, pregunta si desea usar el Modo 2 (offline), donde podrá ingresar marca y
modelo. Al finalizar, puede exportar el informe a `./reportes/`.

### Modo servidor web

Con el servidor embebido de PHP:

```bash
php -S localhost:8000
```

Luego abra `http://localhost:8000/index.php` en el navegador. La interfaz
muestra dos formularios: uno para analizar por ADB y otro para la consulta
offline por marca y modelo. Los informes exportados quedan disponibles para
descarga desde la misma página.

## Variables de entorno (API externa opcional)

Si desea usar una API pública de especificaciones técnicas en lugar (o además)
de la base de datos local, cree un archivo `.env` en la raíz del proyecto
(nunca incluya claves directamente en el código):

```env
DEVICE_SPECS_API_URL=https://api.ejemplo.com/v1/specs
DEVICE_SPECS_API_KEY=su_clave_secreta_aqui
```

Si estas variables no están definidas, o si la API falla, el script recurre
automáticamente a `dispositivos.json` (modo offline), generándolo con datos de
ejemplo la primera vez que se ejecuta.

## Base de datos local de ejemplo

`dispositivos.json` se crea automáticamente en la primera ejecución del Modo 2
si no existe, con especificaciones de ejemplo para:

- Samsung Galaxy S23
- Xiaomi Redmi Note 12
- Motorola Moto G84

Puede editar este archivo o agregar más dispositivos manualmente.

## Exportar informes

Al finalizar un análisis (por ADB o por consulta offline), el script permite
guardar el resultado en `./reportes/` en formato `.json` o `.txt`:

- En CLI: se pregunta al final si desea exportar y en qué formato.
- En web: aparece un formulario con un selector de formato y, tras exportar,
  un enlace de descarga.

La carpeta `reportes/` está excluida del control de versiones (ver `.gitignore`).

## Pruebas automatizadas con GitHub Actions (opcional)

Como `adb` requiere un dispositivo físico o un emulador, las pruebas
automatizadas en GitHub Actions solo pueden cubrir el **Modo 2 (offline)** y la
verificación de sintaxis PHP. Ejemplo de workflow (`.github/workflows/ci.yml`):

```yaml
name: CI

on: [push, pull_request]

jobs:
  test:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4

      - name: Configurar PHP
        uses: shivammathur/setup-php@v2
        with:
          php-version: '8.2'

      - name: Verificar sintaxis
        run: php -l index.php

      - name: Probar generación de base de datos local
        run: |
          php -r "
            define('CLI_TEST', true);
            require 'index.php';
          " || true
```

> Para pruebas con un dispositivo Android real emulado, se recomienda usar un
> runner con soporte de virtualización (por ejemplo, `reactivecircus/android-emulator-runner`)
> e instalar `adb` en el runner antes de ejecutar el script en Modo 1.

## Estructura del proyecto

```
analizador-celular/
├── index.php          # Script principal (CLI + web)
├── dispositivos.json  # Base de datos local (se genera automáticamente)
├── reportes/          # Informes exportados (ignorado por git)
├── .env               # Variables de entorno (opcional, no versionado)
├── .gitignore
└── README.md
```

## Notas técnicas

- El código sigue las convenciones **PSR-12**.
- No se usan frameworks externos; solo `cURL` (opcional) para la API externa.
- Las claves de API nunca se escriben en el código: se leen con `getenv()`
  desde un archivo `.env`.
- Compatible con PHP 8.0 en adelante.

## Licencia

MIT
