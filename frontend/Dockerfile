# 阶段1：构建前端静态文件
FROM node:18-alpine as build-stage
WORKDIR /app
COPY package.json package-lock.json ./
RUN npm install --registry=https://registry.npmmirror.com
COPY . .
RUN npm run build

# 阶段2：用Nginx部署静态文件
FROM nginx:alpine as production-stage
# 复制构建好的静态文件到Nginx
COPY --from=build-stage /app/dist /usr/share/nginx/html
# 复制自定义Nginx配置（解决前端路由和跨域）
COPY nginx.conf /etc/nginx/conf.d/default.conf
EXPOSE 80
CMD ["nginx", "-g", "daemon off;"]