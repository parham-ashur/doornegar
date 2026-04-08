# Doornegar Social Media Plan

## Strategy

Doornegar's social media presence serves two purposes:
1. **Drive traffic** — Share top stories to bring readers to the website
2. **Build credibility** — Position Doornegar as a trusted source for media transparency

### Content Types

| Type | Frequency | Example |
|------|-----------|---------|
| **Top story** | 2-3x daily | Story title + summary + coverage bar image + link |
| **Blind spot alert** | When detected | "This story is only covered by state media — diaspora media is silent" |
| **Bias comparison** | 1x daily | Side-by-side: how state vs diaspora media framed the same event |
| **Weekly digest** | Monday | Top 5 stories of the week + coverage stats |
| **Source spotlight** | 1x weekly | Deep dive into one media source's coverage patterns |

### Tone & Language
- **Primary language**: Farsi
- **Secondary**: English (for diaspora audience)
- **Tone**: Neutral, analytical, factual — never take sides
- **Never**: Express political opinions, mock any source, or call any media "fake"

---

## Platforms to Consider

### 1. Twitter/X
- **Audience**: Iranian diaspora, journalists, researchers
- **Format**: Short text + image + link
- **Posting**: 2-3 times daily
- **API**: Free tier allows 1,500 tweets/month (more than enough)
- **Account needed**: Create at twitter.com
- **API setup**: Apply at developer.twitter.com → create app → get API keys

### 2. Telegram Channel
- **Audience**: Iranians inside and outside Iran (most accessible)
- **Format**: Longer posts with formatted text + images
- **Posting**: 3-5 times daily
- **API**: Use existing Telethon setup (already configured!)
- **Account needed**: Create a channel via Telegram app → get channel username
- **Easiest to start with** — you already have the Telegram API configured

### 3. Instagram
- **Audience**: Younger Iranian diaspora
- **Format**: Image cards with Farsi text overlay, stories
- **Posting**: 1-2 times daily
- **API**: Meta Business API (complex setup)
- **Consider later** — requires image generation for each post

### 4. Bluesky
- **Audience**: Tech-savvy, journalists
- **Format**: Similar to Twitter
- **API**: Free, open API
- **Consider later**

### 5. Mastodon
- **Audience**: Privacy-conscious, open-source community
- **Format**: Similar to Twitter but longer posts allowed
- **API**: Free, open API
- **Consider later**

---

### 5. WhatsApp Business
- **Audience**: Direct reach to contacts, groups
- **Format**: Plain text messages, broadcast lists
- **API**: WhatsApp Business API (requires Meta Business verification)
- **Setup**: Create WhatsApp Business account → verify business → get API access
- **Note**: Broadcast requires pre-approved templates. Best for curated subscriber lists.

### 6. LinkedIn
- **Audience**: Researchers, journalists, academics, policy makers
- **Format**: Professional long-form posts
- **Posting**: 2-3 times per week
- **API**: LinkedIn Marketing API
- **Setup**: Create LinkedIn Company Page → apply for API access

### 7. Bluesky
- **Audience**: Tech-savvy, journalists, open-source community
- **Format**: Short posts (300 chars)
- **API**: Free, open AT Protocol
- **Setup**: Create account at bsky.app → Settings → App Passwords → create one
- **Easiest API** — no approval process needed

## Recommended Launch Order

1. **Telegram Channel** (Week 1) — Easiest, already have API, most Iranian reach
2. **Twitter/X** (Week 1-2) — Broadest diaspora reach
3. **Bluesky** (Week 2) — Easy API, journalist audience
4. **WhatsApp** (Week 3) — Direct subscriber reach
5. **LinkedIn** (Month 2) — Professional/research audience
6. **Instagram** (Month 2) — Requires image card generation

---

## What You Need to Do

### For Telegram Channel:
1. Open Telegram → Create Channel
2. Name: `دورنگر | Doornegar`
3. Description: `شفافیت رسانه‌ای ایران — مقایسه پوشش خبری رسانه‌های داخل و خارج ایران`
4. Username: `@doornegar` (check availability)
5. Set channel as **Public**
6. Tell me the username once created

