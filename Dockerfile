# Use official Python slim image
FROM python:3.13-slim

# Install poppler-utils (provides pdfinfo etc.)
RUN apt-get update && apt-get install -y poppler-utils && rm -rf /var/lib/apt/lists/*

# Set working directory inside container
WORKDIR /app

# Copy requirements first (to leverage Docker cache)
COPY requirements.txt .

# Install Python dependencies
RUN pip install --no-cache-dir -r requirements.txt

# Copy the rest of the application code
COPY . .

# Expose port your app runs on
EXPOSE 10000

# Run your FastAPI app with uvicorn
CMD ["uvicorn", "app.api:app", "--host", "0.0.0.0", "--port", "10000"]