# NILO backend

Backend de **NILO**, plataforma para la **monitorización integral de pacientes** (personas en camas, neonatos en incubadoras, niños, etc.).

Sistema software-hardware que registra, por paciente y correlacionado por `timestamp` (UTC):

- **Vídeo** de la grabación del paciente (troceado en chunks).
- **Landmarks corporales** extraídos del vídeo (MediaPipe / YOLO).
- **Parámetros fisiológicos** de monitores médicos (pulso, saturación y un conjunto variable de atributos).
- **Audio** (sonido ambiental o notas de voz), con opción de *speech-to-text*.
- **Eventos de dolor** (clip de vídeo del que se extraen landmarks faciales).
- **Documentos médicos** (informes, análisis...) — dominio preparado para el futuro.

## Stack

- **Python 3.13** + **FastAPI**
- **MongoDB** con **Beanie** (ODM async sobre el driver nativo `pymongo.AsyncMongoClient`) — esquema flexible para nuevas fuentes de datos
- **MinIO** (almacenamiento de objetos S3) para binarios (vídeo, audio, landmarks, documentos)
- **JWT** para autenticación y control de roles
- **Cifrado de datos de pacientes en reposo** (AES-256-GCM a nivel de aplicación + SSE en MinIO)

## Cifrado de datos (privacidad médica)

Los datos personales del paciente y el email de usuario se guardan **cifrados en MongoDB**: un volcado en crudo de la base de datos es ilegible sin la clave maestra.

- **Algoritmo:** AES-256-GCM (confidencialidad + integridad), a nivel de aplicación. De una clave maestra base64 (`ENCRYPTION_MASTER_KEY` en `credentials.env`) se derivan por HKDF una clave de cifrado y una clave HMAC independientes.
- **Tokens versionados** `enc:v1:<base64>` para permitir **rotación de claves** en el futuro.
- **Campos cifrados:** `Patient.full_name`, `medical_record_number`, `birth_date`, `notes` y `User.email`. En memoria siempre están en texto plano; solo se cifran al escribir en Mongo (vía `bson_encoders`) y se descifran al leer.
- **Búsqueda/unicidad (blind index):** para el login por email y la unicidad del nº de historia se almacena un HMAC-SHA256 determinista (`email_bidx`, `mrn_bidx`) que permite buscar sin exponer el valor. El dato real va cifrado con nonce aleatorio.
- **Binarios en MinIO:** cifrado en reposo mediante **SSE-S3** por defecto en el bucket (requiere KMS configurado en el servidor MinIO; ver `docker-compose.yml`). Se puede desactivar con `MINIO_SSE: false`.

> **IMPORTANTE:** perder `ENCRYPTION_MASTER_KEY` implica perder el acceso a los datos cifrados. Haz copia de seguridad de la clave en un gestor de secretos. El código de carga de claves (`app/core/crypto.py::_load_keys`) está aislado para poder integrar un KMS/Vault más adelante.

Genera claves nuevas con:

```bash
python -c "import base64,os; print(base64.b64encode(os.urandom(32)).decode())"
```

## Estrategia de vídeo (importante)

El vídeo 24/7 **no** se guarda como un fichero único. Se usa una estrategia **híbrida**:

- Segmentos cortos tipo **HLS** (`DEFAULT_HLS_SEGMENT_SECONDS`, por defecto 6s) para visualización en vivo.
- Chunks de **archivo** consolidados (`DEFAULT_VIDEO_CHUNK_SECONDS`, por defecto **300s / 5 min**) para almacenamiento y post-procesado.

El binario de cada chunk vive en **MinIO**; MongoDB solo guarda metadatos (`patient_id`, `start_ts`, `end_ts`, `object_key`, códec, resolución, estado...). El agente de captura sube los binarios **directamente a MinIO mediante presigned URLs**, de modo que FastAPI nunca hace de proxy de ficheros grandes.

**Flujo de subida (presigned):**

1. Se crea un `Recording` (sesión) para un paciente.
2. Por cada chunk se hace `POST /recordings/{id}/segments` con los metadatos → devuelve un `VideoSegment` (estado `pending_upload`) y una **presigned PUT URL**.
3. El agente sube el binario directamente a esa URL (MinIO).
4. Se confirma con `POST /recordings/segments/{segment_id}/confirm` → el backend verifica el objeto y marca `uploaded`.

El mismo patrón (upload → confirm → download) se usa para audio, eventos de dolor, landmarks y documentos médicos.

## Roles

- `root`: administrador supremo (gestión de usuarios).
- `healthcare_provider`: personal sanitario (crea pacientes, registra datos).
- `patient`: perfil de paciente.

`root` siempre tiene permiso. Al arrancar por primera vez se crea el usuario root definido por `ROOT_EMAIL` / `ROOT_PASSWORD`.

## Estructura del proyecto

