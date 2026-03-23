# Docker Deployment Guide - Credos

This project is containerized using Docker and Docker Compose for easy deployment and persistence.

## Prerequisites
- Docker
- Docker Compose

## Quick Start
1. Clone the repository: `git clone https://github.com/fernandoapaiva-dotcom/credos`
2. Navigate to the project root.
3. Start the system:
   ```bash
   docker-compose up -d --build
   ```

## Services
- **Backend (API)**: Runs on port `8001`.
- **Frontend (UI)**: Runs on port `80` (Standard HTTP).

## Data Persistence
The SQLite databases are stored in a Docker Volume named `db-data`. Even if you stop or delete the containers, your data will be preserved as long as the volume exists.

## How to Update
Every time a new update is pushed to GitHub, simply run:
```bash
git pull
docker-compose up -d --build
```
This will rebuild the images with the latest code provided by the AI agent and restart the services.
