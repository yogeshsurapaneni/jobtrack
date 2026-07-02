# Makefile for JobTracker Application
# Defualt values for registry, image name, and tag. Can be overridden via environment variables.
REGISTRY ?= "contreg.theyogesh.top"
IMAGE_NAME ?= jobtracker
TAG ?= latest
FULL_IMAGE_NAME = $(REGISTRY)/$(IMAGE_NAME):$(TAG)

.PHONY: help build push login up down logs ps clean

help:
	@echo "Available commands:"
	@echo "  make build             - Build the Docker image locally"
	@echo "  make push              - Push the Docker image to the registry"
	@echo "  make login             - Log in to the Docker registry"
	@echo "  make up                - Start the entire local stack (Postgres, MinIO, Web)"
	@echo "  make down              - Stop the local stack"
	@echo "  make logs              - View streaming logs of the web service"
	@echo "  make ps                - View status of local running containers"
	@echo "  make clean             - Stop containers and remove volumes/temporary files"

build:
	@echo "Building Docker image: $(FULL_IMAGE_NAME)..."
	docker build -t $(FULL_IMAGE_NAME) .

push:
	@echo "Pushing Docker image: $(FULL_IMAGE_NAME)..."
	docker push $(FULL_IMAGE_NAME)

login:
	@echo "Logging in to registry $(REGISTRY)..."
	docker login $(REGISTRY)

up:
	@echo "Starting application stack in background..."
	docker compose up --build -d

down:
	@echo "Stopping application stack..."
	docker compose down

logs:
	docker compose logs -f web

ps:
	docker compose ps

clean:
	@echo "Stopping stack and deleting database & storage volumes..."
	docker compose down -v
	@find . -type d -name "__pycache__" -exec rm -rf {} +
	@find . -type f -name "*.pyc" -delete
