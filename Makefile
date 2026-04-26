PREFIX ?= /usr/local
BINDIR = $(PREFIX)/bin

.PHONY: all install clean

all:
	@echo "Nothing to build. Use 'make install' to install the script."

install:
	install -d $(DESTDIR)$(BINDIR)
	install -m 0755 generate_report.py $(DESTDIR)$(BINDIR)/generate-kernel-review-report

clean:
	rm -rf __pycache__
	rm -f report.html
