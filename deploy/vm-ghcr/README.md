# Despliegue VM sin codigo fuente

Solo Docker, scripts en esta carpeta y credentials.env. No hace falta git clone del backend.

La aplicacion va dentro de la imagen ghcr.io/neovisionsai/nilo-backend.

## Primera vez en la VM

```bash
mkdir -p ~/nilo-api && cd ~/nilo-api
curl -fsSL https://raw.githubusercontent.com/NeoVisionsAI/NILO-backend/main/deploy/vm-ghcr/bootstrap.sh | bash

chmod +x configure.sh update.sh deploy.sh
./configure.sh
docker login ghcr.io   # si el paquete GHCR es privado
./deploy.sh
```

Opcional arranque al boot: sudo ./deploy.sh --install-systemd

## Tras commit + push (sin subir ficheros a mano)

En GitHub: Actions en verde (imagen nueva).

En la VM, desde ~/nilo-api:

```bash
./update.sh image
```

Eso hace docker pull y reinicia el contenedor. Es lo habitual cuando solo cambia codigo de la API.

Si en el repo cambiaste scripts de despliegue (deploy.sh, configure.sh, compose.yaml):

```bash
./update.sh scripts
```

Ambos (scripts + imagen):

```bash
./update.sh
```

Equivalente manual:

- ./bootstrap.sh  = pull de scripts desde main (raw GitHub)
- ./deploy.sh     = pull de imagen GHCR

credentials.env no se sobrescribe con bootstrap.

## Recuperar bootstrap roto (una linea, sin scp)

```bash
cd ~/nilo-api
curl -fsSL https://raw.githubusercontent.com/NeoVisionsAI/NILO-backend/main/deploy/vm-ghcr/bootstrap.sh -o bootstrap.sh
chmod +x bootstrap.sh
./bootstrap.sh
```

Requiere que deploy/vm-ghcr este en la rama main del repo remoto.

Documentacion: docs/07.ghcr_deploy.md
