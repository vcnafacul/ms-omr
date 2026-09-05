#!/bin/bash

set -e # se der erro, saia!

# Deploy do ms-omr em PRODUÇÃO. Mesmo script do homol, com duas diferenças:
#  - puxa a tag :stable (a que o ci-prod.yml publica no push de tag), não :latest;
#  - limites de memória maiores — prod é 2 vCPU / 8GB (homol é ~954MB).
# Vai pra `~/subir_ms_omr.sh` no servidor de PROD (mesmo nome que o ci-prod chama).

nome_image="vcnafacul/ms-omr:stable"
nome_container="vcnafacul_ms_omr"
nome_rede="network-vcnafacul"

# `|| true`: no primeiro deploy o container/imagem ainda não existem e o `set -e`
# abortaria o script antes do `docker run`.
docker rm -f $nome_container || true
docker rmi -f $nome_image || true

if docker network inspect $nome_rede >/dev/null 2>&1; then
	echo "A rede $nome_rede existe."
else
	docker network create $nome_rede
fi

# Prod tem folga (8GB). OMR_MAX_WORKERS=1 continua adequado: 2 núcleos, carga CPU-bound.
docker run --name $nome_container \
	--memory 2g --memory-swap 3g --cpus 1.5 \
	--restart unless-stopped \
	--env-file ./env/.env.omr \
	--network $nome_rede \
	-d $nome_image
