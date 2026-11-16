# Motion Graphics Studio v2

This upgrade adds two creation workflows:

- **Use my video:** add an animated title-card graphic to video footage or export a graphics-only transparent MOV overlay.
- **Create from prompt:** create a standalone animated graphic from a written brief using an included visual template.

## Important current limitation

This is a deterministic FFmpeg motion-graphics renderer, not a generative AI video model. It does not yet create arbitrary 3D scenes, track objects, segment subjects, or generate photorealistic video from prompts. Those capabilities require connecting an external AI provider and API credentials. Automatic visual style selection currently uses simple prompt keyword rules.

## Starter runtime limits

- Upload size: 80 MB maximum
- Clip duration: 30 seconds maximum
- Output sizes: 1080p and 4K
- Free Render instances have limited CPU/RAM and may sleep when idle. For first tests, use short 1080p clips.

## Render deployment

Use the existing Dockerfile. Root directory: `motion-graphics-studio-mvp/motion_graphics_studio`. Dockerfile path: `Dockerfile`.
