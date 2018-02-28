PREFIX ?= /

SRC_DIR := $(dir $(lastword $(MAKEFILE_LIST)))

ANANICY_D_R := $(shell find $(SRC_DIR)/ananicy.d -type f -name "*.rules")
ANANICY_D_R_I := $(patsubst $(SRC_DIR)/%.rules, $(PREFIX)/etc/%.rules, $(ANANICY_D_R))

ANANICY_D_T := $(shell find $(SRC_DIR)/ananicy.d -type f -name "*.types")
ANANICY_D_T_I := $(patsubst $(SRC_DIR)/%.types, $(PREFIX)/etc/%.types, $(ANANICY_D_T))

A_SERVICE := $(PREFIX)/lib/systemd/system/ananicy.service
A_CONF := $(PREFIX)/etc/ananicy.d/ananicy.conf
A_BIN := $(PREFIX)/usr/bin/ananicy


default:  help

$(ANANICY_D_T_I): $(ANANICY_D_T)
	install -Dm644 $< $@

$(ANANICY_D_R_I): $(ANANICY_D_R)
	install -Dm644 $< $@

$(A_CONF): $(SRC_DIR)/ananicy.d/ananicy.conf
	install -Dm644 $< $@

$(A_BIN): $(SRC_DIR)/ananicy
	install -Dm755 $< $@

$(A_SERVICE): $(SRC_DIR)/ananicy.service
	install -Dm644 $< $@


install: ## Install ananicy
install: $(A_CONF) $(A_BIN) $(A_SERVICE) $(ANANICY_D_R_I) $(ANANICY_D_T_I)

uninstall: ## Delete ananicy
uninstall:
	@rm -fv   $(A_CONF) $(A_BIN) $(A_SERVICE) $(ANANICY_D_R_I)


deb: ## Create debian package
deb:
	./package.sh debian

help: ## Show help
	@fgrep -h "##" $(MAKEFILE_LIST) | fgrep -v fgrep | sed -e 's/\\$$//' | sed -e 's/##/\t/'
