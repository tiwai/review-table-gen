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
		--dataset gemma-4 test/data/gemma-4 \
		--dataset qwen3.6-q4 test/data/qwen3.6-q4 \
		--branch SLE12-SP5 --output test-report.html

clean:
	rm -rf __pycache__
	rm -f report.html test-report.html
