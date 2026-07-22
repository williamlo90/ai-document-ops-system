# Demo Recording

**Artifact:** [Invoice Review captioned MP4](assets/demo/invoice-review-demo.mp4)

The recording uses the real React routes and PDF viewer with deterministic, stateful API fixtures.
It demonstrates interface behavior and safety boundaries without provider credentials or latency.

Regenerate it with:

```powershell
.\scripts\build_demo_video.ps1
```

The script records the six active product routes, converts the Playwright WebM to an H.264
fast-start MP4, and writes both files under `docs/assets/demo`.

The video is not provider-benchmark evidence. Accuracy, latency, cost, failure iterations, and known
limits are documented under the [evidence index](INDEX.md).
