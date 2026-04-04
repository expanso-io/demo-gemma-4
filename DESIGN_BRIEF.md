# kurate.cloud — Taste Brief & Design System

## What This Is

kurate.cloud is a **taste capture system** whose primary output is an LLM-consumable design brief. The moodboard UI is the input mechanism; the taste brief is the product. The goal: hand any LLM this brief and get output that reflects David Aronchick's design taste — not AI slop.

This document is both a **taste filter** (what to avoid) and a **design system** (what to build). The taste filter is comprehensive. The design system provides sensible defaults for critical dimensions — typography, spacing, radius, motion — while acknowledging that it will grow over time through continued taste capture.

## The Core Problem

AI-generated designs default to generic patterns: cosmic gradients, glassmorphism everywhere, 35% opacity text, buzzword copy, emoji icons, cookie-cutter hero sections. They look like "an AI made this" because no human taste was applied. kurate captures and codifies one person's taste so LLMs can produce output with genuine craft and opinion.

---

## Part 1: The Taste Brief (Skill)

The brief is the primary deliverable. It is a document that an LLM reads before generating any visual output. It has three layers, a design token system, and a brand reference.

### Layer 1: Core Principles (Always Apply)

These emerged from 12 site reviews (91 likes, 28 dislikes, 12 detailed commentaries). They apply regardless of context — tool UI, marketing page, presentation, or demo.

**Contrast is non-negotiable.**
Every piece of text must be readable against its background. Meet WCAG AA minimum (4.5:1 for body text, 3:1 for large text). Low-contrast text (light gray on dark gray, purple on black, 35% opacity body text) is the single most consistent critique across every site reviewed. If choosing between "looks cool" and "reads well," choose reads well. Every time. This also applies to interactive elements: buttons, links, and form controls must have sufficient contrast in all states.

**Color is semantic, not decorative.**
Every color in the palette must communicate something: brand identity, interaction state, data category, status, or hierarchy. Elements of the same color imply a related function. Don't use color for variety or visual interest — use it because it means something. The best design systems have a small palette played within. Random color variety signals lack of taste. Exception: marketing hero sections may use color expressively (e.g., black background for impact), but even there, color choices should feel intentional and consistent with the brand.

**No single element should BE the design.**
Glassmorphism, gradients, dark mode, brutalist typography — none of these are inherently good or bad. They become slop when they ARE the design instead of serving it. Stripe uses glass effects as one note in a composed system. AI slop makes glass effects the whole composition. Restraint + context + fit into the overall system is what separates taste from template. If you removed the element and the design collapsed, the element was doing too much.

**Craft signals human curation.**
Hand-selected icons (even paid ones from Flaticon) beat generated SVGs. Curated imagery beats stock. Custom font pairings beat system defaults. The presence of deliberate human choices is what separates designed from generated. When curated assets are not available, **do not fake curation.** Instead, use a clearly marked placeholder box describing what the asset should be and why (e.g., "Replace with: line icon showing data flow between nodes, matching Phosphor light style, 24px"). Honest placeholders are infinitely better than generic filler that pretends to be a choice.

**Constrain width intentionally.**
Content max-width: **1280px**. Don't design for full viewport. On screens wider than 1280px, center the content with even margins. This applies to all contexts. Within that frame, content areas should be even narrower where appropriate (prose: 720px max, centered forms: 480px max).

**Fewer words, larger type.**
Prefer concise, punchy copy set at a larger size over dense paragraphs at small sizes. This applies to marketing pages, tool UIs, and documentation. Every word should earn its place. If a heading can be 4 words instead of 8, use 4.

**Speak the user's language.**
Use familiar patterns — monospace for code/data, color-coded status indicators, breadcrumbs for hierarchy. Don't invent new paradigms when established ones work. Familiarity is a feature. However, familiar does NOT mean generic. The difference: familiar patterns executed with opinionated details (your specific colors, your specific radius, your specific type choices) feel both comfortable and authored. Familiar patterns with default everything feel like a template.

**Progressive disclosure over complexity.**
Show the basics, hint at depth. Figma shows Fill with hex value and opacity, but Stroke and Effects are collapsed with a + button. Surface the essentials, let people drill in. Don't overwhelm, but don't hide capability either.

### Design Tokens

These are the concrete values that back up the principles. Use these as defaults. They can be adjusted per context but should be the starting point.

