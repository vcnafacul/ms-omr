IMAGE      := vcnafacul/omr:dev
CONTAINER  := ms-omr
DOCKERFILE := omr.dockerfile
PORT       := 8000

.PHONY: up down logs

## up: build da imagem e sobe o container (detached) em localhost:8000
up:
	docker build -f $(DOCKERFILE) -t $(IMAGE) .
	-docker rm -f $(CONTAINER) 2>/dev/null
	docker run -d --rm --name $(CONTAINER) -p $(PORT):8000 $(IMAGE)
	@echo "ms-omr up → http://localhost:$(PORT)/health  |  http://localhost:$(PORT)/docs"

## down: para e remove o container
down:
	-docker stop $(CONTAINER)

## logs: acompanha os logs do container
logs:
	docker logs -f $(CONTAINER)
