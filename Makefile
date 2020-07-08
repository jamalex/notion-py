help:  ## display this help
	@awk 'BEGIN {FS = ":.*##"; printf "\nUsage:\n  make \033[36m<target>\033[0m\n\nTargets:\n"} \
	/^[a-zA-Z_-]+:.*?##/ { printf "  \033[36m%17s\033[0m  %s\n", $$1, $$2 }' $(MAKEFILE_LIST)

build: clean  ## build python wheel
	python3 setup.py sdist bdist_wheel

release: build  ## upload wheel to pypi
	twine upload -s dist/*

clean:  ## clean all build files
	find . -name "*.pyc" -print0 | xargs -0 rm -rf
	rm -rf build
	rm -rf dist
	rm -rf notion.egg-info

install:  ## install package locally
	python setup.py install

format:  ## reformat code with black
	black .
