# Media Agent — Screenshot Generation

You are a media generation agent for X/Twitter content. Your job is to capture screenshots of URLs.

## How It Works

When generating media, include a URL in your prompt. The agent will:
1. Open the URL in OpenClaw's browser
2. Capture a screenshot at X card dimensions (1200×630)
3. Save it to `media/generated/`

## Usage

```
"Screenshot https://example.com/page"
```

or simply include a URL:

```
"Capture this: https://your-site.com/dashboard"
```

## X Card Dimensions

- Size: 1200×630 pixels (1.91:1 ratio)
- Format: PNG
- Quality: 2x scale for retina displays

## Output

Screenshots are saved to: `media/generated/`

Filename format: `screenshot_{YYYYMMDD_HHMMSS}.png`

## Requirements

- OpenClaw gateway must be running
- `OPENCLAW_GATEWAY_TOKEN` must be set in `.env`

## Example Response

```json
{
  "success": true,
  "path": "media/generated/screenshot_20260307_143022.png",
  "mode": "screenshot",
  "url": "https://example.com/page"
}
```

## Tips

- For best results, use pages with clean, visual content
- Dark mode pages often look better as X cards
- Avoid pages that require login or have cookie banners
