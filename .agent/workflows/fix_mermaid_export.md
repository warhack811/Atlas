---
description: Fix Mermaid PDF/PNG export issues using Computed Style Baking
---

# Mermaid Export Fix Workflow

This workflow implements a robust "Computed Style Baking" strategy to resolve PDF "black box" issues and PNG export failures.

## 1. Analysis & Preparation
- [x] Confirm `svg2pdf.js` limitations regarding CSS variables (Done in Planning).
- [ ] Create backup of `MermaidViewer.tsx` (optional but good practice).

## 2. Implementation (`MermaidViewer.tsx`)
- [ ] Import `Loader2` from `lucide-react` for feedback state.
- [ ] Rewrite `getSvgForExport` function:
    - [ ] Create a deep clone of the SVG.
    - [ ] Iterate recursively through all elements.
    - [ ] Use `window.getComputedStyle()` to capture:
        - `fill`, `stroke`, `stroke-width`
        - `font-family`, `font-size`, `font-weight`
        - `opacity`, `visibility`, `display`
    - [ ] Apply these styles inline (`element.style.setProperty(...)`).
    - [ ] Force a white/theme-appropriate background rectangle if transparent.
- [ ] Update `downloadPNG` and `downloadPDF` to use the new async/baked SVG.

## 3. Verification
- [ ] Verify PDF export (No black boxes).
- [ ] Verify PNG export (Correct styles).
- [ ] Confirm no side effects on the interactive viewer (Zoom/Pan).

## 4. Final Review
- [ ] Request user approval before marking task complete.
