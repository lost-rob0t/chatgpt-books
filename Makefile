SHELL := /usr/bin/env bash
.PHONY: assets fixture fixture-regression test ert book check all-books
assets:
	./tools/generate-assets
fixture:
	./tools/build-fixture
fixture-regression: fixture
	python3 ./tools/check-epub-fixture dist/bootstrap-fixture.epub
test:
	./tools/check-structure
ert:
	emacs -Q --batch -L elisp -l test/chatgpt-books-test.el -f ert-run-tests-batch-and-exit
book:
	./tools/build-book "$(BOOK)"
check: book
	./tools/validate-book "books/$(BOOK)/dist/$(BOOK).epub"
all-books:
	./tools/build-all
