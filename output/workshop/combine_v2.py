#!/usr/bin/env python3
"""Combine 6 HTML presentation sections into one file.
Uses CSS nesting to scope each section's styles under a wrapper class,
preventing cross-section style conflicts."""

import re, os

DIR = os.path.dirname(os.path.abspath(__file__))

def read(name):
    with open(os.path.join(DIR, name), 'r', encoding='utf-8') as f:
        return f.read()

def between(html, start, end):
    s = html.find(start)
    if s == -1: return ''
    s += len(start)
    e = html.find(end, s)
    if e == -1: return ''
    return html[s:e]

def get_css(html):
    return between(html, '<style>', '</style>').strip()

def get_body(html):
    body = between(html, '<body>', '</body>')
    body = re.sub(r'<script[\s\S]*?</script>', '', body)
    body = re.sub(r'<!-- Navigation -->', '', body)
    body = re.sub(r'<!-- ========== NAV UI ========== -->', '', body)
    body = re.sub(r'<!-- ========== JUMP NAV ========== -->', '', body)
    for pat in [
        r'<div\s+class="progress-bar"[^>]*></div>',
        r'<div\s+class="slide-counter"[^>]*></div>',
        r'<div\s+class="nav-hint"[^>]*>[\s\S]*?</div>',
        r'<div\s+class="progress"[^>]*></div>',
        r'<div\s+class="counter"[^>]*></div>',
        r'<button\s+class="nav-btn"[^>]*>[\s\S]*?</button>',
        r'<div\s+class="nav-overlay"[^>]*></div>',
        r'<div\s+class="nav-panel"[^>]*></div>',
    ]:
        body = re.sub(pat, '', body)
    body = re.sub(r'class="slide active"', 'class="slide"', body)
    body = re.sub(r'class="slide section-divider active"', 'class="slide section-divider"', body)
    body = re.sub(r'class="slide intro-slide active"', 'class="slide intro-slide"', body)
    return body.strip()

def remove_block(css, pattern):
    while True:
        m = re.search(pattern, css)
        if not m:
            break
        start = m.start()
        pos = css.find('{', start)
        if pos == -1:
            break
        depth = 1
        i = pos + 1
        while i < len(css) and depth > 0:
            if css[i] == '{': depth += 1
            elif css[i] == '}': depth -= 1
            i += 1
        css = css[:start] + css[i:]
    return css

def strip_globals(css):
    css = remove_block(css, r':root\s*\{')
    css = remove_block(css, r'\*\s*,\s*\*::before\s*,\s*\*::after\s*\{')
    css = remove_block(css, r'(?<![.\w#-])\*\s*\{')
    css = remove_block(css, r'(?<![.\w#-])body\s*\{')
    css = remove_block(css, r'(?<![.\w#-])html\s*\{')
    css = remove_block(css, r'@media\s*\(\s*prefers-reduced-motion')
    for pat in [r'\.progress-bar\s*\{', r'\.slide-counter\s*\{',
                r'(?<!\w)\.nav-hint\b[^{]*\{', r'\.nav-hint\.hidden\s*\{',
                r'\.progress\s*\{', r'\.counter\s*\{']:
        css = remove_block(css, pat)
    return css.strip()

def strip_persona_nav_ui(css):
    for pat in [
        r'\.nav-btn\b[^{]*\{', r'\.nav-btn:hover\s*\{',
        r'\.nav-btn\.open\b[^{]*\{',
        r'\.nav-btn\s+span\s*\{',
        r'\.nav-overlay\b[^{]*\{', r'\.nav-overlay\.open\s*\{',
        r'\.nav-panel\b[^{]*\{', r'\.nav-panel\.open\s*\{',
        r'\.nav-section-label\b[^{]*\{',
        r'\.nav-item\b[^{]*\{', r'\.nav-item:hover\s*\{', r'\.nav-item\.active\s*\{',
        r'\.nav-dot\s*\{',
        r'\.nav-stage-list\s*\{', r'\.nav-stage-item\b[^{]*\{',
    ]:
        css = remove_block(css, pat)
    return css

def extract_keyframes(css):
    keyframes = []
    while True:
        m = re.search(r'@keyframes\s+[\w-]+\s*\{', css)
        if not m:
            break
        start = m.start()
        pos = m.end() - 1
        depth = 1
        i = pos + 1
        while i < len(css) and depth > 0:
            if css[i] == '{': depth += 1
            elif css[i] == '}': depth -= 1
            i += 1
        keyframes.append(css[start:i])
        css = css[:start] + css[i:]
    return css.strip(), '\n'.join(keyframes)

