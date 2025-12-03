# services/willys-service/Dockerfile

FROM node:22

# /app will be the repo root inside the container
WORKDIR /app

# 1) Copy the willys-service package manifest and install its deps
COPY services/willys-service/package*.json ./services/willys-service/

WORKDIR /app/services/willys-service
RUN npm install --omit=dev

# 2) Copy the rest of the repo so scripts/, etc. are available
WORKDIR /app
COPY . .

# 3) Run the willys-service server from its own folder
WORKDIR /app/services/willys-service
CMD ["node", "-r", "dotenv/config", "server.js"]
