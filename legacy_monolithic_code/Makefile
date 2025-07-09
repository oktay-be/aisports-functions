.PHONY: setup test lint run clean docker-build docker-run

# Setup and Installation
setup:
	pip install -r requirements.txt

# Run the application
run:
	python app.py

# Run tests
test:
	python -m unittest discover -s tests

# Run linting
lint:
	flake8 .

# Clean up cache and temporary files
clean:
	rm -rf __pycache__
	rm -rf .pytest_cache
	rm -rf .coverage
	rm -rf cache/*
	find . -name "*.pyc" -delete

# Docker commands
docker-build:
	docker build -t turkish-sports-api .

docker-run:
	docker run -p 5000:5000 --env-file .env turkish-sports-api