def get_persona_script(html):
    script = between(html, '<script>', '</script>').strip()
    if script.startswith('(function() {'):
        script = script[len('(function() {'):]
    if script.rstrip().endswith('})();'):
        script = script.rstrip()[:-len('})();')]

    nav_marker = '// ---- Navigation state ----'
    nav_idx = script.find(nav_marker)
    part1 = script[:nav_idx].strip() if nav_idx > 0 else script.strip()

    ug_marker = '  function updateGraph('
    ug_start = script.find(ug_marker)
    show_marker = '\n  function showScreen('
    show_start = script.find(show_marker, ug_start) if ug_start > 0 else -1
    part2 = ''
    if ug_start > 0 and show_start > ug_start:
        part2 = script[ug_start:show_start].strip()

    return part1 + '\n\n  ' + part2

# ============================================================
# READ ALL FILES
# ============================================================
print('Reading source files...')
sec1_html = read('01_assumptions.html')
sec2_html = read('02_findings.html')
sec3_html = read('03_competition.html')
sec4_html = read('persona_journeys_v2.html')
sec5_html = read('05_recommendations.html')
sec6_html = read('06_close.html')

# Extract and scope CSS
css1 = strip_globals(get_css(sec1_html))
css2 = strip_globals(get_css(sec2_html))
css3 = strip_globals(get_css(sec3_html))
css4_raw = strip_globals(get_css(sec4_html))
css4_raw = strip_persona_nav_ui(css4_raw)
css4, keyframes4 = extract_keyframes(css4_raw)
css5 = strip_globals(get_css(sec5_html))
css6 = strip_globals(get_css(sec6_html))

# Extract body content
body1 = get_body(sec1_html)
body2 = get_body(sec2_html)
body3 = get_body(sec3_html)
body4 = get_body(sec4_html)
body5 = get_body(sec5_html)
body6 = get_body(sec6_html)

# Persona script
persona_script = get_persona_script(sec4_html)

# ============================================================
# BUILD COMBINED HTML
# ============================================================
print('Building combined file...')

parts = []
parts.append('''<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>Student Food &amp; Delivery Research — Deliveroo Plus</title>
<link rel="preconnect" href="https://fonts.googleapis.com">
<link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
<link href="https://fonts.googleapis.com/css2?family=DM+Sans:ital,opsz,wght@0,9..40,400;0,9..40,500;0,9..40,600;1,9..40,400&family=Newsreader:ital,opsz,wght@0,16..72,400;0,16..72,600;0,16..72,700;1,16..72,400&family=Instrument+Serif:ital@0;1&family=Plus+Jakarta+Sans:ital,wght@0,300;0,400;0,500;0,600;0,700;1,400&display=swap" rel="stylesheet">
<style>
/* ============================================
   GLOBAL VARIABLES & RESET
   ============================================ */
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
  --ease-expo: cubic-bezier(0.16, 1, 0.3, 1);
  --duration: 450ms;
  --bg: #f8f6f1;
  --bg-warm: #f2efe8;
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
}

*, *::before, *::after { margin: 0; padding: 0; box-sizing: border-box; }

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

.progress-bar {
  position: fixed; bottom: 0; left: 0;
  height: 2px; background: var(--accent); z-index: 500;
  transition: width 0.4s var(--ease);
}
.slide-counter {
  position: fixed; bottom: 1rem; right: 1.5rem;
  font-size: 0.55rem; font-weight: 500;
  color: var(--text-tertiary); z-index: 500;
  letter-spacing: 0.06em; font-variant-numeric: tabular-nums;
}
.nav-hint {
  position: fixed; bottom: 2.8rem; left: 50%;
  transform: translateX(-50%);
  font-size: 0.58rem; color: var(--text-tertiary);
  z-index: 500; transition: opacity 0.8s; opacity: 0.6;
}
.nav-hint.hidden { opacity: 0; }

@media (prefers-reduced-motion: reduce) {
  *, *::before, *::after { transition-duration: 0.01ms !important; animation-duration: 0.01ms !important; }
}
''')

if keyframes4:
    parts.append(keyframes4 + '\n')

parts.append('\n/* ============================================\n   SECTION 1: ASSUMPTIONS\n   ============================================ */\n.sec-1 {\n')
parts.append(css1)
parts.append('\n}\n')

parts.append('\n/* ============================================\n   SECTION 2: FINDINGS\n   ============================================ */\n.sec-2 {\n')
parts.append(css2)
parts.append('\n}\n')

parts.append('\n/* ============================================\n   SECTION 3: COMPETITION\n   ============================================ */\n.sec-3 {\n')
parts.append(css3)
parts.append('\n}\n')

parts.append('\n/* ============================================\n   SECTION 4: PERSONAS\n   ============================================ */\n.sec-4 {\n  --serif: \'Instrument Serif\', Georgia, serif;\n  --sans: \'Plus Jakarta Sans\', -apple-system, system-ui, sans-serif;\n')
parts.append(css4)
parts.append('\n}\n')

