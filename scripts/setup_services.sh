#!/usr/bin/env bash

set -e

CONFIG_STORE=".env.services"

# Cargar credenciales guardadas previamente si existen
if [ -f "$CONFIG_STORE" ]; then
    # shellcheck disable=SC1090
    source "$CONFIG_STORE"
fi

# Comprobar privilegios de Docker
if ! docker info >/dev/null 2>&1; then
    echo "ERROR: No tienes permisos para ejecutar Docker."
    echo "Ejecuta el script con sudo: sudo ./setup_services.sh"
    exit 1
fi

echo "=========================================="
echo "    GESTIÓN DE SERVICIOS DOCKER           "
echo "        (MinIO y MongoDB)                 "
echo "=========================================="
echo "1) Configurar MinIO (host_minio)"
echo "2) Configurar MongoDB + Base de Datos (host_mongo)"
echo "3) Ver estado y logs de ambos servicios"
echo "4) Salir"
echo "=========================================="
read -rp "Selecciona una opción [1-4]: " OPTION

case $OPTION in
    1)
        echo ""
        echo "--- Configurando MinIO (host_minio) ---"
        
        # 1. Detectar volumen
        DATA_SOURCE=$(docker inspect host_minio --format '{{range .Mounts}}{{if eq .Destination "/data"}}{{.Source}}{{end}}{{end}}' 2>/dev/null || true)
        if [ -z "$DATA_SOURCE" ]; then
            DATA_SOURCE=$(docker inspect host_minio --format '{{range .Mounts}}{{.Source}}{{println}}{{end}}' 2>/dev/null | head -n 1)
        fi

        DEFAULT_MINIO_DIR="${DATA_SOURCE:-/opt/datos_nilo/minio}"
        read -rp "Directorio de datos en el host [$DEFAULT_MINIO_DIR]: " INPUT_MINIO_DIR
        DATA_SOURCE="${INPUT_MINIO_DIR:-$DEFAULT_MINIO_DIR}"
        mkdir -p "$DATA_SOURCE"

        # 2. Usuario
        DEFAULT_MINIO_USER="${SAVED_MINIO_USER:-admin}"
        read -rp "MINIO_ROOT_USER [$DEFAULT_MINIO_USER]: " INPUT_MUSER
        MINIO_USER="${INPUT_MUSER:-$DEFAULT_MINIO_USER}"

        # 3. Contraseña (mantiene la anterior si pulsas Intro)
        if [ -n "$SAVED_MINIO_PASS" ]; then
            read -rsp "MINIO_ROOT_PASSWORD [Pulsa INTRO para mantener la anterior]: " INPUT_MPASS
            echo ""
            MINIO_PASS="${INPUT_MPASS:-$SAVED_MINIO_PASS}"
        else
            read -rsp "MINIO_ROOT_PASSWORD (mínimo 8 caracteres): " MINIO_PASS
            echo ""
        fi

        if [ ${#MINIO_PASS} -lt 8 ]; then
            echo "Error: La contraseña debe tener al menos 8 caracteres."
            exit 1
        fi

        SAVED_MINIO_USER="$MINIO_USER"
        SAVED_MINIO_PASS="$MINIO_PASS"
        cat <<ENV_EOF > "$CONFIG_STORE"
SAVED_MINIO_USER="$SAVED_MINIO_USER"
SAVED_MINIO_PASS="$SAVED_MINIO_PASS"
SAVED_ROOT_USER="${SAVED_ROOT_USER:-admin}"
SAVED_ROOT_PASS="${SAVED_ROOT_PASS:-}"
SAVED_APP_DB="${SAVED_APP_DB:-nilo}"
SAVED_APP_USER="${SAVED_APP_USER:-nilo}"
SAVED_APP_PASS="${SAVED_APP_PASS:-}"
ENV_EOF
        chmod 600 "$CONFIG_STORE"

        echo "Deteniendo y eliminando contenedor host_minio previo..."
        docker stop host_minio 2>/dev/null || true
        docker rm host_minio 2>/dev/null || true

        echo "Lanzando contenedor host_minio..."
        docker run -d \
          --name host_minio \
          --restart unless-stopped \
          -p 9000:9000 \
          -p 9091:9090 \
          -e "MINIO_ROOT_USER=$MINIO_USER" \
          -e "MINIO_ROOT_PASSWORD=$MINIO_PASS" \
          -v "$DATA_SOURCE":/data \
          pgsty/minio:latest server /data --console-address ":9090"

        echo ""
        echo "✔ MinIO configurado correctamente:"
        echo "  - API: puerto 9000"
        echo "  - Consola Web: http://IP_DEL_SERVIDOR:9091"
        ;;

    2)
        echo ""
        echo "--- Configuración de MongoDB y Base de Datos ---"

        # 1. Directorio de datos
        DATA_SOURCE=$(docker inspect host_mongo --format '{{range .Mounts}}{{if eq .Destination "/data/db"}}{{.Source}}{{end}}{{end}}' 2>/dev/null || true)
        if [ -z "$DATA_SOURCE" ]; then
            DATA_SOURCE=$(docker inspect host_mongo --format '{{range .Mounts}}{{.Source}}{{println}}{{end}}' 2>/dev/null | head -n 1)
        fi

        DEFAULT_MONGO_DIR="${DATA_SOURCE:-/opt/datos_nilo/mongo}"
        read -rp "Directorio de datos en el host [$DEFAULT_MONGO_DIR]: " INPUT_MONGO_DIR
        DATA_SOURCE="${INPUT_MONGO_DIR:-$DEFAULT_MONGO_DIR}"
        mkdir -p "$DATA_SOURCE"

        # Comprobar si hay datos antiguos y ofrecer limpiarlos
        if [ -d "$DATA_SOURCE" ] && [ "$(ls -A "$DATA_SOURCE" 2>/dev/null)" ]; then
            echo ""
            echo "⚠  Se detectaron archivos previos en: $DATA_SOURCE"
            echo "   (Archivos de versiones anteriores pueden causar 'exitCode: 62')"
            read -rp "¿Deseas formatear/vaciar este directorio antes de arrancar? (s/N): " PURGE_DIR
            if [[ "$PURGE_DIR" =~ ^[Ss]$ ]]; then
                echo "Vaciando contenido de $DATA_SOURCE..."
                # Se usa rm dentro de un contenedor efímero si hay problemas de permisos con root
                docker run --rm -v "$DATA_SOURCE":/target alpine sh -c "rm -rf /target/* /target/.[!.]* /target/..?*" 2>/dev/null || rm -rf "${DATA_SOURCE:?}"/*
                echo "Directorio limpiado con éxito."
            else
                echo "Se mantendrán los archivos existentes."
            fi
        fi

        # 2. Credenciales ROOT
        echo ""
        echo "[1/3] Credenciales ROOT (Administrador global de Mongo):"
        DEFAULT_ROOT_USER="${SAVED_ROOT_USER:-admin}"
        read -rp "MONGO_ROOT_USERNAME [$DEFAULT_ROOT_USER]: " INPUT_RUSER
        ROOT_USER="${INPUT_RUSER:-$DEFAULT_ROOT_USER}"

        if [ -n "$SAVED_ROOT_PASS" ]; then
            read -rsp "MONGO_ROOT_PASSWORD [Pulsa INTRO para mantener la anterior]: " INPUT_RPASS
            echo ""
            ROOT_PASS="${INPUT_RPASS:-$SAVED_ROOT_PASS}"
        else
            read -rsp "MONGO_ROOT_PASSWORD: " ROOT_PASS
            echo ""
        fi

        # 3. Base de Datos y Usuario de la Aplicación
        echo ""
        echo "[2/3] Base de Datos y Usuario de la Aplicación:"
        DEFAULT_APP_DB="${SAVED_APP_DB:-nilo}"
        read -rp "Nombre de la base de datos [$DEFAULT_APP_DB]: " INPUT_ADB
        APP_DB="${INPUT_ADB:-$DEFAULT_APP_DB}"

        DEFAULT_APP_USER="${SAVED_APP_USER:-nilo}"
        read -rp "Usuario para '$APP_DB' [$DEFAULT_APP_USER]: " INPUT_AUSER
        APP_USER="${INPUT_AUSER:-$DEFAULT_APP_USER}"

        if [ -n "$SAVED_APP_PASS" ]; then
            read -rsp "Contraseña para el usuario '$APP_USER' [Pulsa INTRO para mantener la anterior]: " INPUT_APASS
            echo ""
            APP_PASS="${INPUT_APASS:-$SAVED_APP_PASS}"
        else
            read -rsp "Contraseña para el usuario '$APP_USER': " APP_PASS
            echo ""
        fi

        SAVED_ROOT_USER="$ROOT_USER"
        SAVED_ROOT_PASS="$ROOT_PASS"
        SAVED_APP_DB="$APP_DB"
        SAVED_APP_USER="$APP_USER"
        SAVED_APP_PASS="$APP_PASS"
        cat <<ENV_EOF > "$CONFIG_STORE"
SAVED_MINIO_USER="${SAVED_MINIO_USER:-admin}"
SAVED_MINIO_PASS="${SAVED_MINIO_PASS:-}"
SAVED_ROOT_USER="$SAVED_ROOT_USER"
SAVED_ROOT_PASS="$SAVED_ROOT_PASS"
SAVED_APP_DB="$SAVED_APP_DB"
SAVED_APP_USER="$SAVED_APP_USER"
SAVED_APP_PASS="$SAVED_APP_PASS"
ENV_EOF
        chmod 600 "$CONFIG_STORE"

        # 4. Detener, eliminar y relanzar contenedor
        echo ""
        echo "[3/3] Deteniendo contenedor antiguo y desplegando host_mongo..."
        docker stop host_mongo 2>/dev/null || true
        docker rm host_mongo 2>/dev/null || true

        docker run -d \
          --name host_mongo \
          --restart unless-stopped \
          -p 27017:27017 \
          -e "GLIBC_TUNABLES=glibc.pthread.rseq=1" \
          -e "MONGO_INITDB_ROOT_USERNAME=$ROOT_USER" \
          -e "MONGO_INITDB_ROOT_PASSWORD=$ROOT_PASS" \
          -v "$DATA_SOURCE":/data/db \
          mongo:latest

        echo "Esperando a que MongoDB inicie y acepte conexiones..."
        RETRIES=30
        until docker exec host_mongo mongosh -u "$ROOT_USER" -p "$ROOT_PASS" --authenticationDatabase "admin" --eval "db.adminCommand('ping')" >/dev/null 2>&1 || [ $RETRIES -eq 0 ]; do
            sleep 1
            RETRIES=$((RETRIES-1))
        done

        if [ $RETRIES -eq 0 ]; then
            echo "Error: MongoDB no logró arrancar. Mostrando logs:"
            docker logs --tail 25 host_mongo
            exit 1
        fi
        echo "MongoDB en línea y operativo."

        # 5. Comprobar si la base de datos ya existe
        DB_EXISTS=$(docker exec host_mongo mongosh -u "$ROOT_USER" -p "$ROOT_PASS" --authenticationDatabase "admin" --quiet --eval "db.getMongo().getDBNames().indexOf('$APP_DB') !== -1")

        if [ "$DB_EXISTS" = "true" ]; then
            echo ""
            echo "⚠  AVISO: La base de datos '$APP_DB' ya existe en MongoDB."
            read -rp "¿Deseas machacarla / eliminarla por completo? (s/N): " DROP_CONFIRM
            if [[ "$DROP_CONFIRM" =~ ^[Ss]$ ]]; then
                echo "Eliminando base de datos '$APP_DB'..."
                docker exec host_mongo mongosh -u "$ROOT_USER" -p "$ROOT_PASS" --authenticationDatabase "admin" --quiet --eval "db.getSiblingDB('$APP_DB').dropDatabase()"
                echo "Base de datos eliminada."
            else
                echo "Se conservan las colecciones existentes de '$APP_DB'."
            fi
        fi

        # 6. Asignar permisos al usuario de la app
        echo ""
        echo "Configurando permisos de lectura/escritura para '$APP_USER' en '$APP_DB'..."
        docker exec host_mongo mongosh -u "$ROOT_USER" -p "$ROOT_PASS" --authenticationDatabase "admin" --eval "
            var targetDb = db.getSiblingDB('$APP_DB');
            try { targetDb.dropUser('$APP_USER'); } catch(e) {}
            targetDb.createUser({
                user: '$APP_USER',
                pwd: '$APP_PASS',
                roles: [{ role: 'readWrite', db: '$APP_DB' }]
            });
            if (targetDb.getCollectionNames().length === 0) {
                targetDb.createCollection('_init_setup');
            }
        " >/dev/null

        echo ""
        echo "✔ MongoDB y base de datos configurados con éxito."
        echo "--------------------------------------------------------"
        echo "Cadena de conexión para tu backend:"
        echo "mongodb://$APP_USER:$APP_PASS@localhost:27017/$APP_DB?authSource=$APP_DB"
        echo "--------------------------------------------------------"
        ;;

    3)
        echo ""
        echo "=== ESTADO DE CONTENEDORES ==="
        docker ps -a --filter "name=host_minio" --filter "name=host_mongo"
        echo ""
        echo "=== ÚLTIMOS LOGS DE MINIO ==="
        docker logs --tail 10 host_minio 2>/dev/null || echo "No hay logs de host_minio"
        echo ""
        echo "=== ÚLTIMOS LOGS DE MONGO ==="
        docker logs --tail 10 host_mongo 2>/dev/null || echo "No hay logs de host_mongo"
        ;;

    4)
        echo "Saliendo..."
        exit 0
        ;;

    *)
        echo "Opción no válida."
        exit 1
        ;;
esac
