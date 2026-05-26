# 阶段1：构建前端静态文件
FROM node:18-alpine as build-stage
WORKDIR /app
COPY package.json package-lock.json ./
RUN --mount=type=cache,target=/root/.npm \
    npm ci --registry=https://registry.npmmirror.com
COPY . .
RUN npm run build

# 阶段2：用Nginx部署静态文件
FROM nginx:1.26-alpine as production-stage
COPY --from=build-stage /app/dist /usr/share/nginx/html
COPY nginx.conf /etc/nginx/conf.d/default.conf
EXPOSE 80
CMD ["nginx", "-g", "daemon off;"]
