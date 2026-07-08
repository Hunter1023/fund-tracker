# 基础镜像（轻量Python镜像）
FROM python:3.9-slim

# 安装系统时区数据，配合 TZ 环境变量让 datetime.now() 返回 CST 时间
RUN apt-get update && apt-get install -y --no-install-recommends tzdata && \
    ln -snf /usr/share/zoneinfo/Asia/Shanghai /etc/localtime && \
    echo "Asia/Shanghai" > /etc/timezone && \
    rm -rf /var/lib/apt/lists/*

# 设置工作目录
WORKDIR /app

# 复制依赖文件并安装
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt -i https://mirrors.aliyun.com/pypi/simple/ --trusted-host mirrors.aliyun.com

# 复制所有后端代码
COPY . .

# 暴露端口（和app.py中一致，如5000）
EXPOSE 5000

# 启动命令（关闭debug，允许外部访问）
CMD ["python", "app.py", "--host", "0.0.0.0", "--port", "5000"]
