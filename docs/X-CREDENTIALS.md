# X API Credentials Setup

Flow needs X API credentials to post tweets. This guide walks you through the setup.

## 1. Create an X Developer App

1. Go to [developer.x.com](https://developer.x.com)
2. Create a new project and app
3. Set up **User authentication settings**:
   - App permissions: **Read and write**
   - Type of App: **Web App**
   - Callback URI: Your `OAUTH_REDIRECT_URI` (e.g., `https://your-domain.com/oauth/callback`)
   - Website URL: Any valid URL

## 2. Get Your Credentials

From your app's **Keys and tokens** page, you need:

### OAuth 2.0 (Primary auth)
- Client ID
- Client Secret

### OAuth 1.0a (Fallback)
- API Key (Consumer Key)
- API Secret (Consumer Secret)
- Access Token
- Access Token Secret

## 3. Create Credential Files

Create these files in your `.secrets/` directory:

### `.secrets/x-oauth.env`
```bash
# OAuth 1.0a credentials (from X Developer portal)
X_CONSUMER_KEY=your_api_key_here
X_CONSUMER_SECRET=your_api_secret_here
X_ACCESS_TOKEN=your_access_token_here
X_ACCESS_TOKEN_SECRET=your_access_token_secret_here

# OAuth 2.0 client (for token refresh)
CLIENT_ID=your_client_id_here
CLIENT_SECRET=your_client_secret_here
```

### `.secrets/x-oauth2.env`
This file is auto-generated when you log in via the web UI. It stores your OAuth 2.0 tokens:

```bash
# Auto-generated — do not edit manually
ACCESS_TOKEN=...
REFRESH_TOKEN=...
CLIENT_ID=...
CLIENT_SECRET=...
```

## 4. First Login

1. Start Flow: `python api.py`
2. Open `http://localhost:5120` in your browser
3. Click "Connect X Account"
4. Authorize the app on X
5. You'll be redirected back — tokens are now saved

## 5. Verify Setup

```bash
# Test posting (dry run)
python lib/post.py "Test tweet" --dry-run

# Verify credentials
curl http://localhost:5120/verify
```

## Troubleshooting

### "401 Unauthorized" on posting
- Your access token may have expired
- Click "Connect X Account" again to refresh

### "Invalid redirect_uri"
- Your `OAUTH_REDIRECT_URI` must exactly match what's in your X Developer app settings

### "Client authentication failed"
- Double-check your Client ID and Client Secret in `.secrets/x-oauth.env`