**Typography Scale:**
| Role | Size | Weight | Line-height | Font |
|------|------|--------|-------------|------|
| Display / Hero | 48px | Semibold (600) | 1.1 | Figtree |
| H1 | 36px | Semibold (600) | 1.15 | Figtree |
| H2 | 24px | Semibold (600) | 1.2 | Figtree |
| H3 | 20px | Medium (500) | 1.3 | Figtree |
| Body | 16px | Regular (400) | 1.6 | Figtree |
| Body Large | 18px | Regular (400) | 1.6 | Figtree |
| Small / Caption | 14px | Regular (400) | 1.5 | Figtree |
| Label / Overline | 12px | Medium (500) | 1.4 | Figtree, uppercase, 0.05em tracking |
| Monospace / Data | 14px | Regular (400) | 1.5 | JetBrains Mono or system monospace |

Never go below 14px for any readable text. Minimum font weight: 400 (regular). Never use 200 or 300 weight for any purpose.

**Spacing Scale (8px grid):**

| Token | Value | Usage |
|-------|-------|-------|
| xs | 4px | Tight gaps between related inline elements |
| sm | 8px | Default gap between related elements |
| md | 16px | Padding inside cards, between form fields |
| lg | 24px | Section padding, card spacing |
| xl | 32px | Between major sections |
| 2xl | 48px | Page-level section separation |
| 3xl | 64px | Hero/section breaks on marketing pages |
| 4xl | 96px | Major page divisions (marketing only) |

**Border Radius:**

| Context | Radius | Notes |
|---------|--------|-------|
| Cards, containers | 4px | Sharp and intentional |
| Buttons (tool UI) | 4px | Match cards |
| Buttons (marketing) | 9999px (pill) | Apple-style, marketing CTAs only |
| Inputs | 4px | Match cards |
| Tags / badges | 4px | Or pill for status indicators |
| Modals | 8px | Slightly softer than cards |
| Tooltips | 4px | Match the system |

Never apply 16px+ radius uniformly to everything. Radius should vary by purpose.

**Shadows:**

| Level | Value | Usage |
|-------|-------|-------|
| None | — | Default for dark mode. Borders replace shadows. |
| Subtle | 0 1px 2px rgba(0,0,0,0.05) | Light mode cards |
| Medium | 0 4px 12px rgba(0,0,0,0.08) | Light mode elevated elements, dropdowns |
| Float | 0 12px 40px rgba(0,0,0,0.15) | Modals, command palettes, floating panels |

In dark mode, use 1px borders (e.g., `#2a2a2a` or `rgba(255,255,255,0.08)`) instead of shadows for elevation. Shadows on dark backgrounds look muddy.

**Motion:**

| Context | Behavior |
|---------|----------|
| Tool UI | Snappy/instant. No transitions on state changes. If something changes, it changes now. Max 100ms for hover color shifts. |
| Marketing pages | Apple-style scroll-triggered animations. Elements may animate in on scroll (opacity + subtle translateY). Easing: ease-out. Duration: 400-600ms. Stagger: 100ms between sequential elements. |
| Page transitions | Instant. No fade, no slide. |
| Loading states | Skeleton screens (gray pulsing blocks), never spinners. |
| Hover states | Color/background change only. No scale, no translateY, no shadow transitions. Max 100ms. |

Never: parallax scroll effects, scroll-jacking, bounce animations, Lottie animations on every section, fade-up-on-scroll for tool UI.

**Responsive Breakpoints:**

| Breakpoint | Width | Behavior |
|------------|-------|----------|
| Desktop | >1280px | Content centered at max-width: 1280px |
| Laptop | 1024-1280px | Full-width within frame, sidebar visible |
| Tablet | 768-1024px | Sidebar collapses to hamburger/overlay. Grid goes from 3-col to 2-col. |
| Mobile | <768px | Single column. Navigation moves to bottom or hamburger. |

**Interactive States:**

