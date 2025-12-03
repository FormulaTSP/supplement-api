# Use official Playwright image (has Chromium + deps preinstalled)
FROM mcr.microsoft.com/playwright:v1.49.0-jammy

# Set working directory at repo root
WORKDIR /app

# Copy only the service package manifests and install
COPY services/willys-service/package*.json services/willys-service/
RUN npm install --prefix services/willys-service --omit=dev

# Copy the rest of the repo
COPY . .

# Switch to service dir
WORKDIR /app/services/willys-service

EXPOSE 8080

# Start the server (dotenv is installed in service package)
CMD ["node", "-r", "dotenv/config", "server.js"]
