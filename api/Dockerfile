# Use official Python image
FROM python:3.12-slim

RUN pip install -U pip

# Set working directory inside the container
WORKDIR /app

# Copy all files to container
COPY ["api/requirements.txt", "api/main.py", "api/schema.py", "./"]

# Install dependencies
RUN pip install --no-cache-dir -r requirements.txt

COPY [ "../models/pipeline.pkl", "./" ]

# Expose FastAPI default port
EXPOSE 8000

# Run the FastAPI app using uvicorn
CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8000"]
