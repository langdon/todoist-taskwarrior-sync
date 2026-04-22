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

.PHONY: help build build-force run sync-dry sync _check-api-key

help:
	@echo "Container engine: $(ENGINE)"
	@echo ""
	@echo "make build        - Build the container image"
	@echo "make build-force  - Rebuild without cache"
	@echo "make run          - Run with custom ARGS (default: --help)"
	@echo "make sync-dry     - Two-way sync dry run"
	@echo "make sync         - Two-way sync (writes to both sides)"
	@echo ""
	@echo "Required env:"
	@echo "  TODOIST_API_KEY - Set in environment before running"
	@echo ""
	@echo "Optional vars:"
	@echo "  TASKRC=$(TASKRC)"
	@echo "  TASK_DATA=$(TASK_DATA)"
	@echo "  TITWSYNC_CFG=$(TITWSYNC_CFG)"
	@echo "  ARGS='sync --apply'"

build:
	@$(ENGINE) build -t $(IMAGE_NAME) --file=$(CONTAINER_FNAME) .

build-force:
	@$(ENGINE) build -t $(IMAGE_NAME) --file=$(CONTAINER_FNAME) --no-cache .

run: _check-api-key
	@$(ENGINE) run --rm $(PODMAN_FLAGS) \
		-v $(TASKRC):/root/.taskrc:ro$(VOLUME_OPTS) \
		-v $(TASK_DATA):/root/.task:rw$(VOLUME_OPTS) \
		-v $(TITWSYNC_CFG):/root/.config/titwsync/titwsyncrc.yaml:ro$(VOLUME_OPTS) \
		-e TODOIST_API_KEY="$(TODOIST_API_KEY)" \
		-e TASKDATA=/root/.task \
		-e HOME=/root \
		$(IMAGE_NAME) $(ARGS)

sync-dry: ARGS=sync
sync-dry: run

sync: ARGS=sync --apply
sync: run

_check-api-key:
	@if [ -z "$(TODOIST_API_KEY)" ]; then \
		echo "Error: TODOIST_API_KEY is not set"; \
		exit 1; \
	fi
