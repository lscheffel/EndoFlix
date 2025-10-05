# 🚀 EndoFlix v5.1.0 Release

**Release Date:** October 5, 2025
**Previous Version:** v5.0.0

## 🐛 What's New in v5.1.0

### Bug Fixes
- Resolved merge conflicts in limiter configuration
- Fixed Redis connection handling for rate limiting

### Performance Improvements
- Optimized database query performance
- Enhanced caching mechanisms for better response times

## 📦 Installation & Upgrade

### Using Docker (Recommended)

```bash
# Pull the latest version
docker pull lscheffel/endoflix:v5.1.0

# Or build from source
git checkout v5.1.0
docker-compose up -d
```

### Manual Installation

```bash
# Update to v5.1.0
git checkout v5.1.0
pip install -r requirements.txt

# Run database optimizations if needed
psql -U postgres -d endoflix -f db_optimizations.sql
```

## 🔧 Configuration

No new configuration required. All existing environment variables remain compatible.

## 📊 Monitoring

Continue using the existing monitoring endpoints:
- Health check: `GET /health`
- Metrics: `GET /metrics`
- Analytics: `/analytics` (requires authentication)

## 🧪 Testing

```bash
pytest tests/ -v
```

## 📚 Documentation

- **CHANGELOG.md** - Updated with v5.1.0 changes
- **README.md** - Installation and usage instructions

## 🤝 Support

- **GitHub Issues:** [Report bugs](https://github.com/lscheffel/EndoFlix/issues)
- **Discussions:** [Community support](https://github.com/lscheffel/EndoFlix/discussions)

---

**Full Changelog:** https://github.com/lscheffel/EndoFlix/compare/v5.0.0...v5.1.0

**Contributors:** lscheffel and the EndoFlix development team

**Made with 💪 for video enthusiasts everywhere!**