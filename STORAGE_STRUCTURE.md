# System Directory Structure

The project directory has been reorganized into a professional layout to strictly separate source code, compiled applications, and user data.

## Global Layout

```text
Tool_Packaged/
├── App/                 Compiled C# Application binaries and dependencies.
├── src/                 All source code for the project.
│   ├── UI/              C# Source code for the desktop application.
│   ├── modules/         Python processing modules (viet_hoa_video, capcut_dubbing, etc.).
│   └── services/        External integrations and services.
├── storage/             Main storage directory for all application data, configs, and temp files.
├── models/              Machine learning models and weights.
├── Setup_New_PC.bat     Environment setup script.
├── START_TOOL.bat       Shortcut to launch the compiled application.
└── tool_paths.py        Path manager script.
```

## Storage Directory Layout (`storage/`)

To prevent clutter, all dynamic files are strictly contained within `storage/`.

```text
storage/
  config/     Configuration files (apiKeys.json, ui_profiles.json, yt-dlp.conf)
  data/       Shared application data (templates.json)
    assets/   Lưu trữ tài nguyên Template (nhạc nền, logo) tập trung
  cache/      Disposable runtime files (thumbnails, browser profiles)
  output/     Generated user-facing outputs
  temp/       Temporary processing workspaces
  logs/       Log files
```

### Key Storage Mappings

- `storage/config/apiKeys.json`
  Centralized API Keys configuration.
- `storage/config/ui_profiles.json`
  UI Settings and user profiles.
- `storage/config/yt-dlp.conf`
  Global yt-dlp configuration.
- `storage/data/templates.json`
  Single source of truth for the Template database.
- `storage/cache/template_manager/`
  Preview thumbnail and preview video cache.
- `storage/cache/viet_hoa_video/browser_profiles/`
  Selenium browser profiles.
- `storage/output/viet_hoa_video/`
  Generated thumbnail/text outputs for the video translation tool.
- `storage/temp/capcut_dubbing/`
  Temporary workspace for dubbing/render pipeline.

## Compatibility & Migration

- **Complete Migration:** All legacy configurations (`App/apiKeys.json`, `App/ui_profiles.json`, `App/data/templates.json`, etc.) have been permanently removed.
- **Single Source of Truth:** The `storage/` directory is now the absolute and only location for reading and writing tool configurations and data. Fallback logic has been completely removed to avoid confusion.
