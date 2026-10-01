# Despliegue VM sin código fuente

Solo **Docker**, estos ficheros y **`credentials.env`**. No hace falta `git clone`.

| Fichero | Uso |
|---------|-----|
| `compose.yaml` | Imagen GHCR + puertos |
| `credentials.env` | Secretos (crear desde `.example`) |
| `deploy.sh` | Pull + arranque; systemd al boot |

La app va **dentro de la imagen** `ghcr.io/neovisionsai/nilo-backend`.

> **`deploy.sh` corre en la VM (host), no dentro del contenedor.** El contenedor solo ejecuta la API (uvicorn). Al boot, systemd lanza `deploy.sh`, que hace `pull` y `docker compose up`.

## Primera vez

```bash
cp credentials.env.example credentials.env
# Editar: NILO_INFRA_HOST, Mongo, MinIO, JWT, ENCRYPTION_MASTER_KEY…

docker login ghcr.io   # paquete privado

chmod +x deploy.sh
./deploy.sh
sudo ./deploy.sh --install-systemd
```

Tras `--install-systemd`, cada **reinicio de la VM**: pull de la imagen (si hay red/login) y contenedor arriba.

## Actualizar versión

```bash
./deploy.sh
# o reiniciar servicio:
sudo systemctl restart nilo-api-vm
```

## Obtener el bundle sin clonar el repo

- **Actions → Publish API image (GHCR) → artefacto `nilo-vm-ghcr-deploy`**
- SCP/USB de la carpeta `deploy/vm-ghcr/`

Documentación: [`docs/07.ghcr_deploy.md`](../../docs/07.ghcr_deploy.md).
