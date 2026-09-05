#!/bin/bash

set -e # se der erro, saia!

# Deploy do ms-omr em homolog. Espelha o padrão de ~/subir_ms.sh (ms-simulado):
# remove container+imagem antigos, e `docker run` puxa a :latest do Docker Hub.
# Serviço INTERNO na rede docker (sem porta publicada): o ms-simulado o chama por
# http://vcnafacul_ms_omr:8000 (env OMR_URL do ms-simulado).

nome_image="vcnafacul/ms-omr:latest"
nome_container="vcnafacul_ms_omr"
nome_rede="network-vcnafacul"

# `|| true`: no primeiro deploy o container/imagem ainda não existem e o `set -e`
# abortaria o script antes do `docker run` (visto no run #33983635736: `No such image`).
docker rm -f $nome_container || true
docker rmi -f $nome_image || true

if docker network inspect $nome_rede >/dev/null 2>&1; then
	echo "A rede $nome_rede existe."
else
	docker network create $nome_rede
fi

# Homol: VPS Hostinger, 4GB RAM / 1 vCPU. RAM sobra; a CPU é o recurso escasso —
# o OMR (opencv/OMRChecker) é CPU-bound e divide o único núcleo com api/ms-simulado.
# --cpus 0.75 evita que uma leitura monopolize a máquina; OMR_MAX_WORKERS=1 no ./env/.env.omr.
docker run --name $nome_container \
	--memory 1g --memory-swap 1500m --cpus 0.75 \
	--restart unless-stopped \
	--env-file ./env/.env.omr \
	--network $nome_rede \
	-d $nome_image
