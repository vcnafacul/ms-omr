#/!bin/bash

set -e # se der erro, saia!

# Deploy do ms-omr em homolog. Espelha o padrão de ~/subir_ms.sh (ms-simulado):
# remove container+imagem antigos, e `docker run` puxa a :latest do Docker Hub.
# Serviço INTERNO na rede docker (sem porta publicada): o ms-simulado o chama por
# http://vcnafacul_ms_omr:8000 (env OMR_URL do ms-simulado).

nome_image="vcnafacul/ms-omr:latest"
nome_container="vcnafacul_ms_omr"
nome_rede="network-vcnafacul"

docker rm -f $nome_container
docker rmi -f $nome_image

if docker network inspect $nome_rede >/dev/null 2>&1; then
	echo "A rede $nome_rede existe."
else
	docker network create $nome_rede
fi

# ⚠️ VM pequena (2 vCPU / ~1GB RAM). OMR (opencv/OMRChecker) é pesado — mantenha
# OMR_MAX_WORKERS=1 no ./env/.env.omr. Limites conservadores; ajuste se a VM crescer.
docker run --name $nome_container \
	--memory 450m --memory-swap 900m --cpus 1.0 \
	--restart unless-stopped \
	--env-file ./env/.env.omr \
	--network $nome_rede \
	-d $nome_image
