PREFIX ?= /usr
SYSTEMDUNITDIR ?= $(PREFIX)/lib/systemd/system
BINDIR ?= $(PREFIX)/bin
LIBDIR ?= $(PREFIX)/lib
SYSCONFDIR ?= /etc

SRC_DIR := $(dir $(lastword $(MAKEFILE_LIST)))

ANANICY_D_R := $(shell find $(SRC_DIR)/ananicy.d -type f -name "*.rules")
ANANICY_D_R_I := $(patsubst $(SRC_DIR)/%.rules, $(SYSCONFDIR)/%.rules, $(ANANICY_D_R))

ANANICY_D_T := $(shell find $(SRC_DIR)/ananicy.d -type f -name "*.types")
ANANICY_D_T_I := $(patsubst $(SRC_DIR)/%.types, $(SYSCONFDIR)/%.types, $(ANANICY_D_T))

ANANICY_D_G := $(shell find $(SRC_DIR)/ananicy.d -type f -name "*.cgroups")
ANANICY_D_G_I := $(patsubst $(SRC_DIR)/%.cgroups, $(SYSCONFDIR)/%.cgroups, $(ANANICY_D_G))

A_SERVICE := $(LIBDIR)/systemd/system/ananicy.service
A_CONF := $(SYSCONFDIR)/ananicy.d/ananicy.conf
A_BIN := $(BINDIR)/ananicy


default:  help

$(SYSCONFDIR)/%.cgroups: $(SRC_DIR)/%.cgroups
	install -Dm644 $< $@

$(SYSCONFDIR)/%.types: $(SRC_DIR)/%.types
	install -Dm644 $< $@

$(SYSCONFDIR)/%.rules: $(SRC_DIR)/%.rules
	install -Dm644 $< $@

$(A_CONF): $(SRC_DIR)/ananicy.d/ananicy.conf
	install -Dm644 $< $@

$(A_BIN): $(SRC_DIR)/ananicy.py
	install -Dm755 $< $@

$(A_SERVICE): $(SRC_DIR)/ananicy.service
	install -Dm644 $< $@


install: ## Install ananicy
install: $(A_CONF) $(A_BIN)
install: $(A_SERVICE)
install: $(ANANICY_D_G_I)
install: $(ANANICY_D_T_I)
install: $(ANANICY_D_R_I)

uninstall: ## Delete ananicy
uninstall:
	@rm -fv $(A_CONF)
	@rm -rf $(A_BIN)
	@rm -rf $(A_SERVICE)
	@rm -rf $(ANANICY_D_G_I)
	@rm -rf $(ANANICY_D_T_I)
	@rm -rf $(ANANICY_D_R_I)


deb: ## Create debian package
deb:
	./package.sh debian

help: ## Show help
	@grep -h "##" $(MAKEFILE_LIST) | grep -v grep | sed -e 's/\\$$//' | column -t -s '##'
