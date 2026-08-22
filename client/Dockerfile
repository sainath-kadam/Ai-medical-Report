# Multi-stage build: compile the Vite app, then serve the static output with nginx.
# The frontend is a pure static bundle in production — it talks to the FastAPI server
# only over HTTP(S), never server-side rendered (no Next.js anywhere in this stack).

FROM node:20-alpine AS build
WORKDIR /app
COPY package.json package-lock.json ./
RUN npm ci
COPY . .
# Baked in at build time — Vite inlines VITE_* vars into the bundle, so these must be
# supplied as build args (see docker-compose.yml) rather than read at container start.
ARG VITE_API_URL=http://localhost:8000/api/v1
ARG VITE_GOOGLE_CLIENT_ID=
ENV VITE_API_URL=$VITE_API_URL
ENV VITE_GOOGLE_CLIENT_ID=$VITE_GOOGLE_CLIENT_ID
RUN npm run build

FROM nginx:1.27-alpine AS runtime
COPY --from=build /app/dist /usr/share/nginx/html
COPY nginx.conf /etc/nginx/conf.d/default.conf
EXPOSE 80
CMD ["nginx", "-g", "daemon off;"]