parts.append('\n/* ============================================\n   SECTION 5: RECOMMENDATIONS\n   ============================================ */\n.sec-5 {\n')
parts.append(css5)
parts.append('\n}\n')

parts.append('\n/* ============================================\n   SECTION 6: CLOSE\n   ============================================ */\n.sec-6 {\n')
parts.append(css6)
parts.append('\n}\n')

parts.append('</style>\n</head>\n<body>\n')

parts.append('\n<!-- ===== SECTION 1: ASSUMPTIONS ===== -->\n<div class="sec-1">\n')
parts.append(body1)
parts.append('\n</div>\n')

parts.append('\n<!-- ===== SECTION 2: FINDINGS ===== -->\n<div class="sec-2">\n')
parts.append(body2)
parts.append('\n</div>\n')

parts.append('\n<!-- ===== SECTION 3: COMPETITION ===== -->\n<div class="sec-3">\n')
parts.append(body3)
parts.append('\n</div>\n')

parts.append('\n<!-- ===== SECTION 4: PERSONAS ===== -->\n<div class="sec-4">\n')
parts.append(body4)
parts.append('\n</div>\n')

parts.append('\n<!-- ===== SECTION 5: RECOMMENDATIONS ===== -->\n<div class="sec-5">\n')
parts.append(body5)
parts.append('\n</div>\n')

parts.append('\n<!-- ===== SECTION 6: CLOSE ===== -->\n<div class="sec-6">\n')
parts.append(body6)
parts.append('\n</div>\n')

