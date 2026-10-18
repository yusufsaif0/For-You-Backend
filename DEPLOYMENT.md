# Deploy the API to Railway and install the Android APK

## Current readiness

The backend has a Dockerfile that runs Uvicorn on `0.0.0.0:$PORT`. `railway.json` selects that Dockerfile, checks `/health` with a 120-second timeout, and retries failed processes up to five times. The app has an EAS `apk` profile for a signed, standalone Android APK.

Verified on October 18, 2026: 30 backend tests passed and nine MongoDB integration tests were skipped because `TEST_MONGODB_URL` was not set. All 28 frontend tests, TypeScript, lint, and Expo dependency compatibility checks passed. Docker Desktop's Linux engine was unavailable, so the container was not run locally. These checks do not prove that Firebase sign-in, Atlas network access, or Railway variables are configured correctly.

Both local environment files now contain Firebase settings. The frontend/backend project IDs match, the Admin JSON matches the backend project, and its private key parses successfully. Live credentials and the Email/Password provider still need verification in Firebase. `npm run release:check` currently fails because the app uses a private HTTP API address; replace that address with the deployed Railway HTTPS URL before building. Local backend settings also omit `APP_ENV=production` and an explicit `CORS_ORIGINS`; add these in Railway as described below.

A debug APK already exists locally, but it is not the configured production release and normally expects the Expo development server. There is no linked EAS project ID in the current app config. No live Railway deployment or release APK has been verified.

## Recommended first deployment: upload the backend directly

You can deploy the existing backend directory with Railway CLI without first creating a GitHub repository. Use this path for the first deployment; the GitHub path in section 1 is optional.

### A. Confirm Firebase

In the existing Firebase project's Authentication settings, enable the Email/Password sign-in provider. Reuse the existing project for both backend and app. The app requires email verification before accessing account data. It uses the Firebase JavaScript SDK and a Firebase Web app's client configuration.

### B. Create and link a Railway service

Create/sign into your Railway account, then run in PowerShell:

```powershell
Set-Location C:\Users\kshit\OneDrive\Desktop\Hello\backend
npm install -g @railway/cli
railway login
railway init
railway add --service daily-life-api
railway open
```

Name the project when prompted. If you already created a project, use `railway link` instead of `railway init`, and reuse its API service instead of adding a duplicate. The commands below explicitly target `daily-life-api`; replace that name if you use another service.

In the Railway dashboard, select `daily-life-api` and add the variables in section 3. Copy secret values from the existing `backend/.env` directly into Railway Variables; do not paste credentials into chat or source code. Add `APP_ENV=production` and explicitly set `CORS_ORIGINS` to an empty string. Leave the service root at its default for this backend-only upload. Keep the Dockerfile's start command.

### C. Allow Railway to reach Atlas

The configured backend requires a `mongodb+srv://` Atlas URI in production. A Railway MongoDB template's ordinary `mongodb://` URI will fail this application's production validation.

For a restricted Atlas IP access list, Railway's static outbound IP feature currently requires its **Pro plan**. Under the API service's Settings > Networking, enable Static IPs, add **all** assigned outbound IPv4 addresses to Atlas > Database & Network Access > IP Access List, and redeploy. The public Railway domain's incoming IP and your laptop's IP are not the service's outbound IPs. If static IPs are unavailable on your plan, resolve the network approach before relying on a restricted Atlas access list; do not assume a changing outbound IP will stay valid. Allowing `0.0.0.0/0` permits connections from anywhere and removes that network restriction.

Use a database user with `readWrite` limited to the selected application database. Preserve the existing `DATABASE_NAME` if you want the existing database; select a separate database and matching user permissions for a fresh production environment. Password characters in the URI must be URL-encoded.

### D. Upload, generate a domain, and verify

From `backend/`:

```powershell
railway up --service daily-life-api
```

This builds on Railway; local Docker Desktop is not required. Wait for the deployment to become healthy. In the API service's Settings > Networking > Public Networking, generate a domain. If asked for a target port, use the port shown in the Uvicorn startup log. The Dockerfile reads Railway's `PORT` automatically.

```powershell
Invoke-RestMethod https://YOUR-SERVICE.up.railway.app/health
```

Expected response: `{"status":"ok"}`. An unauthenticated `/api/schedules` request should return 401; `/docs` is intentionally unavailable in production. `/health` confirms the process started after the initial database connection; it does not continuously ping MongoDB or validate Firebase sign-in.

