# Stage 1: Build
FROM node:20-slim AS build

WORKDIR /app

# Copy package.json and install dependencies
COPY package*.json ./
RUN npm install

# Copy the rest of the frontend source code
COPY . .

# Build the production bundle
RUN npm run build

# Stage 2: Production
FROM nginx:alpine

# Copy the build output from the builder stage
COPY --from=build /app/dist /usr/share/nginx/html

# Copy custom Nginx config
COPY nginx.conf /etc/nginx/conf.d/default.conf

# Expose port 80
EXPOSE 80

# Command to run Nginx
CMD ["nginx", "-g", "daemon off;"]
