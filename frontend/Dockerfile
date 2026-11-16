# Etapa 1: compila o Vue + TypeScript com o Vite
FROM node:22-alpine AS build
WORKDIR /app
COPY package.json package-lock.json .npmrc* ./
RUN npm ci --no-audit --no-fund
COPY . .
RUN npm run build

# Etapa 2: nginx sem root servindo os arquivos e encaminhando /api e /ws para a API
FROM nginxinc/nginx-unprivileged:1.27-alpine
COPY nginx.conf /etc/nginx/conf.d/default.conf
COPY --from=build /app/dist /usr/share/nginx/html
EXPOSE 8080