| State | Treatment |
|-------|-----------|
| Default | As specified |
| Hover | Background color shift or border color change. Subtle, fast (100ms). No scale or shadow changes. |
| Focus | Visible focus ring: 2px solid accent color, 2px offset. Never remove default focus for keyboard users. |
| Active/Pressed | Slightly darker background. No transform. |
| Disabled | 50% opacity. No pointer events. |
| Error | Red accent (#FF4A0E from Expanso red-600) + text description. Never color alone. |
| Success | Green accent (#52CD42 from Expanso green-600) + text description. |
| Loading | Skeleton placeholder or inline spinner. Never block the whole UI. |

**Unavailable Assets Protocol:**

When generating output and curated assets (icons, images, illustrations) are not available:
1. Use a visible placeholder box with a light dashed border
2. Inside, describe what the asset should be: type (icon/photo/illustration), subject, style reference, approximate size
3. Example: `[ASSET: Line icon, 24px, "network nodes connected" — match Phosphor light weight]`
4. Never substitute emoji, generated SVG blobs, or stock imagery without explicit approval
5. A design with honest placeholders is better than a design with fake curation

### Layer 2: Context-Dependent Moves

These are available design strategies activated by what you're building. If a page mixes contexts (e.g., a marketing page with an embedded product demo), the primary context governs the page-level decisions (background, typography scale, spacing) and the secondary context governs its section only.

**Tool / Dashboard UI (Linear, Stripe, Supabase, Figma reference)**
- Default: dark mode. Background: slightly tinted dark (not pure black). Use #141414 or #1a1a2e range.
- The UI chrome should recede — neutral gray tones for shell, borders, navigation.
- Brand accent (Expanso violet #501E99 or #9259ED) reserved for: primary action buttons, active states, key highlights only. Don't paint the whole UI violet.
- Blue (#0055FF or #0d99ff) for interactive/selection states — separate from brand accent.
- Dense information display: use the smaller end of the spacing scale (8px, 16px gaps). 14px body text acceptable here.
- Row-based lists for data, masonry/grid for visual content.
- Sidebar navigation (collapsible), two-level if needed (icon rail + text panel, like Supabase).
- Content max-width: 1280px even on wide screens.
- No scroll animations. Instant transitions. Skeleton loading states.

**Marketing / Messaging Pages (Apple reference)**
- Default: dark mode, black or near-black background (#000000 or brand dark #000F3B).
- Apple is the gold standard for single-message pages, demos, landing pages. Study its structure: centered vertical layout, dramatic type scale (Display size: 48px+), scroll-based storytelling.
- Pill-shaped CTAs (9999px radius), solid brand color (not gradient).
- Muted labels (12px, uppercase, tracked) with bold values (36-48px, semibold).
- 1px lines as design elements, spec grids for features.
- Minimize choices — one clear CTA per section, one clear message per page.
- Scroll-triggered animations allowed here (opacity + translateY, 400-600ms, ease-out).
- Section spacing: generous (64px-96px between major sections).
- This is the ONLY context where high marketing energy is appropriate.

**Documentation / Brief Output (Tailwind reference)**
- Dark mode: navy range (#0f172a), not pure black. Slightly warmer than tool UI.
- Sidebar navigation with section labels (uppercase, tracked) and left-border active indicators (2px solid accent).
- Prose mixed with structured data / code examples.
- Syntax highlighting with clear color differentiation — sub-elements (attributes, values, tags) should each have distinguishable colors within the same family.
- Copy buttons on code blocks / exportable sections.
- Content area: max-width 720px for prose, wider for code blocks. Sidebar: 240-280px.

**Editorial / Storytelling**
- Serif typography (Signifier Light for Expanso context) for headings. Figtree for body.
- Warm neutral palette, earth tones (#faf9f6 background, #2c2416 text, #8b7355 accents).
- Generous whitespace: 48px-96px section spacing, 32px card gaps.
- Spaced uppercase labels (12px, 0.15em tracking) for categories.
- Light backgrounds are the default in this context (the only context where light is default).

### Layer 3: Anti-Patterns (Never Do This)

These are explicit dislikes captured from reviewing bad designs, augmented by adversarial review. They apply to ALL contexts, including client work. Organized by severity.

**Hard Fails (if present, the design fails review):**
- Body text contrast below WCAG AA (4.5:1)
- Body text at 35% opacity or lower
- Cosmic/space gradient backgrounds
- Rainbow gradient text
- Gradient text on headlines
- "Revolutionary/innovative/next-gen/cutting-edge" copy
- "All-in-one platform" buzzword headlines
- Fake company logos as social proof
- Emoji as feature icons
- No real content / all placeholder with no indication it needs replacement
- Designed as a screenshot, not as a usable product

**Strong Dislikes (fix these, but they don't auto-fail):**
- Glassmorphism as the primary design element
- Backdrop-blur on everything
- Ultra-thin font weight (200) for any text
- Ultra-wide letter-spacing on names or headlines
- Glowing gradient avatars or elements with glow shadows
- 16px+ border radius applied uniformly everywhere
- Gradient bar charts
- Each card using a different gradient color for its icon
- Cosmetic background gradients serving no informational purpose
- Gradient primary buttons (solid color is better)
- Ghost-border circular social icons
- Wave emoji in greetings
- Announcement pill banners ("Now with AI!")
- Every card/component having identical cookie-cutter structure
- Greyed-out trust logos of companies that aren't customers
- "Trusted by 10,000+ companies" unverified claims
- "Everything you need to succeed" section headers
- Generic project names (Alpha, Beta, Gamma) as placeholders
- "Full Stack Developer • Designer • Creator" multi-title subtitles
- Decorative elements that serve no functional purpose

**Modern AI Slop Patterns (also avoid):**
- Bento grid layouts with pastel fills and rounded corners
- Fake browser window chrome around hero screenshots
- Generic stat cards with "12.5k / 99.9% / +24%" filler data
- Dot-grid / radial-gradient / mesh background noise textures
- Twelve feature cards with identical icon-top/headline/sentence structure
- Fake terminal or code snippets showing meaningless commands
- Decorative charts with made-up data
- Placeholder avatars with stock-smile energy
- "AI assistant" sparkle/star/orbit motifs
- Noise texture overlays used to fake sophistication
- Giant blurred blobs behind content
- 100vh hero sections that bury actual content below the fold
- "Ready to get started?" CTA sections on gradient bands
- Infinite marquee logo strips
- Split-screen hero with left copy + right fake app mockup at 15 degrees
- Over-animated scroll reveals on every single section
- Three-column pricing tables copied from SaaS templates
- Perfectly symmetrical layouts with no focal tension
- Do not invent fake brands, fake customer logos, or fake product metrics
- Do not use placeholder feature names unless explicitly marking them for replacement

### Brand Foundation: Expanso

The Expanso brand guidelines serve as the default color and typography system. Personal taste principles (Layer 1) take precedence on questions of craft. Expanso defines the specific palette and type.

**Colors:**
- Violet (primary brand): #501E99 (dark), #9259ED (mid), #DFCBFD (light)
- Blue (secondary/open-source): #001C70 (dark), #0055FF (mid)
- Ice (accent): #33CCFF
- Dark backgrounds: #000F3B (blue-dark), #140034 (violet-dark)
- Neutrals: #000000 (text primary), #9F9F9F (text secondary), #FFFFFF (light bg)
- Semantic: #FF4A0E (error/red), #52CD42 (success/green), #ff9f0a (warning/orange)

**Color Roles (semantic mapping):**
- Violet: brand identity, primary actions, key highlights
- Blue: interactive states, links, selection
- Ice: secondary accent, code syntax, data visualization emphasis
- Red: errors, destructive actions, strong dislikes
- Green: success, positive trends, likes
- Orange: warnings, caution states
- Grays: chrome, borders, secondary text, backgrounds

**Typography:**
- Primary: Figtree (geometric sans-serif) — semibold for headers, regular for body
- Secondary: Signifier Light (modern serif) — editorial/formal headings only
- Monospace: JetBrains Mono or system monospace — data, code, metadata
- Fallback (when Signifier unavailable): Georgia or system serif

**Rules:**
- Violet must always appear in Expanso-branded work (at minimum in primary CTA or logo)
- Blue/Ice required for open-source (Bacalhau) context
- When palettes blend, one must dominate (>60% of color usage by surface area)
- Photography: authentic, diverse, natural — never staged, tilted, or artificially lit
- If brand colors fail contrast requirements, contrast wins. Adjust the shade, not the rule.

### Client Override Layer (Optional)

When building for a client, their brand overrides the Expanso palette and typography. However, the Core Principles (Layer 1) and Design Tokens still govern execution:
- Client color palette replaces Expanso colors
- Client typography replaces Figtree/Signifier
- Client tone/voice guidelines apply
- Your principles — contrast, semantic color, craft, restraint, constrained width, progressive disclosure — still apply
- Your design tokens — spacing scale, radius system, motion rules — still apply unless the client has their own design system

You execute in their brand with your taste.

---

## Part 2: The Review Mode

When reviewing LLM-generated output (a website, slide deck, or other visual), evaluate against these criteria in order:

1. **Contrast check**: Can every piece of text be read comfortably? Test against WCAG AA (4.5:1 body, 3:1 large text). Check buttons, links, and form labels too.
2. **Color audit**: Does every color serve a semantic purpose? Is any color purely decorative? Are related items the same color? Is the palette limited (5-7 functional colors max)?
3. **Craft signals**: Are there curated elements (icons, imagery, type pairings) that show human choice? Or could everything have been randomly generated? Are placeholders honestly marked?
4. **Anti-pattern scan**: Check against the full anti-pattern list (hard fails, strong dislikes, modern AI slop patterns). Any hard fail = automatic rejection.
5. **Token compliance**: Does the output follow the design token system? Check font sizes, spacing rhythm, border radius, shadow usage, and motion behavior.
6. **Width/layout**: Is content constrained to 1280px max? Is prose constrained to ~720px? Are responsive breakpoints handled?
7. **Context match**: Is the design strategy appropriate for what's being built (tool vs. marketing vs. docs vs. editorial)?
8. **Opinion check**: Does this feel like it has a point of view? Or could it be any company's page? The test: if you removed the logo, would you know whose design system this is?

Return structured feedback:
```
PASS/FAIL: [overall assessment]
HARD FAILS: [any automatic failures from anti-pattern list]
CONTRAST: [specific issues with element, colors, and ratio]
COLOR: [semantic vs decorative usage, palette size]
CRAFT: [human curation signals present/absent, placeholder quality]
ANTI-PATTERNS: [specific violations found, categorized by severity]
TOKENS: [typography, spacing, radius, shadow, motion compliance]
LAYOUT: [width constraints, responsive behavior, grid usage]
CONTEXT: [appropriate strategy for the deliverable type]
OPINION: [does it feel authored or generated — specific evidence]
RECOMMENDED FIXES: [prioritized list, hard fails first]
```

---

## Part 3: The kurate.cloud System (Future)

### Ingest
- **Bookmarklet / Share target**: Capture URL from any page (desktop + mobile via share sheet to `kurate.cloud/save?url=...`)
- **Auto-screenshot**: Save a visual record of the page at capture time
- **Auto-metadata scrape**: OG tags, colors, fonts, page structure
- **Reactions added later**: Binary like/dislike per element, text commentary, at user's leisure

### Taste Engine
- **Recency weighting**: Newer reactions weighted slightly higher, but taste is roughly stable over time
- **Commentary override**: Explicit comments ("this feels dated") are hard overrides regardless of recency
- **Proactive element discovery**: Analyze ingested sites for recurring patterns the user hasn't reacted to, surface them for opinion (e.g., "You've saved 8 sites with variable font weight animation and never commented — thoughts?")
- **Three-tier classification**: Core (always) / Moves (contextual) / Anti-patterns (never)

### Brief API
- `GET /brief` — full taste brief as markdown (default)
- `GET /brief?format=json` — structured data for programmatic use
- `GET /brief?only=colors,typography` — filtered to specific sections (keeps context window light)
- `GET /brief?only=anti-patterns` — just the slop filter
- `GET /brief?only=tokens` — just the design token system
- `GET /brief?context=editorial` — brief with editorial move pre-activated
- `GET /brief?client=acme` — brief with client override applied

### Feedback Loop
- Generate output with another LLM using the brief
- Feed the generated URL back to kurate
- kurate (or an LLM with the brief) reviews against the taste criteria using Review Mode
- Structured feedback returned for iterative improvement
- Over time, review results inform the taste profile (auto-discover new anti-patterns from repeated failures)

---

## Key Quotes (From Taste Discovery)

> "The challenge is separating what feels normal and good UX design from what feels like it actually has taste. Things shouldn't just be unique for unique's sake."

> "Coloring should be limited, but it should be a visual signal that ties things together. Everything of a similar color should be implying a similar thing."

> "There are things that look hand-drawn, even if they're pulled or paid for from external sources. Those are unique and incredibly important to capture."

> "I care more about the design system that we're building generally rather than the specific app."

> "Apple is our best of breed for marketing/messaging pages. We should follow it."

> "The best design systems in the world have a very small set of palette that they play within."

> "No single element should be the essence of the design — it should merely be a portion of the taste."

> "Absolutely no taste or custom work was put into this, which is one of the elements that makes it feel so generic."

> "Both Stripe and Apple show a lot of taste as a whole, and so glassmorphism is merely a portion of the taste they are trying to get across, not the essence."
