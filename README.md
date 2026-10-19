# Daily Life API

See [DEPLOYMENT.md](DEPLOYMENT.md) for the GitHub → Railway → MongoDB Atlas setup and the directly installable APK build steps.

FastAPI and MongoDB backend for the Daily Life planner. This repository contains the backend service; the Expo/React Native app is maintained separately. See [DEPLOYMENT.md](DEPLOYMENT.md) for Railway deployment and APK configuration.

Run from this directory with `venv/Scripts/python.exe -m uvicorn app.main:app --host 0.0.0.0 --port 8000 --reload`. Configuration is read from `.env`; use `.env.example` as a template. Install `requirements-dev.txt` to run the tests in `tests/`.

Food-photo analysis is optional. To enable it, add `GEMINI_API_KEY` to this backend's local `.env` file. The key stays on the server and must never be added to the Expo app. The free-tier Gemini service has quotas and its terms may allow submitted photos to be used to improve Google products. The app asks for confirmation before sending each photo; analysis returns estimates for user review, and non-food photos remain in the app's private on-device gallery.

Schedule, life-item, food-analysis, and document-extraction endpoints require a verified Firebase ID token. Set `FIREBASE_PROJECT_ID` and either `FIREBASE_SERVICE_ACCOUNT_JSON` or valid Application Default Credentials for local development. Production requires a matching Firebase Admin service account, a TLS-enabled Atlas URI, `APP_ENV=production`, and HTTPS-only CORS origins (or an empty `CORS_ORIGINS` value for mobile-only use). Existing records without a `user_id` are hidden by account-scoped queries; migrate them only after explicitly identifying their owner and backing up the database.

`POST /api/documents/extract` accepts a PDF/JPEG/PNG/WebP up to 6 MB and forwards it to Google Gemini only after the user confirms in the app. The backend does not persist the document or extracted fields. Google processes submitted content under its service terms; extracted fields remain in the user's encrypted on-device vault.

Railway deploys this service from the root `Dockerfile` and `railway.json`. When connecting this backend-only repository, leave the Railway root directory at `/`; do not set it to `/backend`. Add production values using Railway's secret variables; do not commit a `.env` file or Firebase service-account JSON. MongoDB Atlas network access should be restricted to the Railway service's static egress IP or private network.

| Method | Path | Behavior |
| --- | --- | --- |
| GET / POST | `/api/schedules/categories` | Load or save the signed-in user's reusable custom schedule categories. Names are limited to 60 characters; repeated names reuse the existing category. Schedule create/update payloads also accept custom category names. |
| POST | `/api/food/analyze` | Analyze a resized JPEG/PNG/WebP image with Gemini and return food items with estimated portions, calories, sugar, and fat. Requires server-side `GEMINI_API_KEY`. |
| POST | `/api/documents/extract` | Extract visible fields from a confirmed PDF/JPEG/PNG/WebP document (maximum 6 MB); requires authentication and server-side `GEMINI_API_KEY`, with no backend file persistence. |
| GET | `/api/market/quotes` | Return cached NIFTY 50, COMEX gold/silver futures converted to approximate INR weights, and update timestamps from Yahoo Finance. No provider key required. |

All routes above except the public market quote route require a verified Firebase user. `/` and `/health` are public deployment health probes. Interactive API documentation is disabled in production.

Market quotes come from Yahoo Finance's unofficial chart endpoint and are cached for five minutes. The gold/silver INR weights are conversions of COMEX futures using USD/INR, not Indian retail or MCX prices; change percentages reflect futures prices, not the currency conversion. Data may be delayed, unavailable, rate-limited, or subject to provider terms; cached quotes are marked stale if the provider is temporarily unavailable.
