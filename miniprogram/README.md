# HKMU Campus Mini Program

Native WeChat Mini Program client for the existing HKMU Campus Platform backend.

## Included

- WeChat one-tap login via `wx.login` -> `/api/v1/auth/wechat/miniprogram`
- Username/password and email/password fallback login
- Mobile-first tab navigation: Home, News, Lost & Found, Profile
- Home dashboard backed by the existing news and lost-found APIs
- Searchable campus news list
- Filterable lost & found list
- Current user profile from the same backend account database

## Setup

1. Configure backend environment variables:

```env
WECHAT_MINIPROGRAM_APPID=your_wechat_appid
WECHAT_MINIPROGRAM_SECRET=your_wechat_secret
```

2. Start the backend with HTTPS on a public domain.

3. Update [project.config.json](/C:/Users/LY/Desktop/hkmu_campus_platform-main/miniprogram/project.config.json) and replace `touristappid` with your real WeChat Mini Program AppID.

4. Update [utils/config.js](/C:/Users/LY/Desktop/hkmu_campus_platform-main/miniprogram/utils/config.js) when needed. Local LAN debugging currently uses `http://192.168.20.147:3002/api/v1`.

5. In the WeChat Mini Program admin console, add your HTTPS domain under "服务器域名".

6. Open the `miniprogram/` folder in WeChat DevTools.

## Notes

- The mini program sends `X-Client-Platform: wechat-miniprogram`, so the backend can distinguish non-browser requests from the existing web SPA.
- The mini program uses the existing FastAPI backend and SQLite database through `/api/v1`; it does not create a separate database.
- WeChat login is optional at runtime. If backend credentials are not configured, the account/password login still works.
- For local debugging, use a proper HTTPS tunnel or deployed test domain. Mini programs cannot use `localhost`.