parts.append('''
<!-- Navigation UI -->
<div class="progress-bar" id="progress"></div>
<div class="slide-counter" id="counter"></div>
<div class="nav-hint" id="navHint">Arrow keys or click to navigate</div>

<script>
(function() {
  // ======= PERSONA DOM GENERATION =======
''')
parts.append(persona_script)
parts.append('''

  // ======= BUILD SCREEN LIST =======
  var PERSONAS_REF = PERSONAS;
  var allScreens = [];

  document.querySelectorAll('.sec-1 .slide').forEach(function(el) {
    allScreens.push({ type: 'slide', el: el, section: 1 });
  });

  document.querySelectorAll('.sec-2 .slide').forEach(function(el) {
    allScreens.push({ type: 'slide', el: el, section: 2 });
  });

  document.querySelectorAll('.sec-3 .slide').forEach(function(el) {
    allScreens.push({ type: 'slide', el: el, section: 3 });
  });

  // Section 4: Personas (special ordering)
  var s4Divider = document.querySelector('.sec-4 [data-slide="divider"]');
  var s4Title = document.querySelector('.sec-4 [data-slide="title"]');
  var s4Intro = document.querySelector('.sec-4 [data-slide="intro"]');
  if (s4Divider) allScreens.push({ type: 'slide', el: s4Divider, section: 4 });
  if (s4Title) allScreens.push({ type: 'slide', el: s4Title, section: 4 });
  if (s4Intro) allScreens.push({ type: 'slide', el: s4Intro, section: 4 });

  PERSONAS_REF.forEach(function(p) {
    var introEl = document.querySelector('.sec-4 [data-slide="persona-intro-' + p.id + '"]');
    if (introEl) allScreens.push({ type: 'slide', el: introEl, section: 4, persona: p });
    var journeyEl = document.querySelector('.sec-4 [data-slide="journey-' + p.id + '"]');
    if (journeyEl) {
      allScreens.push({ type: 'journey', el: journeyEl, section: 4, persona: p, stage: -1 });
      for (var s = 0; s < 6; s++) {
        allScreens.push({ type: 'journey', el: journeyEl, section: 4, persona: p, stage: s });
      }
    }
  });

  var s4Comp = document.querySelector('.sec-4 [data-slide="comparison"]');
  var s4Close = document.querySelector('.sec-4 [data-slide="closing"]');
  if (s4Comp) allScreens.push({ type: 'slide', el: s4Comp, section: 4 });
  if (s4Close) allScreens.push({ type: 'slide', el: s4Close, section: 4 });

  document.querySelectorAll('.sec-5 .slide').forEach(function(el) {
    allScreens.push({ type: 'slide', el: el, section: 5 });
  });

  document.querySelectorAll('.sec-6 .slide').forEach(function(el) {
    allScreens.push({ type: 'slide', el: el, section: 6 });
  });

  // ======= CHAPTER BAR MANAGEMENT =======
  var barEls = {
    2: document.querySelector('.sec-2 .chapter-bar'),
    3: document.querySelector('.sec-3 .chapter-bar'),
    5: document.querySelector('.sec-5 .chapter-bar')
  };

  var chapterMaps = {
    2: [0, 1,1,1, 2,2,2, 3,3,3,3, 4,4,4, 0],
    3: [0, 1,1,1,1, 2,2,2, 3,3,3,3, 4,4,4, 0],
    5: [0, 0, 1,1, 2,2, 3,3, 4,4, 5,5, 0]
  };

  function hideAllBars() {
    [2,3,5].forEach(function(k) {
      if (barEls[k]) barEls[k].style.opacity = '0';
    });
  }

  function updateChapterBar(section, localIdx) {
    hideAllBars();
    var bar = barEls[section];
    if (!bar) return;
    var map = chapterMaps[section];
    if (!map) return;
    var ch = (localIdx < map.length) ? map[localIdx] : 0;
    if (ch === 0) return;
    bar.style.opacity = '1';
    bar.querySelectorAll('.chapter-bar-item').forEach(function(item, i) {
      var num = i + 1;
      item.classList.remove('active', 'completed');
      if (num < ch) item.classList.add('completed');
      if (num === ch) item.classList.add('active');
    });
  }

  // ======= NAVIGATION =======
  var currentIdx = 0;
  var totalSteps = allScreens.length;
  var progressEl = document.getElementById('progress');
  var counterEl = document.getElementById('counter');
  var hintEl = document.getElementById('navHint');

  function getLocalIdx(globalIdx) {
    var screen = allScreens[globalIdx];
    var count = 0;
    for (var i = 0; i < globalIdx; i++) {
      if (allScreens[i].section === screen.section) count++;
    }
    return count;
  }

  function showScreen(idx) {
    if (idx < 0 || idx >= totalSteps) return;
    var prev = allScreens[currentIdx];
    var next = allScreens[idx];
    var changingElement = prev.el !== next.el;

    if (changingElement) {
      prev.el.classList.remove('active');
      if (prev.type === 'journey') prev.el.classList.remove('detail-mode');
    }

    if (next.type === 'slide') {
      next.el.querySelectorAll('.bar-fill').forEach(function(b) { b.style.width = '0'; });
    }

    if (next.type === 'journey' && changingElement) {
      next.el.style.transition = 'none';
      next.el.querySelectorAll('.graph-panel, .detail-panel, .journey-persona-name, .graph-subtitle, .graph-container').forEach(function(el) {
        el.style.transition = 'none';
      });
      updateGraph(next.persona, next.stage);
      next.el.offsetHeight;
      next.el.style.transition = '';
      next.el.querySelectorAll('.graph-panel, .detail-panel, .journey-persona-name, .graph-subtitle, .graph-container').forEach(function(el) {
        el.style.transition = '';
      });
    }

    next.el.classList.add('active');

    if (next.type === 'journey' && !changingElement) {
      updateGraph(next.persona, next.stage);
    }

    if (next.type === 'slide') {
      requestAnimationFrame(function() {
        requestAnimationFrame(function() {
          next.el.querySelectorAll('.bar-fill').forEach(function(b) { b.style.width = ''; });
        });
      });
    }

    currentIdx = idx;

    var accent = next.persona ? next.persona.color : 'var(--accent)';
    progressEl.style.width = ((idx + 1) / totalSteps * 100) + '%';
    progressEl.style.background = accent;
    counterEl.textContent = (idx + 1) + ' / ' + totalSteps;

    updateChapterBar(next.section, getLocalIdx(idx));
  }

  document.addEventListener('keydown', function(e) {
    if (e.key === 'ArrowRight' || e.key === ' ' || e.key === 'Enter') { e.preventDefault(); showScreen(currentIdx + 1); }
    if (e.key === 'ArrowLeft' || e.key === 'Backspace') { e.preventDefault(); showScreen(currentIdx - 1); }
    if (e.key === 'Home') { e.preventDefault(); showScreen(0); }
    if (e.key === 'End') { e.preventDefault(); showScreen(totalSteps - 1); }
  });

  document.addEventListener('click', function(e) {
    if (e.target.closest('button') || e.target.closest('a') || e.target.closest('svg')) return;
    var w = window.innerWidth;
    if (e.clientX > w * 0.6) showScreen(currentIdx + 1);
    else if (e.clientX < w * 0.35) showScreen(currentIdx - 1);
  });

  setTimeout(function() { hintEl.classList.add('hidden'); }, 3500);

  document.querySelectorAll('.slide.active, .journey-view.active').forEach(function(el) {
    el.classList.remove('active');
  });
  hideAllBars();
  showScreen(0);
})();
</script>
</body>
</html>
''')

output = ''.join(parts)
outpath = os.path.join(DIR, 'full_presentation.html')
with open(outpath, 'w', encoding='utf-8') as f:
    f.write(output)

slide_count = output.count('class="slide')
journey_count = output.count('class="journey-view"')
print(f'Done! Written to {outpath}')
print(f'Slide elements: ~{slide_count}, Journey views: ~{journey_count}')
