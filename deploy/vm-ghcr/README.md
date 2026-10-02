# Despliegue VM sin código fuente

Solo **Docker**, estos ficheros y **`credentials.env`**. No hace falta `git clone`.

| Fichero | Uso |
|---------|-----|
| `compose.yaml` | Imagen GHCR + puertos |
| `credentials.env` | Secretos (crear desde `.example`) |
| `configure.sh` | Menú interactivo → `credentials.env` |
| `deploy.sh` | Pull + arranque; systemd al boot |

La app va **dentro de la imagen** `ghcr.io/neovisionsai/nilo-backend`.

> **`deploy.sh` corre en la VM (host), no dentro del contenedor.** El contenedor solo ejecuta la API (uvicorn). Al boot, systemd lanza `deploy.sh`, que hace `pull` y `docker compose up`.

## Primera vez

```bash
chmod +x configure.sh deploy.sh
./configure.sh         # menú: credenciales + probar puertos/health
# o: cp credentials.env.example credentials.env && nano credentials.env

docker login ghcr.io   # paquete privado

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

**Instalación (una línea, repo público):**

```bash
mkdir -p ~/nilo-api && cd ~/nilo-api
curl -fsSL https://raw.githubusercontent.com/NeoVisionsAI/NILO-backend/main/deploy/vm-ghcr/bootstrap.sh | bash
```

Repo privado: exporta `GITHUB_TOKEN` (contenido `read`) antes del `curl`, o copia la carpeta por SCP.

## Qué actualizar y cuándo

| Cambio en GitHub | En la VM |
|------------------|----------|
| **Código de la API** (commit + push → Actions) | Solo `./deploy.sh` (`docker pull` + reinicio). **No** bajes ZIP ni bootstrap. |
| **Scripts de despliegue** (`deploy.sh`, `compose.yaml`, …) | `./bootstrap.sh` (vuelve a bajar solo esos ficheros). Pasa poco. |

- **Actions → artefacto `nilo-vm-ghcr-deploy`**: alternativa offline al bootstrap; no hace falta en cada push de código.

Documentación: [`docs/07.ghcr_deploy.md`](../../docs/07.ghcr_deploy.md).
