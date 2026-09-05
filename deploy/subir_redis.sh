#/!bin/bash

set -e # se der erro, saia!

# Provisiona um Redis na rede docker. HOJE HOMOL NÃO TEM REDIS (REDIS_HOST=localhost no
# .env do api aponta pra nada). O ms-omr precisa dele pra fila (arq) e o ms-simulado pra
# fila de respostas do callback do cartão. Leve, sem persistência (fila/cache são efêmeros).
# Depois de subir: aponte REDIS_HOST=vcnafacul_redis nos .env do api e do ms-simulado, e
# REDIS_URL=redis://vcnafacul_redis:6379/0 no .env.omr.

nome_image="redis:7-alpine"
nome_container="vcnafacul_redis"
nome_rede="network-vcnafacul"

if docker network inspect $nome_rede >/dev/null 2>&1; then
	echo "A rede $nome_rede existe."
else
	docker network create $nome_rede
fi

docker rm -f $nome_container || true

docker run --name $nome_container \
	--memory 80m --memory-swap 160m --cpus 0.3 \
	--restart unless-stopped \
	--network $nome_rede \
	-d $nome_image \
	redis-server --save "" --appendonly no --maxmemory 48mb --maxmemory-policy allkeys-lru
