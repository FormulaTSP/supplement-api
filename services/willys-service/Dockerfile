# Use official Playwright image (has Chromium + deps preinstalled)
FROM mcr.microsoft.com/playwright:v1.49.0-jammy

# Set working directory
WORKDIR /app

# Copy package manifests
COPY package*.json ./

# Install dependencies (no dev deps in production)
RUN npm install --omit=dev

# Copy the rest of the app
COPY . .

# Render sets PORT env; use it in server.js (you already do: const { PORT = 8080 } = process.env)
EXPOSE 8080

# Start the server
CMD ["npm", "start"]