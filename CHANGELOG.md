# Changelog

## 2026-03-07

### Fixed
- **Media upload now works** — Switched from v1.1 OAuth 1.0a to v2 OAuth 2.0 Bearer
  - Added `upload_media_v2()` in `post.py`
  - Uses `POST api.x.com/2/media/upload` with JSON body
  - Falls back to v1.1 if v2 fails
  - Fixes 401 errors on media upload

### Added
- README.md with setup instructions and API documentation
- CHANGELOG.md

## 2026-03-06

### Added
- OAuth 2.0 PKCE flow for X authentication
- Login page with "Connect X Account" button
- Token exchange on `/oauth/callback`
- Session management with signed cookies

### Fixed
- OAuth redirect handling
- Token refresh on 401
