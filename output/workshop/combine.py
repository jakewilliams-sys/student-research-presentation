#!/usr/bin/env python3
"""
Combines 6 standalone HTML presentation files into one single HTML file.
Reads from the workshop directory and outputs full_presentation.html.
"""

import re
from pathlib import Path

WORKSHOP_DIR = Path(__file__).resolve().parent
OUTPUT_FILE = WORKSHOP_DIR / "full_presentation.html"

# Source files in order (section number, path, has_chapter_bar, remove_last_bridge)
SOURCES = [
    (1, "01_assumptions.html", False, False),
    (2, "02_findings.html", True, True),   # Remove bridge at end
    (3, "03_competition.html", True, True),  # Remove bridge at end
    (4, "persona_journeys_v2.html", False, False),  # Persona - special handling
    (5, "05_recommendations.html", True, False),
    (6, "06_close.html", False, False),
]


def extract_between(content: str, start_tag: str, end_tag: str) -> str:
    """Extract content between two tags (case-insensitive, non-greedy)."""
    pattern = re.compile(
        re.escape(start_tag) + r"(.*?)" + re.escape(end_tag),
        re.DOTALL | re.IGNORECASE
    )
    match = pattern.search(content)
    return match.group(1).strip() if match else ""


def extract_body_inner(html: str, exclude_nav: bool = True, exclude_script: bool = True) -> str:
    """Extract body content, optionally excluding nav elements and script."""
    body_match = re.search(r"<body[^>]*>(.*)</body>", html, re.DOTALL | re.IGNORECASE)
    if not body_match:
        return ""
    body = body_match.group(1)

    if exclude_nav:
        body = re.sub(
            r'<div class="progress-bar"[^>]*>.*?</div>',
            "", body, flags=re.DOTALL | re.IGNORECASE
        )
        body = re.sub(
            r'<div class="progress"[^>]*>.*?</div>',
            "", body, flags=re.DOTALL | re.IGNORECASE
        )
        body = re.sub(
            r'<div class="slide-counter"[^>]*>.*?</div>',
            "", body, flags=re.DOTALL | re.IGNORECASE
        )
        body = re.sub(
            r'<div class="counter"[^>]*>.*?</div>',
            "", body, flags=re.DOTALL | re.IGNORECASE
        )
        body = re.sub(
            r'<div class="nav-hint"[^>]*>.*?</div>',
            "", body, flags=re.DOTALL | re.IGNORECASE
        )
        body = re.sub(
            r'<button class="nav-btn"[^>]*>.*?</button>',
            "", body, flags=re.DOTALL | re.IGNORECASE
        )
        body = re.sub(
            r'<div class="nav-overlay"[^>]*>.*?</div>',
            "", body, flags=re.DOTALL | re.IGNORECASE
        )
        body = re.sub(
            r'<div class="nav-panel"[^>]*>.*?</div>',
            "", body, flags=re.DOTALL | re.IGNORECASE
        )

    if exclude_script:
        body = re.sub(r"<script[^>]*>.*?</script>", "", body, flags=re.DOTALL | re.IGNORECASE)

    return body.strip()


def extract_chapter_bar(html: str) -> str:
    """Extract the chapter bar nav element."""
    match = re.search(
        r'<nav class="chapter-bar"[^>]*>.*?</nav>',
        html, re.DOTALL | re.IGNORECASE
    )
    return match.group(0) if match else ""


def remove_bridge_slide(html: str) -> str:
    """Remove the last bridge slide (Next: ...) from body content."""
    # Match slide containing bridge-headline and bridge-sub with "Next:"
    bridge_pattern = r'<!-- S\d+: BRIDGE -->\s*<div class="slide bridge-slide">.*?</div>\s*'
    return re.sub(bridge_pattern, "", html, flags=re.DOTALL)