### For Twitter/X:
1. Create account at twitter.com
2. Apply for developer access at developer.twitter.com
3. Create a project + app
4. Generate these 4 keys and add to `.env`:
   ```
   TWITTER_API_KEY=...
   TWITTER_API_SECRET=...
   TWITTER_ACCESS_TOKEN=...
   TWITTER_ACCESS_TOKEN_SECRET=...
   ```

### For Bluesky:
1. Create account at bsky.app
2. Go to Settings → App Passwords → Add App Password
3. Add to `.env`:
   ```
   BLUESKY_HANDLE=doornegar.bsky.social
   BLUESKY_APP_PASSWORD=...
   ```

### For WhatsApp Business:
1. Create a Meta Business account at business.facebook.com
2. Add WhatsApp to your business
3. Get a WhatsApp Business phone number
4. Add to `.env`:
   ```
   WHATSAPP_PHONE_NUMBER_ID=...
   WHATSAPP_ACCESS_TOKEN=...
   ```
Note: WhatsApp broadcast requires pre-approved message templates. Initially, share posts manually via WhatsApp groups.

### For Instagram:
1. Create an Instagram Business account
2. Connect it to a Facebook Page via Meta Business Suite
3. Get a long-lived access token from Meta Developer portal
4. Add to `.env`:
   ```
   INSTAGRAM_ACCESS_TOKEN=...
   INSTAGRAM_BUSINESS_ACCOUNT_ID=...
   ```
Note: Instagram requires an image for every post. The system will use the story's article image.

### For LinkedIn:
1. Create a LinkedIn Company Page for Doornegar
2. Apply for Marketing API access at linkedin.com/developers
3. Create an app and get OAuth access token
4. Add to `.env`:
   ```
   LINKEDIN_ACCESS_TOKEN=...
   LINKEDIN_ORG_ID=...
   ```

---

## Content Template Examples

### Top Story (Farsi)
```
📰 {story.title_fa}

{summary_fa (first 2 sentences)}

📊 پوشش: حکومتی {state_pct}٪ · مستقل {independent_pct}٪ · برون‌مرزی {diaspora_pct}٪

🔗 {story_url}

#دورنگر #شفافیت_رسانه #ایران
```

### Blind Spot Alert (Farsi)
```
🔴 نقطه کور رسانه‌ای

«{story.title_fa}»

این خبر فقط توسط رسانه‌های {side} پوشش داده شده است.
رسانه‌های {other_side} سکوت کرده‌اند.

چرا؟ تحلیل کامل:
🔗 {story_url}

#نقطه_کور #دورنگر
```

### Bias Comparison (Farsi)
```
⚖️ مقایسه پوشش خبری

{story.title_fa}

🔴 رسانه حکومتی: {state_summary_fa (1 sentence)}
🔵 رسانه برون‌مرزی: {diaspora_summary_fa (1 sentence)}

تفاوت چارچوب‌بندی: {framing comparison}

🔗 {story_url}

#سوگیری_رسانه #دورنگر
```

---

## Auto-posting Architecture

The system is designed to auto-post when ready:

```
auto_maintenance.py
  └── step_social_post()
        ├── Pick top story (most articles, not yet posted)
        ├── Generate post text from story data
        ├── Post to Telegram channel (via Telethon)
        ├── Post to Twitter/X (via tweepy)
        └── Mark story as "posted" (avoid re-posting)
```

A `social_posts` table tracks what's been posted where, preventing duplicates.

---

## Security Considerations

- **Never post automatically without review** initially — start with a review queue
- **No political opinions** — only factual coverage comparison
- **Attribute all data** — "بر اساس تحلیل دورنگر" (Based on Doornegar analysis)
- **Don't tag individual journalists or sources** negatively
- **Iranian user safety** — no content that could endanger readers inside Iran