Then continue with sections **4 and 5** below to configure and build the APK. For subsequent backend changes, run `railway up --service daily-life-api` again from the backend directory.

### Common first-deployment failures

| Symptom | Check |
| --- | --- |
| `CORS_ORIGINS must not include a wildcard` | Explicitly set an empty `CORS_ORIGINS` value in Railway. In its raw environment editor use `CORS_ORIGINS=""`. |
| MongoDB selection timeout | Atlas IP access list, running cluster, connection string, and Railway outbound IPs. |
| MongoDB authentication failure | Database username/password, URL encoding, and database-specific user permissions. |
| Firebase configuration error | Complete valid Admin JSON, matching project IDs, and preserved `\n` escapes inside the private key. |
| APK build fails the release check | Set all six public variables in EAS **production**, including the HTTPS API URL ending in `/api`. |
| APK cannot sign in | Firebase Email/Password provider, verified email, matching project settings, and the actual deployed API. |
| Android refuses an update | Existing app may use a different signing key. Preserve local-only vault data before considering an uninstall, which removes app data. |

## 1. Optional: publish the backend source to GitHub

The backend is maintained in its own repository: [yusufsaif0/For-You-Backend](https://github.com/yusufsaif0/For-You-Backend). Its repository root contains `Dockerfile`, `railway.json`, `requirements.txt`, and `app/`. The sibling `Hello-app/` has a separate Git repository; pushing the frontend repository does not publish backend changes.

For deployment, connect Railway to `yusufsaif0/For-You-Backend`, select branch `main`, and leave the service root directory at `/`. Railway can then redeploy automatically when backend commits are pushed. Set the production variables in Railway before deploying.

Never add a populated `.env` file, Firebase Admin credentials, or `venv/` to the GitHub repository. The supplied ignore files exclude environment files and common service-account filenames.

## 2. Configure Firebase and MongoDB Atlas

1. Create/select a Firebase project and enable Email/Password under Authentication.
2. Register a Web app in that Firebase project. This React Native app uses the Firebase JavaScript SDK, so use that Web app's public configuration in the Expo variables listed below.
3. Generate a Firebase Admin service-account key for the same project. Store its JSON only in Railway's secret variables.
4. Use a MongoDB Atlas database user and a `mongodb+srv://` connection string. Allow the Railway service's outbound network to reach the Atlas cluster. The backend validates the SRV scheme in production and creates its indexes at startup.

## 3. Deploy from GitHub to Railway

Create a Railway service from the repository containing the backend code.

- For a backend-only repository, leave the service root at the repository root.
- For a monorepo, set the service root directory to `/backend`.
- Railway should detect `Dockerfile`. Keep its default start command; the Dockerfile already reads Railway's `PORT` variable.
- The supplied `railway.json` sets `/health` and its 120-second timeout. For a monorepo, explicitly select `/backend/railway.json` as the Railway config file; its path is relative to the repository root.
- Generate a public HTTPS domain for the service after deploying.

Add these Railway Variables, using `.env.production.example` as a template. Existing secret values are already present in the local `backend/.env`; reuse them directly in Railway if this deployment should use those services:

| Variable | Value |
| --- | --- |
| `APP_ENV` | `production` |
| `MONGODB_URL` | Your Atlas SRV connection string |
| `DATABASE_NAME` | Existing value from `backend/.env`, or a deliberate new production database name |
| `FIREBASE_PROJECT_ID` | Firebase project ID |
| `FIREBASE_SERVICE_ACCOUNT_JSON` | The complete matching Admin service-account JSON |
| `CORS_ORIGINS` | Empty for mobile-only use; otherwise the exact HTTPS web origin(s), comma-separated |
| `GEMINI_API_KEY` | Optional; needed for food-photo and document analysis |
| `GEMINI_MODEL` | A model available to your Google project; the current application default is in `.env.example` |

Production startup intentionally fails if Firebase configuration, Atlas URI, or CORS settings are missing/invalid. For a mobile-only service, explicitly set `CORS_ORIGINS` to an empty value: omitting it uses the development wildcard default and fails production validation.

Check the deployment before building the APK:

```powershell
Invoke-RestMethod https://YOUR-SERVICE.up.railway.app/health
```

Expected response: `{"status":"ok"}`. An unauthenticated `GET /api/schedules` should return 401. The interactive `/docs` page is intentionally disabled in production. Verify email sign-up, verification, sign-in, and user-isolated data with valid Firebase credentials.

## 4. Configure the APK

From `Hello-app/`, sign into Expo and link/create the EAS project:

```powershell
npx eas-cli login
npx eas-cli init
```

In the EAS project's **production** environment, add every public value in `Hello-app/.env.production.example`:

```text
EXPO_PUBLIC_API_URL=https://YOUR-SERVICE.up.railway.app/api
EXPO_PUBLIC_FIREBASE_API_KEY=...
EXPO_PUBLIC_FIREBASE_AUTH_DOMAIN=...
EXPO_PUBLIC_FIREBASE_PROJECT_ID=...
EXPO_PUBLIC_FIREBASE_APP_ID=...
EXPO_PUBLIC_FIREBASE_MESSAGING_SENDER_ID=...
```

These are client configuration values embedded in the APK. Keep the Firebase Admin JSON, Atlas password, and Gemini key exclusively on the backend. Use the same Firebase project on the app and server. After changing public configuration, build a new APK.

In the Expo dashboard, open the linked project > Project settings > Environment variables, select **production**, and add the six values above with Plain text visibility. Copy the five Firebase client values from the existing `Hello-app/.env`; use the new Railway URL for `EXPO_PUBLIC_API_URL`. The app's ignored `.env` is excluded from EAS uploads, so configuring only the local file is insufficient. The `apk` profile explicitly selects the EAS production environment.

Also change only `EXPO_PUBLIC_API_URL` in the local `Hello-app/.env` to the same HTTPS URL so the local release check uses the production configuration. Leave the existing Firebase client values in place. Verify your cloud configuration with:

```powershell
npx eas-cli env:list --environment production
```

To check an equivalent local `.env` before building:

```powershell
npm run release:check
```

The EAS post-install hook runs the same check against the selected EAS environment. It fails non-development builds that still use a private/non-HTTPS API URL, missing Firebase settings, or missing custom Android modules.

## 5. Build and install

```powershell
Set-Location C:\Users\kshit\OneDrive\Desktop\Hello\Hello-app
npx eas-cli build --platform android --profile apk
```

The `apk` profile uses production variables and remote signing credentials. Let EAS generate/manage the Android keystore when prompted, or use an existing keystore if you must update an already distributed release. Keep using the same signing key for updates. This builds an APK with the JavaScript bundle included, so the installed app runs without Metro or your laptop.

Open the completed EAS build's APK download link on your phone, allow installation from that source if Android asks, and install it. The `production` profile remains available for a Play Store AAB; use `apk` for direct installation.

No Play Store account or Expo Go is required to install the resulting APK. Metro and your laptop can be off; account data still requires internet access and the deployed backend. Keep the keystore for future updates. This app's vault and documents are stored only on-device, so do not uninstall an existing installation without first preserving anything you need.

The custom `android/` sources must be committed and uploaded. They contain the usage-access and step-counter modules. `.gitignore` and `.easignore` now retain source files while excluding build outputs, machine SDK paths, private keystores, and environment files. Do not run `expo prebuild --clean` without first preserving/recreating those native modules.

## Final phone checks

- Install and launch with Metro stopped; sign up, verify email, and sign in.
- Create/edit/complete/delete schedules and check persistence after restarting.
- Schedule a reminder a few minutes ahead, grant notification access, and confirm delivery while the app is backgrounded.
- Check native step tracking, usage-access settings, camera, location, and local vault on the actual phone.
- Confirm meal, weight, event, and task entries persist under the signed-in account.
- Food/document analysis also requires a working backend Gemini model/key and quota. Markets depend on the upstream Yahoo Finance endpoint.

No release APK or live Railway deployment has been verified yet. Railway performs the container build remotely; local Docker image execution requires Docker Desktop's Linux engine to be running.

References: [Railway CLI](https://docs.railway.com/cli), [Railway FastAPI](https://docs.railway.com/guides/fastapi), [Railway configuration](https://docs.railway.com/config-as-code/reference), [Railway static outbound IPs](https://docs.railway.com/networking/static-outbound-ips), [Atlas IP access lists](https://www.mongodb.com/docs/atlas/security/ip-access-list/), [Railway healthchecks](https://docs.railway.com/deployments/healthchecks), [Expo APK builds](https://docs.expo.dev/build-reference/apk/), [EAS environment variables](https://docs.expo.dev/eas/environment-variables/manage/), [EAS source archives](https://docs.expo.dev/build-reference/easignore/).
