# EndoFlix Docker Deployment Guide

This guide provides comprehensive instructions for deploying EndoFlix using Docker in both development and production environments.

## Table of Contents

- [Quick Start](#quick-start)
- [Development Setup](#development-setup)
- [Production Deployment](#production-deployment)
- [Configuration](#configuration)
- [Monitoring](#monitoring)
- [Troubleshooting](#troubleshooting)

## Quick Start

### Using Docker Compose (Recommended)

1. **Clone the repository:**
   ```bash
   git clone <repository-url>
   cd EndoFlix
   ```

2. **Start with Docker Compose:**
   ```bash
   # For development
   docker-compose -f docker-compose.dev.yml up

   # For production
   docker-compose up
   ```

3. **Access the application:**
   - Application: http://localhost:5000
   - Health check: http://localhost:5000/health

## Development Setup

### Prerequisites

- Docker Engine 20.10+
- Docker Compose 2.0+

### Development Environment

1. **Environment Configuration:**
   ```bash
   cp .env.dev .env
   # Edit .env file with your preferred settings
   ```

2. **Start Development Environment:**
   ```bash
   docker-compose -f docker-compose.dev.yml up
   ```

3. **Development Features:**
   - Hot reloading enabled
   - Volume mounting for code changes
   - Exposed database and Redis ports for local access
   - Debug logging enabled

### Database Access

For local development, you can access the database directly:

```bash
# Connect to PostgreSQL
docker-compose -f docker-compose.dev.yml exec postgres psql -U postgres -d videos_dev

# Connect to Redis
docker-compose -f docker-compose.dev.yml exec redis redis-cli
```

## Production Deployment

### Prerequisites

- Docker Engine 20.10+
- Docker Compose 2.0+
- Secrets management setup (optional but recommended)

### Environment Configuration

1. **Set up environment variables:**
   ```bash
   cp .env.prod .env
   # Edit .env file with production values
   ```

2. **Configure secrets (recommended):**
   ```bash
   # Create Docker secrets
   echo "your_secure_db_password" | docker secret create db_password -
   echo "your_secure_redis_password" | docker secret create redis_password -
   echo "your_secure_postgres_password" | docker secret create postgres_password -
   ```

3. **Deploy to production:**
   ```bash
   docker-compose up -d
   ```

### Production Features

- **Security:** Non-root user, read-only filesystem where possible
- **Resource Limits:** CPU and memory constraints
- **Health Checks:** Comprehensive health monitoring
- **Logging:** Structured JSON logging
- **Backup:** Automated database backups
- **Monitoring:** Prometheus metrics collection

## Configuration

### Environment Variables

| Variable | Description | Default | Required |
|----------|-------------|---------|----------|
| `SECRET_KEY` | Flask application secret key | - | Yes |
| `DB_NAME` | PostgreSQL database name | videos_prod | No |
| `DB_USER` | PostgreSQL username | postgres | No |
| `DB_PASSWORD` | PostgreSQL password | - | Yes |
| `DB_HOST` | PostgreSQL host | postgres | No |
| `DB_PORT` | PostgreSQL port | 5432 | No |
| `REDIS_HOST` | Redis host | redis | No |
| `REDIS_PORT` | Redis port | 6379 | No |
| `LOG_LEVEL` | Application log level | INFO | No |
| `MAX_WORKERS` | Number of worker threads | 8 | No |

### Docker Compose Files

- **`docker-compose.yml`**: Production configuration
- **`docker-compose.dev.yml`**: Development configuration
- **`docker-compose.override.yml`**: Optional production overrides

## Monitoring

### Health Checks

All services include health checks:

- **EndoFlix:** HTTP health endpoint at `/health`
- **PostgreSQL:** Database connectivity check
- **Redis:** Ping connectivity check

### Metrics

Prometheus metrics are available at:
- Application metrics: `http://localhost:5000/metrics`

### Logs

View logs for all services:

```bash
# All services
docker-compose logs

# Specific service
docker-compose logs endoflix

# Follow logs
docker-compose logs -f endoflix
```

## Troubleshooting

### Common Issues

1. **Port Conflicts:**
   ```bash
   # Check what's using port 5000
   lsof -i :5000
   # Or use different port in docker-compose.yml
   ```

2. **Permission Issues:**
   ```bash
   # Fix volume permissions
   sudo chown -R $USER:$USER volumes/
   ```

3. **Database Connection Issues:**
   ```bash
   # Check database logs
   docker-compose logs postgres

   # Test database connectivity
   docker-compose exec postgres pg_isready -U postgres
   ```

4. **Memory Issues:**
   ```bash
   # Check resource usage
   docker stats

   # Adjust resource limits in docker-compose.yml
   ```

### Debug Mode

Enable debug logging:

```bash
# Set log level to DEBUG
LOG_LEVEL=DEBUG docker-compose up
```

### Database Issues

If you encounter database problems:

```bash
# Reset database
docker-compose down -v
docker-compose up -d postgres
# Wait for postgres to be ready, then run:
docker-compose exec -T postgres psql -U postgres -d videos_prod < scripts/init.sql
```

### Backup and Restore

```bash
# Create manual backup
docker-compose exec db-backup pg_dump -h postgres -U postgres videos_prod > backup.sql

# Restore from backup
docker-compose exec -T postgres psql -U postgres -d videos_prod < backup.sql
```

## Security Considerations

### Production Checklist

- [ ] Change all default passwords
- [ ] Use Docker secrets for sensitive data
- [ ] Enable SSL/TLS in production
- [ ] Configure firewall rules
- [ ] Set up log aggregation
- [ ] Regular security updates
- [ ] Backup strategy implemented
- [ ] Monitoring and alerting configured

### Secrets Management

For enhanced security, use Docker secrets:

```bash
# Create secrets
echo "secure_password" | docker secret create db_password -
echo "redis_password" | docker secret create redis_password -

# Use in docker-compose.yml
secrets:
  - db_password
```

## Performance Tuning

### Resource Allocation

Adjust resource limits based on your hardware:

```yaml
deploy:
  resources:
    limits:
      cpus: '2.0'      # Increase for better performance
      memory: 2G       # Increase for larger datasets
    reservations:
      cpus: '0.5'
      memory: 1G
```

### Database Optimization

For better database performance:

```bash
# Analyze tables after large data imports
docker-compose exec postgres vacuum analyze;

# Check query performance
docker-compose exec postgres psql -U postgres -d videos_prod -c "EXPLAIN ANALYZE SELECT * FROM your_table;"
```

## Scaling

### Horizontal Scaling

For high availability:

1. **Load Balancer:** Use nginx or HAProxy
2. **Multiple Instances:** Deploy multiple EndoFlix containers
3. **Database Clustering:** Consider PostgreSQL clustering
4. **Redis Clustering:** Use Redis Cluster for scalability

### Vertical Scaling

Increase resource allocation:

```bash
# Scale up individual services
docker-compose up -d --scale endoflix=3
```

## Support

For issues and questions:

1. Check the logs: `docker-compose logs`
2. Verify health checks: `curl http://localhost:5000/health`
3. Review configuration files
4. Check service status: `docker-compose ps`

## Contributing

When contributing to the Docker setup:

1. Test changes in development environment
2. Update documentation for any configuration changes
3. Ensure production configurations remain secure
4. Update CI/CD pipeline if needed