def scope_persona_css(css: str) -> str:
    """Scope persona CSS under .persona-section and map variables."""
    # Replace :root variables with .persona-section variables
    persona_vars = """
.persona-section {
  --bg: #f8f6f1;
  --bg-warm: #f2efe8;
  --text: #2c2a25;
  --text-mid: #78746b;
  --text-light: #a9a49a;
  --border: #e8e4dc;
  --optimizer: #1d7775;
  --optimizer-soft: #e8f3f3;
  --social: #b07328;
  --social-soft: #f7f0e4;
  --balancer: #3a7a55;
  --balancer-soft: #e9f3ed;
  --dependent: #6454a4;
  --dependent-soft: #efedf7;
  --ease-out-quart: cubic-bezier(0.25, 1, 0.5, 1);
  --ease-out-expo: cubic-bezier(0.16, 1, 0.3, 1);
  --serif: 'Instrument Serif', Georgia, serif;
  --sans: 'Plus Jakarta Sans', -apple-system, system-ui, sans-serif;
}
"""
    # Remove persona :root block
    css = re.sub(r":root\s*\{[^}]*\}\s*", "", css, count=1)
    # Prefix top-level selectors with .persona-section
    # Split by } that ends a rule block (naive - assume no nested braces in values)
    scoped = []
    depth = 0
    current_rule = []
    i = 0
    while i < len(css):
        c = css[i]
        if c == "{":
            depth += 1
            current_rule.append(c)
        elif c == "}":
            depth -= 1
            current_rule.append(c)
            if depth == 0:
                rule = "".join(current_rule)
                # Add .persona-section prefix to first selector
                if "{" in rule:
                    sel, rest = rule.split("{", 1)
                    sel = sel.strip()
                    if sel and not sel.startswith("@"):
                        parts = [s.strip() for s in sel.split(",")]
                        prefixed = ", ".join(
                            ".persona-section " + p if p.strip() else p
                            for p in parts
                        )
                        rule = prefixed + " {" + rest
                scoped.append(rule)
                current_rule = []
        else:
            if depth > 0 or (depth == 0 and current_rule):
                current_rule.append(c)
        i += 1
    return persona_vars + "\n".join(scoped)


def extract_persona_script(html: str) -> str:
    """Extract persona data, DOM generation, and updateGraph - excluding navigation."""
    script_match = re.search(r"<script[^>]*>(.*?)</script>", html, re.DOTALL | re.IGNORECASE)
    if not script_match:
        return ""
    script = script_match.group(1).strip()

    # Part 1: Everything before "// ---- Navigation state ----"
    nav_pos = script.find("// ---- Navigation state ----")
    if nav_pos < 0:
        nav_pos = script.find("var allScreens = [];")
    if nav_pos < 0:
        nav_pos = len(script)
    part1 = script[:nav_pos].strip()

    # Part 2: updateGraph function (defined after nav section)
    ug_pos = script.find("function updateGraph(")
    if ug_pos < 0:
        ug_pos = script.find("function updateGraph (")
    part2 = ""
    if ug_pos >= 0:
        i = script.find("{", ug_pos) + 1
        brace_count = 1
        while i < len(script) and brace_count > 0:
            if script[i] == "{":
                brace_count += 1
            elif script[i] == "}":
                brace_count -= 1
            i += 1
        part2 = script[ug_pos:i]

    combined = part1
    if part2:
        combined += "\n  " + part2 + "\n  window.updatePersonaGraph = updateGraph;\n  window.PERSONAS = PERSONAS;"

    return combined.rstrip()


def add_data_section(body: str, section: int) -> str:
    """Add data-section attribute to slide elements."""
    return re.sub(
        r'(<div class="slide[^"]*)(")',
        rf'\1 data-section="{section}"\2',
        body,
        flags=re.IGNORECASE
    )


