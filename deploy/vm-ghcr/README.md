# Despliegue VM sin codigo fuente

## Flujo unico (lo que debes recordar)

**En tu PC:** commit + push a `main` → espera Actions en verde.

**En la VM:**

```bash
cd ~/nilo-api
./update.sh
```

Eso hace todo:

1. Baja scripts actualizados desde GitHub (`bootstrap`, sin tocar `credentials.env`).
2. `docker pull` de la imagen GHCR y reinicia la API.

Alias equivalente: `./sync.sh`

No hace falta `./bootstrap.sh` a mano salvo recuperacion rara.

### Variantes (opcional)

```bash
./update.sh image     # solo nueva imagen API (mas rapido)
./update.sh scripts   # solo scripts de despliegue
./configure.sh        # credenciales Mongo/MinIO/host (1a vez)
```

## Primera vez en la VM

```bash
mkdir -p ~/nilo-api && cd ~/nilo-api
curl -fsSL https://raw.githubusercontent.com/NeoVisionsAI/NILO-backend/main/deploy/vm-ghcr/bootstrap.sh | bash
./configure.sh
docker login ghcr.io   # si GHCR privado
./update.sh
```

Documentacion: docs/07.ghcr_deploy.md
