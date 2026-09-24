# Render Quality Upgrade v1

The render reads the existing `scenes`, `captions`, `bgm`, `narration`, and `output` inputs. Each `visual_keyword` deterministically chooses a locally generated palette. Adjacent scenes are given different palettes; no third-party photo or video is fetched. Simple shape layers move slowly, and 0.12-second fades mark cuts. Missing visual keywords use a generated fallback.

Captions use the existing timings. Optional `emphasis_words` (array of exact phrases) or `emphasis` can highlight important text; source text is escaped before adding color tags. Captions sit above the lower Shorts interface area. The subtitle file is burned into the MP4.

Optional audio assets must be bundled as `render-worker/assets/audio/<filename>` with a matching `<filename>.license.txt` describing provenance and permission. Set `bgm.asset` to the basename. Set `bgm.sfx.asset` to a separately licensed sound basename. Missing or unapproved audio assets are silently skipped. Narration is normalized; BGM and SFX are mixed at 10% and 12% respectively. No audio assets are bundled in v1, so existing requests stay narration-only.

The quality gate verifies the encoded file's size, 1080x1920 resolution, 30fps, audio stream, bounded duration, a generated timed subtitle file, non-black decoded frames, and audible average level. The subtitle check confirms the file and successful render; it does not perform OCR on every burned frame. Render failure is reported through the existing `render-result.json` stage structure.
