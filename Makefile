IMAGE_NAME      ?= titwsync
CONTAINER_FNAME ?= Containerfile
TASKRC          ?= $(HOME)/.taskrc
TASK_DATA       ?= $(HOME)/.task
TITWSYNC_CFG    ?= $(HOME)/.config/titwsync/titwsyncrc.yaml
ARGS            ?= --help
PODMAN_FLAGS    ?= -it

# Detect container engine.
# Prefer podman (real binary, not an alias) so we can apply SELinux volume
# labels (:Z). Fall back to docker, which does not use them.
_PODMAN := $(shell command -v podman 2>/dev/null)
ifneq ($(_PODMAN),)
  ENGINE      := podman
  VOLUME_OPTS := ,Z
else
  ENGINE      := docker
  VOLUME_OPTS :=
endif

# Allow `make run <cmd> [args...]` — extra words after "run" become the command.
# e.g. `make run count` runs `titwsync count`
#      `make run sync --apply` runs `titwsync sync --apply`
ifeq ($(firstword $(MAKECMDGOALS)),run)
  RUN_ARGS := $(wordlist 2,$(words $(MAKECMDGOALS)),$(MAKECMDGOALS))
  ifneq ($(RUN_ARGS),)
    $(eval $(RUN_ARGS):;@:)
  endif
endif

.PHONY: help build build-force run run-configure shell sync-dry sync _check-api-key _run-engine

help:
	@echo "Container engine: $(ENGINE)"
	@echo ""
	@echo "make build              - Build the container image"
	@echo "make build-force        - Rebuild without cache"
	@echo "make run [cmd [args]]   - Run a titwsync command (default: --help)"
	@echo "make run-configure      - Run titwsync configure (set project/tag mappings)"
	@echo "make sync-dry           - Two-way sync dry run"
	@echo "make sync               - Two-way sync (writes to both sides)"
	@echo "make shell              - Open a shell in the container (for debugging)"
	@echo ""
	@echo "Examples:"
	@echo "  make run sync"
	@echo "  make run import-v1"
	@echo "  make run sync --apply"
	@echo ""
	@echo "Required env:"
	@echo "  TODOIST_API_KEY - Set in environment before running"
	@echo ""
	@echo "Optional vars:"
	@echo "  TASKRC=$(TASKRC)"
	@echo "  TASK_DATA=$(TASK_DATA)"
	@echo "  TITWSYNC_CFG=$(TITWSYNC_CFG)"

build:
	@$(ENGINE) build -t $(IMAGE_NAME) --file=$(CONTAINER_FNAME) .

build-force:
	@$(ENGINE) build -t $(IMAGE_NAME) --file=$(CONTAINER_FNAME) --no-cache .

_run-engine:
	@$(ENGINE) run --rm $(PODMAN_FLAGS) \
		-v $(TASKRC):/root/.taskrc:ro$(VOLUME_OPTS) \
		-v $(TASK_DATA):/root/.task:rw$(VOLUME_OPTS) \
		-v $(TITWSYNC_CFG):/root/.config/titwsync/titwsyncrc.yaml:ro$(VOLUME_OPTS) \
		-e TODOIST_API_KEY="$(TODOIST_API_KEY)" \
		-e TASKDATA=/root/.task \
		-e HOME=/root \
		$(IMAGE_NAME) $(CMD)

run: _check-api-key
	@$(MAKE) --no-print-directory _run-engine CMD="$(if $(RUN_ARGS),$(RUN_ARGS),$(ARGS))"

run-configure: _check-api-key
	@$(MAKE) --no-print-directory _run-engine CMD="configure $(TODOIST_API_KEY)"

shell: _check-api-key
	@$(ENGINE) run --rm -it \
		--entrypoint /bin/bash \
		-v $(TASKRC):/root/.taskrc:ro$(VOLUME_OPTS) \
		-v $(TASK_DATA):/root/.task:rw$(VOLUME_OPTS) \
		-v $(TITWSYNC_CFG):/root/.config/titwsync/titwsyncrc.yaml:ro$(VOLUME_OPTS) \
		-e TODOIST_API_KEY="$(TODOIST_API_KEY)" \
		-e TASKDATA=/root/.task \
		-e HOME=/root \
		$(IMAGE_NAME)

sync-dry: _check-api-key
	@$(MAKE) --no-print-directory _run-engine CMD="sync"

sync: _check-api-key
	@$(MAKE) --no-print-directory _run-engine CMD="sync --apply"

_check-api-key:
	@if [ -z "$(TODOIST_API_KEY)" ]; then \
		echo "Error: TODOIST_API_KEY is not set"; \
		exit 1; \
	fi