```
app/
├── main.py                 # App FastAPI + lifespan (Mongo/MinIO/bootstrap root)
├── core/
│   ├── config.py           # Settings (config.yaml + credentials.env)
│   ├── security.py         # Hashing (bcrypt) + JWT
│   └── crypto.py           # AES-256-GCM + blind index (cifrado de datos)
├── db/
│   └── mongodb.py          # Conexión pymongo async + init Beanie
├── storage/
│   └── minio_client.py     # Cliente MinIO, presigned URLs, claves de objeto
├── models/                 # Documentos Beanie
│   ├── user.py, patient.py, recording.py, physiological.py,
│   ├── audio.py, pain_event.py, landmarks.py, medical_document.py
│   └── enums.py, base.py, fields.py (tipos cifrados)
├── schemas/                # Modelos Pydantic de request/response
└── api/
    ├── deps.py             # Auth + control de roles
    └── v1/
        ├── router.py       # Router agregado
        └── endpoints/      # auth, users, patients, recordings, physiological,
                            # audio, pain_events, landmarks, medical_documents
```

## Configuración

La configuración está separada en dos ficheros:

- **`config.yaml`** — ajustes **no sensibles** (nombres, puertos, bucket, tamaños de chunk, CORS, algoritmo JWT, expiraciones...). Se versiona y se incluye en la imagen Docker.
- **`credentials.env`** — **secretos** (URI de Mongo, claves de MinIO, `JWT_SECRET_KEY`, credenciales del root). **No se versiona** (está en `.gitignore`); parte de `credentials.env.example`.

**Precedencia** (de mayor a menor): variable de entorno > `credentials.env` > `config.yaml`. Por eso en Docker basta con inyectar overrides como variables de entorno.

Las rutas de ambos ficheros pueden cambiarse con `NILO_CONFIG_FILE` y `NILO_CREDENTIALS_FILE`.

```bash
cp credentials.env.example credentials.env   # y rellena los secretos
```

## Puesta en marcha

### Opción A — Docker Compose (Mongo + MinIO + API)

```bash
cp credentials.env.example credentials.env    # ajusta secretos
docker compose --env-file credentials.env up --build
```

> El flag `--env-file credentials.env` hace que los secretos estén disponibles tanto para la sustitución de variables del compose (MinIO) como dentro del contenedor de la API.

- API: http://localhost:8000 — docs en http://localhost:8000/docs
- MinIO API: http://localhost:9000 — consola: http://localhost:9001

Dentro de la red de contenedores, el compose sobreescribe `MONGODB_HOST` (`mongo`) y `MINIO_ENDPOINT` (`minio:9000`); el resto de la configuración viene de `config.yaml` (incluido en la imagen).

### MongoDB: provisión automática

La conexión a MongoDB se define por componentes en `config.yaml` (`MONGODB_HOST`, `MONGODB_PORT`, `MONGODB_DB`, usuarios admin/app) y las **contraseñas en `credentials.env`** (`MONGODB_ADMIN_PASSWORD`, `MONGODB_APP_PASSWORD`). Al arrancar, si `MONGODB_PROVISION: true`, la app:

1. Se conecta con las credenciales de **admin** (`MONGODB_ADMIN_USER`/`MONGODB_ADMIN_PASSWORD`, authSource `admin`).
2. Crea (o actualiza) el usuario de aplicación `MONGODB_APP_USER`/`MONGODB_APP_PASSWORD` con rol `readWrite` sobre la base de datos `MONGODB_DB`.
3. Reconecta como ese usuario de aplicación y trabaja siempre con esa base de datos.

En Docker, el servicio `mongo` arranca con `MONGO_INITDB_ROOT_USERNAME/PASSWORD` que **deben coincidir** con `MONGODB_ADMIN_*` de `config.yaml`.

> Las contraseñas de Mongo (`MONGODB_ADMIN_PASSWORD`, `MONGODB_APP_PASSWORD`) están en `credentials.env` (no versionado), no en `config.yaml`.

### Opción B — Local (con Mongo y MinIO ya disponibles)

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
cp credentials.env.example credentials.env    # ajusta MINIO_*, JWT_SECRET_KEY, ENCRYPTION_MASTER_KEY...
uvicorn app.main:app --reload
```

Puedes levantar solo las dependencias con: `docker compose up mongo minio`.

## Uso rápido de la API

```bash
# Login (usa el email en el campo username)
curl -X POST http://localhost:8000/api/v1/auth/login \
  -d "username=root@nilo.local&password=changeme"

# Con el token: crear un paciente
curl -X POST http://localhost:8000/api/v1/patients \
  -H "Authorization: Bearer <TOKEN>" -H "Content-Type: application/json" \
  -d '{"full_name":"Paciente 1","patient_type":"neonate"}'
```

La documentación interactiva completa (todos los endpoints) está en `/docs`.

## Próximos pasos (pendientes / futuro)

- Speech-to-text real para notas de voz.
- Pipeline de extracción de landmarks (MediaPipe/YOLO) desde los chunks de vídeo.
- Generación/consolidación de manifiestos HLS para *live view*.
- Índices compuestos y TTL/retención para datos de alta frecuencia.
- Tests automatizados.
