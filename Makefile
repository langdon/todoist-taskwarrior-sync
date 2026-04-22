IMAGE_NAME   ?= titwsync
CONTAINER_FNAME ?= Containerfile
TASKRC       ?= $(HOME)/.taskrc
TASK_DATA    ?= $(HOME)/.task
ARGS         ?= --help
PODMAN_FLAGS ?= -it

.PHONY: help podman-build podman-build-force podman-run sync sync-dry

help:
	@echo "make podman-build        - Build the container image"
	@echo "make podman-build-force  - Rebuild without cache"
	@echo "make podman-run          - Run with custom ARGS (default: --help)"
	@echo "make sync-dry            - Two-way sync dry run"
	@echo "make sync                - Two-way sync (writes to both sides)"
	@echo ""
	@echo "Required env:"
	@echo "  TODOIST_API_KEY        - Set in environment before running"
	@echo ""
	@echo "Optional vars:"
	@echo "  TASKRC=$(TASKRC)"
	@echo "  TASK_DATA=$(TASK_DATA)"
	@echo "  ARGS='sync --apply'"

podman-build:
	@podman build -t $(IMAGE_NAME) --file=$(CONTAINER_FNAME) .

podman-build-force:
	@podman build -t $(IMAGE_NAME) --file=$(CONTAINER_FNAME) --no-cache .

podman-run: _check-api-key
	@podman run --rm $(PODMAN_FLAGS) \
		-v $(TASKRC):/root/.taskrc:ro,Z \
		-v $(TASK_DATA):/root/.task:rw,Z \
		-e TODOIST_API_KEY="$(TODOIST_API_KEY)" \
		$(IMAGE_NAME) $(ARGS)

sync-dry: ARGS=sync --dry-run
sync-dry: podman-run

sync: ARGS=sync --apply
sync: podman-run

_check-api-key:
	@if [ -z "$(TODOIST_API_KEY)" ]; then \
		echo "Error: TODOIST_API_KEY is not set"; \
		exit 1; \
	fi
