PYTHON ?= python3
EP ?= EP-001

.PHONY: cards test clean

cards:
	$(PYTHON) scripts/build.py episodes/$(EP).json

test:
	$(PYTHON) -m unittest discover -s tests -v

clean:
	rm -rf build
