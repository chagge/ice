ifeq ($(OS), Windows_NT)
	PYTHON = python
else
	PYTHON = python3
endif

build:
	$(PYTHON) setup.py build

install:
	$(PYTHON) setup.py install --record install.txt

test: .FORCE
	$(PYTHON) -m unittest -vf

coverage:
	coverage run --branch -m test
	coverage report -m
	coverage html

test-release:
	$(PYTHON) setup.py register -r https://testpypi.python.org/pypi
	$(PYTHON) setup.py sdist upload -r https://testpypi.python.org/pypi

release:
	$(PYTHON) setup.py register
	$(PYTHON) setup.py sdist upload

build-rtd:
	# See http://docs.readthedocs.io/en/latest/webhooks.html#others
	curl -XPOST http://readthedocs.org/build/icepy

clean:
	rm -rf build dist MANIFEST install.txt
	rm -rf .coverage htmlcov
	rm -rf docs/_build
	find . -name "__pycache__" -exec rm -r {} +
	find . -name "*.pyc" -exec rm {} +

.FORCE:

# vim: noet
