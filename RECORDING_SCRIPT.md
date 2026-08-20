# Recording script — Gemma 4 × Expanso Edge (60 seconds)

> **Draft.** Message and beats derived from this repo's README and pipeline.
> The audience line is a guess — correct it before recording.

**For:** vision and multi-modal conversations, Google/Gemma partner slots, booth
openers where a live webcam does the selling.

**Total spoken:** ~130 words at ~140 wpm = **0:56**.

**A note on scope.** The demo can run four analyses on one frame — object
detection, OCR, scene description and safety judgement. Four capabilities is
four messages, and a viewer remembers none of them. This script picks **one
claim** and uses the analyses as its evidence. If you need the full capability
tour, record that separately and call it a walkthrough.

**Setup before recording**

- Webcam pointed at something with text *and* objects in frame — a shipping
  label on a box works well. The demo is more convincing on a real object than
  on a test card.
- Dashboard fullscreen, one frame already processed so the structure is visible
  on the opening shot.
- Read each italic direction silently, then deliver the line.

---

### 0:00 — The constraint (12s)

*Hold the object up to the camera. Dashboard visible.*

A camera produces pixels. Every system downstream of it wants rows — something
with fields you can query, join and alert on. Bridging that gap is normally a
cloud round trip per frame.

---

### 0:12 — What we built (12s)

*Point at the node.*

Gemma 4 runs on this device, next to the camera. One frame goes in, and what
comes out the other side is structured data — not an image, and not a round
trip.

---

### 0:26 — The proof (18s)

*Point at the structured output for the frame just captured.*

Here is that frame as a record. What it saw, the text it read off the label,
what it judged the scene to be. That is a row. It can go straight into a
database, and the picture it came from never left the device.

---

### 0:44 — Why it matters (12s)

*Stay on the output.*

Any webcam becomes a structured data source. Not a video feed you have to store
and later regret — a stream of rows, generated where the camera already is.

---

## Do not say

- Do not claim frontier-model accuracy. The claim is that useful structure comes
  out locally, not that it beats a large hosted model.
- Do not promise a specific frames-per-second figure unless it is on screen.
- Do not list all four analyses as separate features in the 60-second cut. They
  are evidence for one claim here.
