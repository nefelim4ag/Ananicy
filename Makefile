PREFIX ?= /

default:  help

install: ## Install ananicy
install:
	mkdir -p                          $(PREFIX)/etc/ananicy.d/
	rsync -a        ./ananicy.d/      $(PREFIX)/etc/ananicy.d/
	install -Dm755  ./ananicy         $(PREFIX)/usr/bin/ananicy
	install -Dm644  ./ananicy.service $(PREFIX)/lib/systemd/system/ananicy.service

uninstall: ## Delete ananicy
uninstall:
	rm -rfv $(PREFIX)/etc/ananicy.d/
	rm -v   $(PREFIX)/usr/bin/ananicy
	rm -v   $(PREFIX)/lib/systemd/system/ananicy.service

deb: ## Create debian package
deb:
	./package.sh debian

help: ## Show help
	@fgrep -h "##" $(MAKEFILE_LIST) | fgrep -v fgrep | sed -e 's/\\$$//' | sed -e 's/##/\t/'
