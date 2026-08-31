PYTHON ?= python3
EP ?= EP-001

.PHONY: cards png test clean

cards:
	$(PYTHON) scripts/build.py episodes/$(EP).json

png:
	$(PYTHON) scripts/build.py episodes/$(EP).json --png

test:
	$(PYTHON) -m unittest discover -s tests -v

clean:
	rm -rf build
