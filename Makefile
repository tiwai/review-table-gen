PREFIX ?= /usr/local
BINDIR = $(PREFIX)/bin

.PHONY: all install clean test

all:
	@echo "Nothing to build. Use 'make install' to install the script."

install:
	install -d $(DESTDIR)$(BINDIR)
	install -m 0755 generate_report.py $(DESTDIR)$(BINDIR)/generate-kernel-review-report

test:
	./generate_report.py --list test/list-test \
		--dataset kreviews \
		--model gemma-4 \
		--model qwen3.6 \
		--links-file test/branches.json \
		--title "SLE12-SP5 Potential Regressions" --output test-report.html

clean:
	rm -rf __pycache__
	rm -f report.html test-report.html
