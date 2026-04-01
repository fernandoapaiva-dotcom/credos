#!/bin/bash

# --- CONFIGURAÇÕES ---
APP_DIR="/home/ubuntu/credos" # Ajuste se necessário

echo "🚀 Iniciando Deploy do Credos na OCI (167.234.252.109)..."

# 1. Garantir que as pastas de persistência existam
mkdir -p data
mkdir -p backups
mkdir -p logs

# 2. Verificar se o Docker Compose está instalado
if ! command -v docker-compose &> /dev/null
then
    echo "❌ docker-compose não encontrado. Instalando dependências..."
    sudo apt-get update
    sudo apt-get install -y docker-compose
fi

# 3. Pull/Build das imagens
echo "🏗️ Construindo imagens..."
docker-compose build --no-cache

# 4. Derrubar containers antigos (se existirem)
echo "🛑 Parando serviços antigos..."
docker-compose down

# 5. Subir novos containers em modo Detached (Background)
echo "✅ Subindo o sistema..."
docker-compose up -d

# 6. Limpeza de imagens órfãs para economizar espaço em disco
echo "🧹 Limpando imagens antigas..."
docker image prune -f

echo "--------------------------------------------------------"
echo "🎉 DEPLOY CONCLUÍDO COM SUCESSO!"
echo "Acesse http://167.234.252.109 para usar o sistema."
echo "Use 'docker-compose logs -f backend' para ver o robô rodando."
echo "--------------------------------------------------------"