def main():
    sections_css = []
    sections_body = []
    chapter_bars = []

    for section_num, filename, has_chapter_bar, remove_bridge in SOURCES:
        filepath = WORKSHOP_DIR / filename
        if not filepath.exists():
            print(f"Warning: {filename} not found, skipping")
            continue

        html = filepath.read_text(encoding="utf-8")

        if section_num == 4:
            # Persona - special handling
            css = extract_between(html, "<style>", "</style>")
            persona_css = scope_persona_css(css)
            sections_css.append(("/* Section 4 (persona) */", persona_css))

            body = extract_body_inner(html)
            body = f'<div class="persona-section" id="persona-section" data-section="4">\n{body}\n</div>'
            sections_body.append(body)
        else:
            css = extract_between(html, "<style>", "</style>")
            # Remove navigation CSS (progress-bar, slide-counter, nav-hint) - we'll add our own
            css = re.sub(
                r"\.progress-bar\s*\{[^}]*\}",
                "", css, flags=re.DOTALL
            )
            css = re.sub(
                r"\.slide-counter\s*\{[^}]*\}",
                "", css, flags=re.DOTALL
            )
            css = re.sub(
                r"\.nav-hint\s*\{[^}]*\}",
                "", css, flags=re.DOTALL
            )
            sections_css.append((f"/* Section {section_num} */", css))

            body = extract_body_inner(html)
            if remove_bridge:
                body = remove_bridge_slide(body)
            body = add_data_section(body, section_num)

            # Remove chapter bar from body (we'll add all chapter bars at top)
            if has_chapter_bar:
                chapter_bar = extract_chapter_bar(html)
                bar_id = {2: "chapterBar-findings", 3: "chapterBar-competition", 5: "chapterBar-recommendations"}[section_num]
                chapter_bar = re.sub(r'id="chapterBar"', f'id="{bar_id}"', chapter_bar)
                chapter_bar = re.sub(r'aria-label="[^"]*"', f'aria-label="Section {section_num} navigation"', chapter_bar)
                chapter_bar = chapter_bar.replace('<nav', '<nav style="opacity:0;pointer-events:none"', 1)
                chapter_bars.append((section_num, chapter_bar))
                body = re.sub(r'<nav class="chapter-bar"[^>]*>.*?</nav>', "", body, flags=re.DOTALL | re.IGNORECASE)

            sections_body.append(body)

    # Build chapter bar HTML - all hidden by default
    chapter_bars_html = "\n  ".join(bar for _, bar in chapter_bars)

    # Build combined CSS
    combined_css = """
/* Base from section 1 */
:root {
  --cream: #FAF8F2;
  --cream-raised: #F0EDE4;
  --cream-reveal: #EBE8E0;
  --text: #1A1714;
  --text-secondary: #6B655C;
  --text-tertiary: #9E978D;
  --accent: #00857C;
  --rule: #D6D1C7;
  --bar-track: #E8E4DB;
  --teal: #00857C;
  --pumpkin: #D4603A;
  --blueberry: #5B8EC4;
  --mustard: #C4A82D;
  --apple: #5A9E4A;
  --serif: 'Newsreader', Georgia, serif;
  --sans: 'DM Sans', system-ui, sans-serif;
  --ease: cubic-bezier(0.25, 1, 0.5, 1);
  --ease-quart: cubic-bezier(0.25, 1, 0.5, 1);
  --ease-quint: cubic-bezier(0.22, 1, 0.36, 1);
  --duration: 450ms;
}

* { margin: 0; padding: 0; box-sizing: border-box; }

body {
  background: var(--cream);
  color: var(--text);
  font-family: var(--sans);
  overflow: hidden;
  height: 100vh;
  width: 100vw;
  -webkit-font-smoothing: antialiased;
  font-weight: 400;
}

/* Unified slide system */
.slide, .journey-view {
  position: fixed;
  inset: 0;
  opacity: 0;
  pointer-events: none;
  transition: opacity 0.5s var(--ease-quart);
  background: var(--cream);
  z-index: 1;
}
.slide.active, .journey-view.active {
  opacity: 1;
  pointer-events: auto;
  z-index: 2;
}

/* Section 1: no chapter bar, full/split layout */
[data-section="1"] .full-slide { padding: 0 clamp(3rem, 8vw, 9rem); }
[data-section="1"] .split-slide { grid-template-columns: 52% 48%; }

/* Sections 2, 3, 5: chapter bar, left padding */
[data-section="2"] .slide:not(.section-divider):not(.hero-slide):not(.faceoff-slide):not(.overview-slide):not(.closing-slide),
[data-section="3"] .slide:not(.section-divider):not(.hero-slide):not(.faceoff-slide):not(.overview-slide):not(.closing-slide),
[data-section="5"] .slide:not(.section-divider):not(.hero-slide):not(.faceoff-slide):not(.overview-slide):not(.closing-slide) {
  padding: 68px 0 0;
  padding-left: 15vw;
  padding-right: clamp(2rem, 5vw, 4rem);
}

/* Section 6: centered */
[data-section="6"] .slide {
  padding: 3rem;
  text-align: center;
}
"""

    for _, css in sections_css:
        combined_css += "\n" + css + "\n"

    combined_css += """
/* Chapter bars - hidden by default, shown by JS */
.chapter-bar[style*="opacity:0"] { pointer-events: none; }

/* Navigation UI */
.progress-bar {
  position: fixed;
  bottom: 0; left: 0;
  height: 2px;
  background: var(--accent);
  z-index: 100;
  transition: width 0.45s var(--ease-quart);
}
.slide-counter {
  position: fixed;
  bottom: 1rem; right: 1.5rem;
  font-size: 0.55rem;
  font-weight: 500;
  color: var(--text-tertiary);
  z-index: 100;
  letter-spacing: 0.06em;
  font-variant-numeric: tabular-nums;
}
.nav-hint {
  position: fixed;
  bottom: 2.8rem;
  left: 50%;
  transform: translateX(-50%);
  font-size: 0.58rem;
  color: var(--text-tertiary);
  z-index: 100;
  transition: opacity 0.8s;
  opacity: 0.6;
}
.nav-hint.hidden { opacity: 0; }

@media (prefers-reduced-motion: reduce) {
  *, *::before, *::after {
    transition-duration: 0.01ms !important;
    animation-duration: 0.01ms !important;
  }
}
"""

    # Remove 'active' from all slides except first
    def strip_active(s: str) -> str:
        return re.sub(r'\s+active\s+', ' ', s)

    for i, body in enumerate(sections_body):
        if i > 0:
            sections_body[i] = strip_active(body)
        else:
            sections_body[i] = body  # Keep first slide active for init

    # Get persona script for DOM generation
    persona_path = WORKSHOP_DIR / "persona_journeys_v2.html"
    persona_html = persona_path.read_text(encoding="utf-8")
    persona_script = extract_persona_script(persona_html)

    # Build unified navigation script
    unified_script = f"""
(function() {{
  // Run persona DOM generation first
  {persona_script}

  // Unified navigation
  var allScreens = [];
  var section1Slides = document.querySelectorAll('.slide[data-section="1"]');
  var section2Slides = document.querySelectorAll('.slide[data-section="2"]');
  var section3Slides = document.querySelectorAll('.slide[data-section="3"]');
  var personaSlides = document.querySelectorAll('.persona-section .slide');
  var personaJourneys = document.querySelectorAll('.persona-section .journey-view');
  var section5Slides = document.querySelectorAll('.slide[data-section="5"]');
  var section6Slides = document.querySelectorAll('.slide[data-section="6"]');

  section1Slides.forEach(function(el) {{ allScreens.push({{ type: 'slide', el: el, section: 1 }}); }});
  section2Slides.forEach(function(el) {{ allScreens.push({{ type: 'slide', el: el, section: 2 }}); }});
  section3Slides.forEach(function(el) {{ allScreens.push({{ type: 'slide', el: el, section: 3 }}); }});

  // Persona: divider, title, intro, then per-persona (intro + 7 journey), comparison, closing
  var PERSONAS = window.PERSONAS || [];
  var personaOrder = [];
  personaSlides.forEach(function(el) {{
    var ds = el.getAttribute('data-slide');
    if (ds === 'divider' || ds === 'title' || ds === 'intro') personaOrder.push({{ type: 'slide', el: el, section: 4 }});
    else if (ds && ds.startsWith('persona-intro-')) personaOrder.push({{ type: 'slide', el: el, section: 4 }});
    else if (ds === 'comparison' || ds === 'closing') personaOrder.push({{ type: 'slide', el: el, section: 4 }});
  }});
  PERSONAS.forEach(function(p) {{
    var jv = document.querySelector('[data-slide="journey-' + p.id + '"]');
    if (jv) {{
      for (var s = -1; s < 6; s++) {{
        personaOrder.push({{ type: 'journey', el: jv, section: 4, persona: p, stage: s }});
      }}
    }}
  }});
  var compSlide = document.querySelector('.persona-section [data-slide="comparison"]');
  var closeSlide = document.querySelector('.persona-section [data-slide="closing"]');
  personaOrder.push({{ type: 'slide', el: compSlide, section: 4 }});
  personaOrder.push({{ type: 'slide', el: closeSlide, section: 4 }});

  allScreens = allScreens.concat(personaOrder);
  section5Slides.forEach(function(el) {{ allScreens.push({{ type: 'slide', el: el, section: 5 }}); }});
  section6Slides.forEach(function(el) {{ allScreens.push({{ type: 'slide', el: el, section: 6 }}); }});

  var totalSteps = allScreens.length;
  var currentIdx = 0;
  var progressEl = document.getElementById('progress');
  var counterEl = document.getElementById('counter');
  var hintEl = document.getElementById('navHint');

  var chapterBars = {{
    2: document.getElementById('chapterBar-findings'),
    3: document.getElementById('chapterBar-competition'),
    5: document.getElementById('chapterBar-recommendations')
  }};

  var chapterMapBySection = {{
    2: {{ 0:0, 1:1, 2:1, 3:1, 4:2, 5:2, 6:2, 7:3, 8:3, 9:3, 10:3, 11:4, 12:4, 13:4 }},
    3: {{ 0:0, 1:1, 2:1, 3:1, 4:1, 5:2, 6:2, 7:2, 8:3, 9:3, 10:3, 11:3, 12:4, 13:4, 14:4 }},
    5: {{ 0:0, 1:0, 2:1, 3:1, 4:2, 5:2, 6:3, 7:3, 8:4, 9:4, 10:5, 11:5, 12:0 }}
  }};

  function getSectionStart(section) {{
    for (var i = 0; i < allScreens.length; i++) {{
      if (allScreens[i].section === section) return i;
    }}
    return -1;
  }}

  function updateChapterBar(section, idx) {{
    Object.keys(chapterBars).forEach(function(s) {{
      var bar = chapterBars[s];
      if (!bar) return;
      bar.style.opacity = '0';
      bar.style.pointerEvents = 'none';
    }});
    var bar = chapterBars[section];
    if (!bar) return;
    var start = getSectionStart(section);
    var localIdx = idx - start;
    var map = chapterMapBySection[section];
    var ch = map && map[localIdx] !== undefined ? map[localIdx] : 0;
    if (ch > 0) {{
      bar.style.opacity = '1';
      bar.style.pointerEvents = 'auto';
      var items = bar.querySelectorAll('.chapter-bar-item');
      items.forEach(function(item, i) {{
        var num = i + 1;
        item.classList.remove('active', 'completed');
        if (num < ch) item.classList.add('completed');
        if (num === ch) item.classList.add('active');
      }});
    }}
  }}

  function updateGraph(persona, stageIdx) {{
    if (typeof window.updatePersonaGraph === 'function') {{
      window.updatePersonaGraph(persona, stageIdx);
    }}
  }}

  function showScreen(idx) {{
    if (idx < 0 || idx >= totalSteps) return;
    var prev = allScreens[currentIdx];
    var next = allScreens[idx];

    if (prev) {{
      prev.el.classList.remove('active');
      if (prev.type === 'journey') prev.el.classList.remove('detail-mode');
      prev.el.querySelectorAll && prev.el.querySelectorAll('.bar-fill').forEach(function(b) {{
        b.style.width = '';
      }});
    }}

    next.el.classList.add('active');

    if (next.type === 'journey' && next.persona) {{
      updateGraph(next.persona, next.stage);
    }}

    if (next.type === 'slide' && next.el.querySelectorAll) {{
      var fills = next.el.querySelectorAll('.bar-fill');
      if (fills.length) {{
        fills.forEach(function(b) {{ b.style.width = '0'; }});
        requestAnimationFrame(function() {{
          requestAnimationFrame(function() {{
            fills.forEach(function(b) {{ b.style.width = ''; }});
          }});
        }});
      }}
    }}

    currentIdx = idx;
    progressEl.style.width = ((idx + 1) / totalSteps * 100) + '%';
    counterEl.textContent = (idx + 1) + ' / ' + totalSteps;

    if (next.section === 2 || next.section === 3 || next.section === 5) {{
      updateChapterBar(next.section, idx);
    }} else {{
      Object.keys(chapterBars).forEach(function(s) {{
        var bar = chapterBars[s];
        if (bar) {{ bar.style.opacity = '0'; bar.style.pointerEvents = 'none'; }}
      }});
    }}
  }}

  document.addEventListener('keydown', function(e) {{
    if (e.key === 'ArrowRight' || e.key === ' ' || e.key === 'Enter') {{ e.preventDefault(); showScreen(currentIdx + 1); }}
    if (e.key === 'ArrowLeft' || e.key === 'Backspace') {{ e.preventDefault(); showScreen(currentIdx - 1); }}
    if (e.key === 'Home') {{ e.preventDefault(); showScreen(0); }}
    if (e.key === 'End') {{ e.preventDefault(); showScreen(totalSteps - 1); }}
  }});

  document.addEventListener('click', function(e) {{
    if (e.target.closest('button') || e.target.closest('a') || e.target.closest('.nav-panel')) return;
    var w = window.innerWidth;
    if (e.clientX > w * 0.6) showScreen(currentIdx + 1);
    else if (e.clientX < w * 0.4) showScreen(currentIdx - 1);
  }});

  setTimeout(function() {{ hintEl.classList.add('hidden'); }}, 3500);

  // Remove active from all, then show first
  document.querySelectorAll('.slide.active, .journey-view.active').forEach(function(el) {{
    el.classList.remove('active');
  }});
  showScreen(0);
}})();
"""

    output = f'''<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>Student Food & Delivery Research</title>
<link rel="preconnect" href="https://fonts.googleapis.com">
<link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
<link href="https://fonts.googleapis.com/css2?family=DM+Sans:ital,opsz,wght@0,9..40,400;0,9..40,500;0,9..40,600;1,9..40,400&family=Newsreader:ital,opsz,wght@0,16..72,400;0,16..72,600;0,16..72,700;1,16..72,400&display=swap" rel="stylesheet">
<link href="https://fonts.googleapis.com/css2?family=Instrument+Serif:ital@0;1&family=Plus+Jakarta+Sans:ital,wght@0,300;0,400;0,500;0,600;0,700;1,400&display=swap" rel="stylesheet">
<style>
{combined_css}
</style>
</head>
<body>
  <!-- Chapter bars (hidden by default) -->
  {chapter_bars_html}

  <!-- Section 1: Assumptions -->
  {sections_body[0]}

  <!-- Section 2: Findings -->
  {sections_body[1]}

  <!-- Section 3: Competition -->
  {sections_body[2]}

  <!-- Section 4: Personas -->
  {sections_body[3]}

  <!-- Section 5: Recommendations -->
  {sections_body[4]}

  <!-- Section 6: Close -->
  {sections_body[5]}

  <!-- Navigation UI -->
  <div class="progress-bar" id="progress"></div>
  <div class="slide-counter" id="counter"></div>
  <div class="nav-hint" id="navHint">Arrow keys or click to navigate</div>

  <script>
{unified_script}
  </script>
</body>
</html>
'''

    OUTPUT_FILE.write_text(output, encoding="utf-8")
    print(f"Written to {OUTPUT_FILE}")
    print(f"Line count: {len(output.splitlines())}")


if __name__ == "__main__":
    main()
